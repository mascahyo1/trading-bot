"""
Saham Trading Bot untuk Pasar Saham Indonesia

Bot ini menganalisis saham Indonesia (kode .JK) setiap 5 menit,
menghasilkan sinyal trading berdasarkan analisis teknikal,
dan mengeksekusi transaksi via browser automation di Ajaib.

Arsitektur:
- yfinance untuk data harga
- Playwright untuk eksekusi transaksi di Ajaib
- State file (saham_state.json) untuk komunikasi dengan Telegram handler
- Tidak polling Telegram (di-handle oleh telegram_handler.py terpisah)

Fitur:
- Monitor 20 saham blue-chip
- Analisis teknikal (RSI, MACD, EMA, Bollinger, ATR, Volume)
- Fee-aware trading (biaya beli/jual otomatis dihitung)
- Portfolio report tiap 5 menit ke Telegram
- Net PnL (setelah potong biaya)

Author: AI Trading Bot
"""

import time
import logging
import signal
import os
import sys
import json
import threading
from datetime import datetime
from config import (
    TRADING_STOCKS, ALL_STOCKS, INTERVAL_SECONDS,
    MAX_OPEN_POSITIONS, POSITION_SIZE_IDR, MIN_ORDER_IDR,
    STOCK_CODE_MAP, BUY_TOTAL_FEE_PCT, SELL_TOTAL_FEE_PCT,
    now_jakarta, format_datetime, LOT_SIZE,
)

from exchange import StockExchange
from analyzer import MarketAnalyzer
from strategy import RiskManager, TradingStrategy
from notifier import setup_logger, TradeNotifier
from telegram_notifier import TelegramNotifier
from ajaib_trader import AjaibTrader

try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAHAM_STATE_FILE = os.path.join(SCRIPT_DIR, "saham_state.json")


