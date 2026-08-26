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
        # Portfolio cache TTL - scrape Ajaib max 1x per jam (kurangi fingerprint)
        self._portfolio_ttl = 3600
        self._portfolio_fetched_at = 0
        self._cached_portfolio = None
        self._session_expired_notified = False


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
        """
        Alias kompatibilitas untuk get_cash_balance().

        Dulunya melakukan scrape langsung; kini hanya mengembalikan
        cache agar hemat sesi browser. Gunakan get_cached_portfolio()
        jika butuh data fresh.
        """
        self.get_cached_portfolio()

    def get_cached_portfolio(self):
        """
        Ambil portfolio dari Ajaib dengan cache TTL 1 jam.

        Mengurangi frekuensi buka browser baru (fingerprint) yang bisa
        memicu Ajaib invalidate session.

        Returns:
            dict | None: Portfolio data, atau None jika session expired.
        """
        import time as _time
        now = _time.time()
        if self._cached_portfolio is not None and (now - self._portfolio_fetched_at) < self._portfolio_ttl:
            return self._cached_portfolio

        portfolio = self.trader.get_portfolio()
        self._portfolio_fetched_at = now

        if portfolio:
            self._cached_portfolio = portfolio
            if portfolio.get("cash") is not None:
                self._last_cash = portfolio["cash"]
            # Session hidup lagi - reset flag notifikasi
            if self._session_expired_notified:
                self._session_expired_notified = False
                self.telegram.send("Session Ajaib aktif kembali.")
        else:
            # None = session expired / Cloudflare -> coba auto-login dulu (headed Chrome + NIK)
            tried = False
            try:
                import asyncio
                if hasattr(self.trader, '_try_auto_login'):
                    # _try_auto_login is async, but get_cached_portfolio is sync - schedule best-effort
                    # Jalankan auto-login sync via subprocess langsung (DISPLAY=:99 sudah di-handle di trader)
                    import subprocess as _sp, pathlib as _pl, os as _os
                    target = _pl.Path.home() / "trading-bot" / "ajaib" / "src" / "auto-login.js"
                    env2 = _os.environ.copy()
                    env2["DISPLAY"] = env2.get("DISPLAY") or ":99"
                    try:
                        # pastikan Xvfb
                        _sp.run(["sh","-c","pgrep Xvfb >/dev/null || (Xvfb :99 -screen 0 1366x768x24 >/tmp/xvfb.log 2>&1 & sleep 2)"], timeout=8)
                    except Exception:
                        pass
                    pr = _sp.run(["node", str(target)], capture_output=True, text=True, timeout=180, env=env2)
                    tried = True
                    self.logger.warning(f"Auto-login attempt after expired: exit {pr.returncode}")
                    if pr.returncode == 0:
                        # retry get_portfolio sekali
                        retry = self.trader.get_portfolio()
                        if retry and retry.get("cash") is not None:
                            self._cached_portfolio = retry
                            self._last_cash = retry["cash"]
                            self._portfolio_fetched_at = now
                            self._session_expired_notified = False
                            self.logger.info(f"Auto-login retry OK: cash={retry['cash']}")
                            self.telegram.send(f"Session Ajaib dipulihkan otomatis. Cash: Rp{retry['cash']:,}")
                            return self._cached_portfolio
            except Exception as e:
                self.logger.warning(f"Auto-login retry error: {e}")
            if not self._session_expired_notified:
                self._session_expired_notified = True
                self.logger.warning("Session Ajaib expired - auto-login gagal, notifikasi dikirim")
                self.telegram.send(
                    "<b>Session Ajaib perlu login ulang</b>\n"
                    "Bot sudah coba login otomatis tapi belum berhasil.\n"
                    "Akan dicoba lagi otomatis 30 menit lagi."
                )

        # Return cache lama (stale) daripada None supaya bot tetap punya data
        return self._cached_portfolio

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
                analysis["ohlcv"] = ohlcv  # keep for process_stock reuse
                results.append(analysis)
            except Exception as e:
                self.logger.warning(f"[{symbol}] Scan error: {e}")
            time.sleep(0.2)
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
                # coba fallback portfolio.json sekali, jangan spam per-saham
                try:
                    import json as _js2, pathlib as _pl2
                    pf2 = _pl2.Path(__file__).parent.parent / "ajaib" / "session" / "portfolio.json"
                    if not pf2.exists():
                        pf2 = _pl2.Path.home() / "trading-bot" / "ajaib" / "session" / "portfolio.json"
                    if pf2.exists():
                        cash = int(_js2.loads(pf2.read_text(encoding="utf-8")).get("cash",0) or 0)
                        if cash>0:
                            self._last_cash = cash
                except Exception:
                    pass
            if cash <= 0:
                # diam saja, sudah di-handle di cycle level
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
            # Pakai cache TTL 1 jam supaya tidak buka browser baru tiap cycle
            # (session expired -> notifikasi sudah dikirim oleh get_cached_portfolio)
            portfolio = self.get_cached_portfolio()

            if not portfolio:
                self.logger.warning("Could not fetch portfolio (session expired?) - pertahankan portfolio lama, coba auto-login next cycle")
            # Jangan timpa portfolio.json dengan 0; biarkan file lama tetap (PADI tetap kebaca)
                return

            cash = self.get_cash_balance()

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
            # Keep-alive ringan tiap ~4 jam + jitter biar tidak konsisten (native), hindari idle 17-18 jam -> expired
            import random, time as _time
            now_ts = _time.time()
            last = getattr(self, "_last_keepalive_ts", 0)
            # jitter 3.0 - 4.5 jam (10800 - 16200 detik)
            interval = getattr(self, "_keepalive_interval", 0)
            if interval == 0 or now_ts - last >= interval:
                # tentukan next interval random
                self._keepalive_interval = random.uniform(10800, 16200)  # 3 - 4.5 jam
                self._last_keepalive_ts = now_ts
                # jam pre-market 08:40 selalu paksa keep-alive juga (cek sebelum buka 09:00)
                force_premarket = (now.hour == 8 and now.minute >= 40 and now.minute < 60)
                if force_premarket or last == 0 or now_ts - last >= interval:
                    self.logger.info(f"Keep-alive ping (next ~{self._keepalive_interval/3600:.1f}h, jitter 3-4.5h)...")
                    try:
                        import asyncio
                        # reuse trader fingerprint (Win32 1366x768 8/16GB) - ringan cuma GET /home
                        res = asyncio.run(self.trader.get_portfolio_async())
                        if res and res.get("cash") is not None:
                            self.logger.info(f"Keep-alive OK: cash={res.get('cash'):,.0f}")
                        else:
                            self.logger.warning("Keep-alive: Session expired? portfolio=None")
                            # alert pre-market 08:40
                            if force_premarket:
                                try:
                                    self.notifier.send_message("⚠️ <b>Ajaib</b>\nSesi expired sebelum buka (08:40). Mohon login manual Chrome lalu kirim storage-state.json")
                                except: pass
                    except Exception as e:
                        self.logger.warning(f"Keep-alive error: {e}")
                        if force_premarket:
                            try:
                                self.notifier.send_message(f"⚠️ <b>Ajaib</b> Keep-alive gagal 08:40: {str(e)[:120]}")
                            except: pass
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
            ohlcv = analysis.get("ohlcv") or self.exchange.fetch_ohlcv(symbol, period="90d", interval="1d")
            if ohlcv:
                self.process_stock(symbol, ohlcv=ohlcv, is_primary=is_primary)

        # Jika tidak ada buy tereksekusi di cycle ini, jelaskan kenapa (biar user tidak kira error/sesi habis)
        if cash < 200000 and len(buy_candidates) == 0:
            # tidak ada buy candidate sama sekali
            try:
                self._send_no_buy_explanation(cash, all_results, buy_candidates, sell_candidates)
            except: pass
        elif cash < 200000:
            # ada buy tapi tidak ada yang affordable / semua ke-filter
            affordable_now = any(
                r.get("price",0) and r["price"]*100*1.001513 <= cash and r.get("confidence",0)>=0.70 and (r.get("indicators",{}).get("rsi",0) or 0) <=65 and r.get("signal")=="buy"
                for r in all_results
            )
            if not affordable_now:
                try:
                    self._send_no_buy_explanation(cash, all_results, buy_candidates, sell_candidates)
                except: pass

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

    def _send_no_buy_explanation(self, cash, all_results, buy_candidates, sell_candidates):
        """Kirim ringkasan Telegram yang gampang dipahami saat tidak ada pembelian.""" 
        # Fallback: jika cash 0 karena session expired, baca portfolio.json agar tidak lapor Rp0 salah
        if cash == 0:
            try:
                import json as _js, pathlib as _pl
                pf = _pl.Path(__file__).parent.parent / "ajaib" / "session" / "portfolio.json"
                if not pf.exists():
                    pf = _pl.Path.home() / "trading-bot" / "ajaib" / "session" / "portfolio.json"
                if pf.exists():
                    d = _js.loads(pf.read_text(encoding="utf-8"))
                    cash = int(d.get("cash", 0) or 0)
                    if cash > 0:
                        self._last_cash = cash
                        self.logger.info(f"No-buy fallback cash from portfolio.json: {cash}")
            except Exception as e:
                self.logger.warning(f"No-buy fallback error: {e}")
            if cash == 0:
                self.logger.warning("No-buy skip: cash still 0 after fallback - jangan spam Rp0")
                return
        try:
            insufficient = []
            rsi_block = []
            low_conf = []
            for r in all_results:
                sig = r.get("signal", "hold")
                conf = r.get("confidence", 0)
                rsi = r.get("indicators", {}).get("rsi", 0) or r.get("rsi", 0)
                sym = r.get("symbol", "")
                price = r.get("price", 0)
                if not price:
                    try:
                        price = self.exchange.fetch_ticker(sym).get("last") or 0
                    except: price = 0
                lot_cost = int(price * 100 * 1.001513) if price else 0
                if sig == "buy":
                    if conf < 0.70:
                        low_conf.append(f"{sym.replace('.JK','')} ({conf:.0%})")
                    elif rsi and rsi > 65:
                        rsi_block.append(f"{sym.replace('.JK','')} (RSI {rsi:.0f})")
                    elif lot_cost > cash:
                        insufficient.append(f"{sym.replace('.JK','')} Rp{price:,.0f} — butuh Rp{lot_cost:,.0f} per lot")
            lines = []
            lines.append(f"⏸ <b>Saham Ajaib — {self._now_str()}</b>")
            lines.append(f"Tidak ada pembelian dulu ya.")
            lines.append(f"")
            max_price = int(cash / 100 / 1.001513)
            lines.append(f"💰 Uang kamu: Rp{cash:,.0f} (1 lot = 100 lembar)")
            lines.append(f"   Hanya saham di bawah Rp{max_price:,} yang cukup — contoh: KLBF Rp800")
            lines.append(f"")
            lines.append(f"🔍 Dicek {len(all_results)} saham: {len(buy_candidates)} mau naik, {len(sell_candidates)} mau turun")
            lines.append(f"")
            lines.append(f"Kenapa tidak beli:")
            if insufficient:
                lines.append(f"• Uang belum cukup ({len(insufficient)} saham): " + ", ".join(insufficient[:3]) + (" ..." if len(insufficient)>3 else ""))
                lines.append(f"  → harganya 269-313 ribu per lot, jadi belum kebeli")
            if rsi_block:
                lines.append(f"• Sudah kemahalan ({len(rsi_block)} saham): " + ", ".join(rsi_block[:3]))
                lines.append(f"  → ditahan dulu biar tidak beli di pucuk")
            if low_conf:
                lines.append(f"• Sinyalnya masih ragu ({len(low_conf)} saham): " + ", ".join(low_conf[:3]))
            if not insufficient and not rsi_block and not low_conf:
                lines.append(f"• Sinyal beli belum kuat, semua masih wait & see")
            lines.append(f"")
            lines.append(f"✨ Bot jalan normal dan sesi aman. Nanti dicek lagi 30 menit lagi ya.")
            msg = "\n".join(lines)
            self.telegram.send(msg)
        except Exception as e:
            self.logger.warning(f"No-buy explain error: {e}")


    def _now_str(self):
        from datetime import datetime
        from config import TZ_JAKARTA
        return datetime.now(TZ_JAKARTA).strftime("%H:%M WIB")

    def _keyboard_listener(self):
        """
        Thread listener keyboard: tekan 'q' + Enter untuk menghentikan bot dengan aman.

        Berjalan di thread terpisah agar tidak memblokir main loop.
        Hanya aktif di Windows (msvcrt).
        """
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
        """
        Handler sinyal SIGINT/SIGTERM: set running=False agar loop berhenti dengan rapi.

        Args:
            signum (int): Nomor sinyal yang diterima.
            frame: Frame eksekusi saat sinyal diterima.

        """
        self.running = False

    def stop(self):
        """
        Menghentikan bot dari perintah Telegram (dipanggil telegram_handler).

        Mengatur flag running=False lalu memaksa exit proses.
        """
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
    """
    Entry point bot saham: setup logger lalu jalankan SahamBot.start().

    Dipanggil saat file dijalankan langsung (python bot.py).
    """
    setup_logger()
    bot = SahamBot()
    bot.start()


if __name__ == "__main__":
    main()