class SahamBot:
    """
    Main bot class untuk trading saham Indonesia.
    
    Bot ini tidak polling Telegram. Sebagian, ia menulis state ke file
    (saham_state.json) yang dibaca oleh telegram_handler.py untuk
    merespon command Telegram.
    
    Attributes:
        exchange (StockExchange): yfinance wrapper
        analyzer (MarketAnalyzer): Technical analysis engine
        risk_manager (RiskManager): Risk management
        strategy (TradingStrategy): Trading strategy
        trader (AjaibTrader): Browser automation untuk Ajaib
    """
    def __init__(self):
        """
        Inisialisasi semua komponen bot: exchange (yfinance), analyzer,
        risk manager, strategy, notifier, Telegram, dan Ajaib trader.
        Bot belum berjalan sampai start() dipanggil.
        """
        self.logger = logging.getLogger("saham_bot")
        self.exchange = StockExchange()
        self.analyzer = MarketAnalyzer(use_llm=False)
        self.risk_manager = RiskManager()
        self.strategy = TradingStrategy(self.analyzer, self.risk_manager)
        self.notifier = TradeNotifier()
        self.telegram = TelegramNotifier()
        self.trader = AjaibTrader()
        self.running = False
        self.cycle_count = 0
        self.start_time = now_jakarta()
        self.daily_pnl = 0
        self.trades_today = 0
        self._stop_event = threading.Event()
        self._last_cash = 0
        # Cache portfolio terakhir dari Ajaib; dibaca telegram_handler via state file
        self._portfolio_cache = {"cash": 0, "stocks": [], "timestamp": ""}


    def is_market_open(self):
        """
        Cek apakah pasar saham BEI sedang buka untuk sesi reguler.

        Sesi perdagangan reguler BEI:
          - Sesi I  : 09:00 - 11:30 WIB
          - Sesi II : 13:30 - 14:59 WIB
        Sabtu/Minggu libur.

        Returns:
            bool: True jika dalam jam perdagangan reguler.
        """
        now = now_jakarta()
        if now.weekday() >= 5:
            return False
        hour = now.hour
        minute = now.minute
        if hour == 9 and minute >= 0:
            return True
        if hour == 10 or hour == 11:
            return True
        if hour == 13 or hour == 14:
            return True
        return False

    def get_cash_balance(self):
        """
        Ambil saldo kas terakhir yang diketahui (dari cache internal).

        Returns:
            float: Saldo kas IDR dari update_cash_balance() terakhir. 0 jika belum pernah sync.
        """
        return self._last_cash

    def update_cash_balance(self):
        """Sinkronkan saldo kas dari scrape halaman home Ajaib ke cache internal."""
        try:
            portfolio = self.trader.get_portfolio()
            if portfolio and portfolio.get("cash") is not None:
                self._last_cash = portfolio["cash"]
        except Exception as e:
            self.logger.warning(f"Could not update cash balance: {e}")

    def execute_buy(self, symbol, lots, current_price):
        """
        Eksekusi order BELI via browser Ajaib + catat posisi + kirim notifikasi.

        Args:
            symbol (str): Simbol saham (mis. "BBCA.JK")
            lots (int): Jumlah lot yang dibeli
            current_price (float): Harga referensi saat order dikirim

        Returns:
            bool: True jika order berhasil dikirim dan posisi tercatat.
        """
        code = STOCK_CODE_MAP.get(symbol, symbol.replace(".JK", ""))
        self.logger.info(f"Executing BUY: {code} x{lots} lots @ {current_price:,.0f}")

        result = self.trader.buy(symbol, lots)
        if result and result.get("success"):
            self.risk_manager.add_position(symbol, current_price, lots, code)
            self.notifier.notify_trade(symbol, "BUY", current_price, lots)
            self.telegram.notify_trade(symbol, "BUY", current_price, lots)
            self.trades_today += 1
            return True
        else:
            error = result.get("error", "unknown") if result else "no response"
            self.logger.error(f"Buy failed: {error}")
            return False

    def execute_sell(self, symbol, current_price):
        """
        Eksekusi order JUAL SELURUH posisi + tutup posisi + kirim notifikasi net PnL.

        Args:
            symbol (str): Simbol saham (mis. "BBCA.JK")
            current_price (float): Harga referensi saat order dikirim

        Returns:
            bool: True jika seluruh posisi berhasil dijual.
        """
        if symbol in self.risk_manager.positions:
            pos = self.risk_manager.positions[symbol]
            lots = pos.lots
            self.logger.info(f"Executing SELL: {pos.code} x{lots} lots @ {current_price:,.0f}")

            result = self.trader.sell(symbol, lots)
            if result and result.get("success"):
                exit_price = current_price
                trade_record = self.risk_manager.close_position(symbol, exit_price)
                if trade_record:
                    self.notifier.notify_trade(
                        symbol, "SELL", exit_price, lots,
                        pnl=trade_record["pnl_amount"]
                    )
                    self.telegram.notify_trade(
                        symbol, "SELL", exit_price, lots,
                        pnl=trade_record["pnl_amount"]
                    )
                    self.daily_pnl += trade_record["pnl_amount"]
                    self.trades_today += 1
                return True
            else:
                error = result.get("error", "unknown") if result else "no response"
                self.logger.error(f"Sell failed: {error}")
        return False

    def execute_sell_partial(self, symbol, current_price, lots):
        """
        Eksekusi order JUAL SEBAGIAN posisi (profit taking TP1).

        Net PnL dihitung manual karena posisi tidak ditutup penuh:
            net_pnl = (nilai jual - biaya jual) - cost basis lot yang dijual

        Args:
            symbol (str): Simbol saham
            current_price (float): Harga referensi saat order dikirim
            lots (int): Jumlah lot yang dijual sebagian

        Returns:
            bool: True jika partial sell berhasil.
        """
        if symbol in self.risk_manager.positions:
            pos = self.risk_manager.positions[symbol]
            self.logger.info(f"Executing PARTIAL SELL: {pos.code} x{lots} lots @ {current_price:,.0f}")

            result = self.trader.sell(symbol, lots)
            if result and result.get("success"):
                sell_value = current_price * lots * LOT_SIZE
                sell_fees = sell_value * SELL_TOTAL_FEE_PCT
                cost_basis = pos.entry_price * lots * LOT_SIZE
                net_pnl = (sell_value - sell_fees) - cost_basis

                self.notifier.notify_trade(symbol, "PARTIAL SELL", current_price, lots, net_pnl)
                self.telegram.notify_trade(symbol, "PARTIAL SELL", current_price, lots, net_pnl)
                self.daily_pnl += net_pnl
                self.trades_today += 1
                return True
            else:
                error = result.get("error", "unknown") if result else "no response"
                self.logger.error(f"Partial sell failed: {error}")
        return False

    def scan_all_stocks(self):
        """
        Scan semua saham di ALL_STOCKS: fetch candle 90 hari + harga terkini,
        lalu jalankan analisis teknikal untuk masing-masing.

        Delay 0.3s antar saham untuk hindari rate-limit yfinance.

        Returns:
            list: Hasil analisis per saham {signal, confidence, indicators, symbol, current_price}
        """
        results = []
        for symbol in ALL_STOCKS:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, period="90d", interval="1d")
                if not ohlcv or len(ohlcv) < 50:
                    continue

                ticker = self.exchange.fetch_ticker(symbol)
                if not ticker:
                    continue

                analysis = self.analyzer.analyze(ohlcv, symbol=symbol)
                analysis["symbol"] = symbol
                analysis["current_price"] = ticker["last"]
                results.append(analysis)
            except Exception as e:
                self.logger.warning(f"[{symbol}] Scan error: {e}")
            time.sleep(0.3)
        return results

    def get_top_candidates(self, results, signal_type="buy"):
        """
        Filter hasil scan dan ambil kandidat terbaik untuk dieksekusi.

        Args:
            results (list): Hasil analisis semua saham dari scan_all_stocks()
            signal_type (str): "buy" atau "sell"

        Returns:
            list: Maks 5 kandidat dengan confidence > 55%, urut tertinggi.
        """
        filtered = [r for r in results if r["signal"] == signal_type and r["confidence"] > 0.55]
        filtered.sort(key=lambda x: x["confidence"], reverse=True)
        return filtered[:5]

    def process_stock(self, symbol, ohlcv=None, is_primary=True):
        """
        Proses satu saham: evaluasi sinyal via strategy lalu eksekusi aksinya.

        Aksi yang mungkin:
          - buy          : cek saldo cukup (termasuk fee beli) -> execute_buy()
          - partial_sell : profit taking sebagian       -> execute_sell_partial()
          - close        : jual seluruh posisi           -> execute_sell()

        Error per-saham ditangkap di sini agar satu kegagalan tidak
        menghentikan pemrosesan saham lain.

        Args:
            symbol (str): Simbol saham
            ohlcv (list, optional): Data candle; di-fetch otomatis jika None
            is_primary (bool): True jika termasuk TRADING_STOCKS (risk lebih besar boleh)
        """
        try:
            if ohlcv is None:
                ohlcv = self.exchange.fetch_ohlcv(symbol, period="90d", interval="1d")
            if not ohlcv or len(ohlcv) < 50:
                self.logger.warning(f"[{symbol}] Insufficient data")
                return

            ticker = self.exchange.fetch_ticker(symbol)
            if not ticker:
                self.logger.warning(f"[{symbol}] Ticker failed")
                return

            current_price = ticker["last"]
            cash = self.get_cash_balance()

            if cash <= 0:
                self.logger.warning(f"[{symbol}] No cash data")
                return

            decision = self.strategy.evaluate(symbol, ohlcv, cash, current_price, is_primary=is_primary)
            action = decision["action"]
            analysis = decision["analysis"]

            self.notifier.notify_signal(
                symbol, analysis["signal"], analysis["confidence"],
                analysis["indicators"]
            )

            if action == "buy":
                lots = decision["lots"]
                if lots == 0:
                    self.logger.warning(f"[{symbol}] Insufficient balance")
                    return
                est_cost_with_fees = lots * LOT_SIZE * current_price * (1 + BUY_TOTAL_FEE_PCT)
                if est_cost_with_fees > cash:
                    self.logger.warning(
                        f"[{symbol}] Need {est_cost_with_fees:,.0f} (incl fees), have {cash:,.0f}"
                    )
                    return
                self.execute_buy(symbol, lots, current_price)

            elif action == "partial_sell":
                lots = decision["lots"]
                reason = decision.get("reason", "tp1_hit")
                self.logger.info(f"[{symbol}] Partial sell: {reason}")
                self.execute_sell_partial(symbol, current_price, lots)

            elif action == "close":
                reason = decision.get("reason", "signal")
                self.logger.info(f"[{symbol}] Close: {reason}")
                self.execute_sell(symbol, current_price)

        except Exception as e:
            self.notifier.notify_error(f"[{symbol}] {str(e)}")
            self.telegram.notify_error(f"[{symbol}] {str(e)}")

    def write_state_to_file(self):
        """
        Tulis state bot ke saham_state.json untuk dikonsumsi telegram_handler.py.

        Karena Saham bot TIDAK polling Telegram, semua command yang butuh data
        (status, portfolio, analytics) dibaca dari file ini oleh listener
        terpusat di proses Indodax bot. Dipanggil setiap akhir cycle.
        """
        try:
            state = {
                "timestamp": now_jakarta().isoformat(),
                "cycle_count": self.cycle_count,
                "cash": self._last_cash,
                "portfolio": self._portfolio_cache,
                "positions": {
                    sym: pos.to_dict()
                    for sym, pos in self.risk_manager.positions.items()
                    if pos.status == "open"
                },
                "analytics": {
                    "total_trades": len(self.risk_manager.trade_history),
                    "total_pnl": self.risk_manager.get_total_pnl(),
                    "win_rate": self.risk_manager.get_win_rate(),
                    "open_positions": self.risk_manager.get_open_positions_count(),
                    "total_fees": sum(
                        t.get("total_fees", 0)
                        for t in self.risk_manager.trade_history
                    ),
                    "daily_pnl": self.daily_pnl,
                    "trades_today": self.trades_today,
                },
            }
            with open(SAHAM_STATE_FILE, "w") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            self.logger.warning(f"Write state error: {e}")

    def send_portfolio_report(self):
        """
        Kirim laporan portfolio lengkap ke Telegram setiap cycle (tiap 5 menit).

        Sumber data: scrape langsung halaman home Ajaib (cash + kepemilikan),
        lalu harga real-time per saham dari yfinance untuk hitung nilai.
        Hasil juga disimpan ke _portfolio_cache untuk state file.

        Termasuk estimasi biaya jual dan grand total NET per posisi.
        """
        try:
            self.update_cash_balance()
            cash = self.get_cash_balance()
            portfolio = self.trader.get_portfolio()

            if not portfolio:
                self.logger.warning("Could not fetch portfolio from Ajaib")
                return

            stocks_raw = portfolio.get("stocks", [])
            position_details = {}
            total_stock_value = 0

            for stock_data in stocks_raw:
                try:
                    if isinstance(stock_data, dict):
                        code = stock_data.get("code", "")
                        lots = stock_data.get("lots", 0)
                    elif isinstance(stock_data, str):
                        text_lines = stock_data.strip().split("\n")
                        if len(text_lines) < 2:
                            continue
                        code = text_lines[0].strip()
                        lots = 0
                        for line in text_lines:
                            if "lot" in line.lower():
                                match = __import__('re').search(r'(\d+)\s*lot', line, __import__('re').IGNORECASE)
                                if match:
                                    lots = int(match.group(1))
                    else:
                        continue

                    if lots == 0 or not code:
                        continue

                    symbol = f"{code}.JK"
                    ticker = self.exchange.fetch_ticker(symbol)
                    if not ticker or not ticker.get("last"):
                        continue

                    current_price = ticker["last"]
                    shares = lots * LOT_SIZE
                    value = current_price * shares
                    est_sell_fees = value * SELL_TOTAL_FEE_PCT
                    total_stock_value += value

                    position_details[symbol] = {
                        "code": code,
                        "lots": lots,
                        "shares": shares,
                        "entry_price": current_price,
                        "entry_price_market": current_price,
                        "current_price": current_price,
                        "value": value,
                        "net_pnl": -est_sell_fees,
                        "pnl": -est_sell_fees,
                        "pnl_pct": -(SELL_TOTAL_FEE_PCT * 100),
                        "est_sell_fees": est_sell_fees,
                        "break_even": current_price * (1 + SELL_TOTAL_FEE_PCT),
                    }
                except Exception as e:
                    self.logger.warning(f"Error processing stock data: {e}")

            grand_total = cash + total_stock_value
            self._portfolio_cache = {
                "cash": cash,
                "stocks": [
                    {"code": d["code"], "lots": d["lots"], "price": d["current_price"]}
                    for d in position_details.values()
                ],
                "timestamp": now_jakarta().isoformat(),
            }
            self.telegram.notify_portfolio_detail(cash, position_details, grand_total)

        except Exception as e:
            self.logger.warning(f"Portfolio report error: {e}")

    def run_cycle(self):
        """
        Satu siklus lengkap bot (dipanggil tiap 5 menit dari start()).

        Urutan:
          1. Reset counter harian saat ganti tanggal (00:00 WIB)
          2. Skip jika pasar tutup
          3. Sync saldo kas + posisi dari Ajaib
          4. Scan semua saham -> filter kandidat buy/sell terbaik
          5. Eksekusi aksi untuk tiap kandidat
          6. Log summary + kirim portfolio report ke Telegram
          7. Tulis state file untuk telegram_handler
        """
        self.cycle_count += 1
        now = now_jakarta()

        if now.hour == 0 and now.minute < 20:
            self.daily_pnl = 0
            self.trades_today = 0

        self.logger.info("=" * 65)
        self.logger.info(f"CYCLE #{self.cycle_count} | {format_datetime(now)}")
        self.logger.info("=" * 65)

        if not self.is_market_open():
            self.logger.info("Market is CLOSED. Skipping analysis.")
            # TETAP update portfolio & saldo saat market tutup agar user bisa cek
            self.update_cash_balance()
            self.send_portfolio_report()
            self.write_state_to_file()
            return

        self.update_cash_balance()
        cash = self.get_cash_balance()
        self.logger.info(f"Cash Balance: {cash:,.0f} IDR")
        self.logger.info(f"Scanning {len(ALL_STOCKS)} stocks...")
        self.logger.info("-" * 65)

        try:
            self.risk_manager.sync_positions_from_exchange(self.exchange, self.trader)
        except Exception as e:
            self.logger.warning(f"Sync positions error: {e}")

        all_results = self.scan_all_stocks()
        buy_candidates = self.get_top_candidates(all_results, "buy")
        sell_candidates = self.get_top_candidates(all_results, "sell")

        self.logger.info(f"Found: {len(buy_candidates)} buy, {len(sell_candidates)} sell candidates")

        for analysis in buy_candidates + sell_candidates:
            symbol = analysis["symbol"]
            is_primary = symbol in TRADING_STOCKS
            ohlcv = self.exchange.fetch_ohlcv(symbol, period="90d", interval="1d")
            if ohlcv:
                self.process_stock(symbol, ohlcv=ohlcv, is_primary=is_primary)

        self.logger.info("-" * 65)
        self.notifier.notify_summary(self.risk_manager, cash)
        self.logger.info(f"Today: PnL={self.daily_pnl:+,.0f} IDR | Trades={self.trades_today}")

        try:
            unrealized = self.risk_manager.get_unrealized_pnl(self.exchange)
            total_stock = self.risk_manager.get_total_stock_value(self.exchange)
            grand_total = cash + total_stock
            total_fees_lifetime = sum(t.get("total_fees", 0) for t in self.risk_manager.trade_history)
            self.logger.info(
                f"Unrealized PnL (net): {unrealized:+,.0f} IDR | "
                f"Stock Value: {total_stock:,.0f} IDR | "
                f"Grand Total: {grand_total:,.0f} IDR"
            )
            if total_fees_lifetime > 0:
                self.logger.info(f"Total Biaya Transaksi (lifetime): {total_fees_lifetime:,.0f} IDR")
        except Exception as e:
            self.logger.warning(f"Portfolio calc error: {e}")

        self.send_portfolio_report()
        self.write_state_to_file()

        self.logger.info(f"Uptime: {str(now - self.start_time).split('.')[0]}")
        self.logger.info("-" * 65)

    def _keyboard_listener(self):
        """Thread listener keyboard: tekan 'q' + Enter untuk stop bot dengan aman (cross-platform)."""
        print("\n[BOT RUNNING] Press 'q' + Enter to stop safely\n")
        while self.running:
            try:
                if WINDOWS:
                    if msvcrt.kbhit():
                        key = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                        if key == "q":
                            print("\n[q pressed] Stopping bot...")
                            self.running = False
                            self._stop_event.set()
                            break
                else:
                    import select
                    if select.select([sys.stdin], [], [], 0.5)[0]:
                        key = sys.stdin.read(1).lower()
                        if key == "q":
                            print("\n[q pressed] Stopping bot...")
                            self.running = False
                            self._stop_event.set()
                            break
            except Exception:
                time.sleep(0.5)

    def start(self):
        """
        Main loop bot: jalankan run_cycle() tiap INTERVAL_SECONDS detik
        sampai user stop (q / Ctrl+C / SIGTERM). Kirim notifikasi start
        + portfolio report awal sebelum masuk loop.
        """
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        keyboard_thread.start()

        self.logger.info("=" * 65)
        self.logger.info("SAHAM TRADING BOT STARTED")
        self.logger.info(f"Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Stocks: {', '.join([s.replace('.JK', '') for s in TRADING_STOCKS])}")
        self.logger.info(f"Interval: {INTERVAL_SECONDS}s ({INTERVAL_SECONDS/60:.0f} min)")
        self.logger.info(f"Max Positions: {MAX_OPEN_POSITIONS}")
        self.logger.info(f"Position Size: {POSITION_SIZE_IDR:,.0f} IDR")
        self.logger.info("=" * 65)

        self.telegram.notify_start(TRADING_STOCKS)
        self.send_portfolio_report()
        self.write_state_to_file()

        while self.running:
            try:
                self.run_cycle()
                self.logger.info(f"Next cycle in {INTERVAL_SECONDS}s... (press 'q' + Enter to stop)")
                for _ in range(INTERVAL_SECONDS):
                    if not self.running:
                        break
                    time.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("Interrupted by user")
                self.running = False
            except Exception as e:
                self.notifier.notify_error(f"Cycle error: {str(e)}")
                self.telegram.notify_error(f"Cycle error: {str(e)}")
                self.logger.info("Retry in 60s...")
                time.sleep(60)

        self._shutdown()

    def _signal_handler(self, signum, frame):
        """Handler SIGINT/SIGTERM: set running=False agar loop berhenti dengan rapi."""
        self.logger.info(f"Signal {signum} received")
        self.running = False

    def stop(self):
        """Stop bot dari Telegram command (dipanggil telegram_handler). Exit paksa setelah shutdown."""
        self.running = False
        self.logger.info("Bot stopping via Telegram...")
        self._shutdown()
        os._exit(0)

    def _shutdown(self):
        """
        Shutdown sequence: log statistik akhir, kirim notifikasi stop +
        summary terakhir + portfolio report penutup ke Telegram.
        """
        self.logger.info("=" * 65)
        self.logger.info("BOT STOPPED")
        self.logger.info(f"Total cycles: {self.cycle_count}")
        self.logger.info(f"Total trades: {len(self.risk_manager.trade_history)}")
        self.logger.info(f"Final PnL (net): {self.risk_manager.get_total_pnl():+,.0f} IDR")
        self.logger.info(f"Win rate: {self.risk_manager.get_win_rate()}%")
        self.logger.info("=" * 65)

        self.telegram.notify_stop("User request / Ctrl+C")

        cash = self.get_cash_balance()
        open_pos = self.risk_manager.get_open_positions_count()
        total_pnl = self.risk_manager.get_total_pnl()
        win_rate = self.risk_manager.get_win_rate()
        total_trades = len(self.risk_manager.trade_history)
        total_fees = sum(t.get("total_fees", 0) for t in self.risk_manager.trade_history)
        self.telegram.notify_summary(cash, open_pos, total_pnl, win_rate, total_trades, total_fees)
        self.send_portfolio_report()


def main():
    """Entry point bot saham: setup logger lalu jalankan SahamBot.start()."""
    setup_logger()
    bot = SahamBot()
    bot.start()


if __name__ == "__main__":
    main()
