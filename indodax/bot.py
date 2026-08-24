"""
Production Crypto Trading Bot untuk Indodax

Modul utama yang mengorkestrasi seluruh alur trading otomatis:
1. Scanning seluruh pair koin di Indodax setiap 5 menit (300 detik).
2. Analisis teknikal & AI LLM scoring pada kandidat koin dengan probabilitas tertinggi.
3. Evaluasi manajemen risiko & eksekusi order (Market Buy, Partial TP1, Full TP2, Trailing Stop, DCA).
4. Pemantauan portofolio dan notifikasi real-time via Telegram & logger lokal.
5. Menjalankan listener Telegram command di background thread.
6. Penanganan graceful shutdown saat menerima sinyal SIGINT/SIGTERM atau tombol 'q'.

Author: AI Trading Bot
"""

import time
import logging
import signal
import os
import sys
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    now_jakarta, format_datetime,
    check_ip_change, get_public_ip, load_known_ip, save_known_ip,
)

from config import (
    TRADING_PAIRS, ALL_PAIRS, INTERVAL_SECONDS, CANDLESTICK_TIMEFRAME,
    INDODAX_SYMBOL_MAP, MAX_OPEN_POSITIONS, POSITION_SIZE_USDT,
    MIN_ORDER_IDR, LLM_TOP_PAIRS,
)
from exchange import IndodaxExchange
from analyzer import MarketAnalyzer
from strategy import RiskManager, TradingStrategy
from notifier import setup_logger, TradeNotifier
from telegram_notifier import TelegramNotifier
from telegram_handler import TelegramCommandHandler

try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False


class ProductionBot:
    """
    Bot Trading Kripto Indodax Mode Produksi (Production Engine).
    
    Attributes:
        logger (logging.Logger): Logger instance untuk bot.
        exchange (IndodaxExchange): Wrapper API exchange Indodax.
        analyzer (MarketAnalyzer): Engine analisis teknikal & AI LLM.
        risk_manager (RiskManager): Pengelola batas risiko dan pelacak posisi terbuka.
        strategy (TradingStrategy): Evaluator strategi trading dan aturan eksekusi.
        notifier (TradeNotifier): Pengirim notifikasi console/file log.
        telegram (TelegramNotifier): Pengirim pesan notifikasi ke Telegram.
        telegram_cmd (TelegramCommandHandler): Threaded poller untuk menerima perintah Telegram.
        running (bool): Status apakah bot sedang berjalan.
        cycle_count (int): Penghitung iterasi siklus pemindaian pasar.
        start_time (datetime): Waktu mulai bot berjalan.
        daily_pnl (float): PnL terealisasi hari ini.
        trades_today (int): Jumlah trade yang diselesaikan hari ini.
    """

    def __init__(self):
        """
        Inisialisasi komponen bot produksi Indodax.
        """
        self.logger = logging.getLogger("bot")
        self.exchange = IndodaxExchange()
        self.analyzer = MarketAnalyzer(use_llm=True)
        self.risk_manager = RiskManager()
        self.strategy = TradingStrategy(self.analyzer, self.risk_manager)
        self.notifier = TradeNotifier()
        self.telegram = TelegramNotifier()
        self.running = False
        self.cycle_count = 0
        self.start_time = now_jakarta()
        self.daily_pnl = 0
        self.trades_today = 0
        self._stop_event = threading.Event()
        self.telegram_cmd = TelegramCommandHandler(bot_instance=self)

    def get_balance(self):
        """
        Mengambil saldo IDR bebas yang siap dipakai bertransaksi.
        
        Returns:
            float: Saldo Rupiah tersedia.
        """
        return self.exchange.get_idr_balance()

    def execute_buy(self, symbol, amount, current_price):
        """
        Mengeksekusi order Market Buy di Indodax dan mencatat posisi baru ke RiskManager.
        
        Args:
            symbol (str): Simbol pair (misal 'BTC/IDR').
            amount (float): Jumlah koin yang dibeli.
            current_price (float): Harga koin saat order dibuat.
            
        Returns:
            bool: True jika order berhasil dikirim dan dieksekusi, False jika gagal.
        """
        pair = INDODAX_SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        quote_qty = int(amount * current_price)
        order = self.exchange.create_order(
            symbol=pair,
            side="BUY",
            order_type="MARKET",
            quote_order_qty=quote_qty,
        )
        if order and not order.get("error"):
            qty = float(order.get("origQty", 0))
            if qty == 0:
                qty = amount
            self.risk_manager.add_position(symbol, current_price, qty)
            self.notifier.notify_trade(symbol, "BUY", current_price, qty)
            self.telegram.notify_trade(symbol, "BUY", current_price, qty)
            self.trades_today += 1
            return True
        self.logger.error(f"Buy failed: {order}")
        return False

    def execute_sell(self, symbol, current_price):
        """
        Mengeksekusi order Market Sell penuh untuk menutup seluruh posisi koin terbuka.
        
        Args:
            symbol (str): Simbol pair (misal 'BTC/IDR').
            current_price (float): Harga pasar saat ini.
            
        Returns:
            bool: True jika eksekusi jual berhasil, False jika gagal.
        """
        if symbol in self.risk_manager.positions:
            pos = self.risk_manager.positions[symbol]
            pair = INDODAX_SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
            order = self.exchange.create_order(
                symbol=pair,
                side="SELL",
                order_type="MARKET",
                quantity=pos.amount,
            )
            if order and not order.get("error"):
                exit_price = current_price
                trade_record = self.risk_manager.close_position(symbol, exit_price)
                if trade_record:
                    self.notifier.notify_trade(
                        symbol, "SELL", exit_price,
                        pnl=trade_record["pnl_amount"]
                    )
                    self.telegram.notify_trade(
                        symbol, "SELL", exit_price,
                        pnl=trade_record["pnl_amount"]
                    )
                    self.daily_pnl += trade_record["pnl_amount"]
                    self.trades_today += 1
                return True
            self.logger.error(f"Sell failed: {order}")
        return False

    def execute_sell_partial(self, symbol, current_price, amount):
        """
        Mengeksekusi order Market Sell sebagian (misal 50% kuantitas pada TP1).
        
        Args:
            symbol (str): Simbol pair.
            current_price (float): Harga pasar saat ini.
            amount (float): Kuantitas koin yang dilepas.
            
        Returns:
            bool: True jika order parsial berhasil, False jika gagal.
        """
        pair = INDODAX_SYMBOL_MAP.get(symbol, symbol.replace("/", ""))
        order = self.exchange.create_order(
            symbol=pair,
            side="SELL",
            order_type="MARKET",
            quantity=amount,
        )
        if order and not order.get("error"):
            pnl = (current_price - self.risk_manager.positions[symbol].entry_price) * amount
            self.notifier.notify_trade(symbol, "PARTIAL SELL", current_price, amount, pnl)
            self.telegram.notify_trade(symbol, "PARTIAL SELL", current_price, amount, pnl)
            self.daily_pnl += pnl
            self.trades_today += 1
            return True
        self.logger.error(f"Partial sell failed: {order}")
        return False

    def scan_all_pairs(self):
        """
        Memindai seluruh pasangan koin di ALL_PAIRS dan menghitung indikator teknikal awal (Fast Scan).
        
        Returns:
            list: Daftar hasil analisis teknikal dari seluruh pair yang berhasil dipindai.
        """
        results = []
        for symbol in ALL_PAIRS:
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100
                )
                if not ohlcv or len(ohlcv) < 50:
                    continue

                ticker = self.exchange.fetch_ticker(symbol)
                if not ticker:
                    continue

                analysis = self.analyzer.analyze_technical(ohlcv, symbol=symbol)
                analysis["symbol"] = symbol
                analysis["current_price"] = ticker["last"]
                results.append(analysis)
            except Exception as e:
                self.logger.warning(f"[{symbol}] Scan error: {e}")
            time.sleep(0.5)
        return results

    def get_top_candidates(self, results, signal_type="buy"):
        """
        Menyaring dan memilih koin dengan skor confidence tertinggi sesuai tipe sinyal.
        
        Args:
            results (list): Hasil pemindaian awal seluruh pair.
            signal_type (str, optional): Tipe sinyal yang dicari ('buy' atau 'sell'). Default 'buy'.
            
        Returns:
            list: Maksimal LLM_TOP_PAIRS kandidat terbaik untuk dianalisis lebih lanjut dengan AI LLM.
        """
        filtered = [r for r in results if r["signal"] == signal_type and r["confidence"] > 0.55]
        filtered.sort(key=lambda x: x["confidence"], reverse=True)
        return filtered[:LLM_TOP_PAIRS]

    def analyze_with_llm(self, candidates):
        """
        Melakukan deep analysis dengan AI LLM untuk daftar kandidat koin terpilih.
        
        Args:
            candidates (list): Daftar koin hasil seleksi teknikal awal.
            
        Returns:
            list: Daftar hasil analisis lengkap yang sudah digabung dengan scoring LLM.
        """
        analyzed = []
        for c in candidates:
            try:
                symbol = c["symbol"]
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100)
                if not ohlcv:
                    continue
                ticker = self.exchange.fetch_ticker(symbol)
                if not ticker:
                    continue
                analysis = self.analyzer.analyze(ohlcv, symbol=symbol)
                analysis["symbol"] = symbol
                analysis["current_price"] = ticker["last"]
                analyzed.append(analysis)
            except Exception as e:
                self.logger.warning(f"[{symbol}] LLM analysis error: {e}")
            time.sleep(1.5)
        return analyzed

    def process_pair(self, symbol, ohlcv=None, is_primary=True):
        """
        Memproses satu pair koin: evaluasi strategi, kirim notifikasi sinyal, dan eksekusi order jika valid.
        
        Args:
            symbol (str): Simbol pair koin.
            ohlcv (list, optional): Data candlestick jika sudah di-cache sebelumnya.
            is_primary (bool, optional): Apakah koin termasuk pair prioritas utama.
        """
        try:
            if ohlcv is None:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100
                )
            if not ohlcv or len(ohlcv) < 50:
                self.logger.warning(f"[{symbol}] Insufficient data")
                return

            ticker = self.exchange.fetch_ticker(symbol)
            if not ticker:
                self.logger.warning(f"[{symbol}] Ticker failed")
                return

            current_price = ticker["last"]
            balance = self.get_balance()

            if balance <= 0:
                self.logger.warning(f"[{symbol}] No balance")
                return

            decision = self.strategy.evaluate(symbol, ohlcv, balance, current_price, is_primary=is_primary)
            action = decision["action"]
            analysis = decision["analysis"]

            self.notifier.notify_signal(
                symbol, analysis["signal"], analysis["confidence"],
                analysis["indicators"], analysis.get("llm")
            )

            if action == "buy":
                amount = decision["amount"]
                if amount == 0:
                    self.logger.warning(
                        f"[{symbol}] Balance terlalu kecil (min {MIN_ORDER_IDR:,} IDR)"
                    )
                    return
                est_cost = amount * current_price
                if est_cost > balance:
                    self.logger.warning(f"[{symbol}] Need {est_cost:,.0f}, have {balance:,.0f}")
                    return
                self.execute_buy(symbol, amount, current_price)

            elif action == "partial_sell":
                amount = decision["amount"]
                reason = decision.get("reason", "tp1_hit")
                self.logger.info(f"[{symbol}] Partial sell: {reason}")
                self.execute_sell_partial(symbol, current_price, amount)

            elif action == "close":
                reason = decision.get("reason", "signal")
                self.logger.info(f"[{symbol}] Close: {reason}")
                self.execute_sell(symbol, current_price)

        except Exception as e:
            self.notifier.notify_error(f"[{symbol}] {str(e)}")
            self.telegram.notify_error(f"[{symbol}] {str(e)}")

    def health_check(self):
        """
        Pemeriksaan kesehatan sistem bot (ketersediaan saldo dan konektivitas API).
        
        Returns:
            dict: Status kesehatan akun (saldo IDR, dll).
        """
        balance = self.get_balance()
        return {"balance": balance}

    def run_cycle(self):
        """
        Menjalankan satu putaran siklus trading lengkap:
        1. Reset metrik harian jika masuk hari baru (pukul 00:00 WIB).
        2. Health check saldo dan logging status siklus.
        3. Sinkronisasi posisi terbuka dengan exchange.
        4. Pemindaian seluruh pair (Fast Scan) dan pemeringkatan top kandidat.
        5. Deep analysis LLM untuk kandidat terbaik.
        6. Eksekusi keputusan trading per koin terpilih.
        7. Pengecekan rebalancing jika kas IDR menipis.
        8. Notifikasi ringkasan status portofolio.
        """
        self.cycle_count += 1
        now = now_jakarta()

        if now.hour == 0 and now.minute < 20:
            self.daily_pnl = 0
            self.trades_today = 0

        # Cek perubahan IP publik (setiap cycle)
        ip_changed, old_ip, new_ip = check_ip_change()
        if ip_changed:
            msg = (
                f"<b>⚠️ IP BERUBAH!</b>\n"
                f"Old: {old_ip}\n"
                f"New: {new_ip}\n\n"
                f"Update registered IP di Indodax API!"
            )
            self.logger.warning(msg)
            self.telegram.send(msg)

        self.logger.info("=" * 65)
        self.logger.info(f"CYCLE #{self.cycle_count} | {format_datetime(now)}")
        self.logger.info("=" * 65)

        health = self.health_check()
        self.logger.info(f"Balance: {health['balance']:,.2f} IDR")
        self.logger.info(f"Scanning {len(ALL_PAIRS)} pairs...")
        self.logger.info("-" * 65)

        self.strategy.risk_manager.sync_positions_from_exchange(self.exchange)

        all_results = self.scan_all_pairs()
        buy_candidates = self.get_top_candidates(all_results, "buy")
        sell_candidates = self.get_top_candidates(all_results, "sell")

        self.logger.info(f"Found: {len(buy_candidates)} buy, {len(sell_candidates)} sell candidates")

        llm_analyzed = self.analyze_with_llm(buy_candidates + sell_candidates)

        for analysis in llm_analyzed:
            symbol = analysis["symbol"]
            current_price = analysis["current_price"]
            is_primary = symbol in TRADING_PAIRS
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100)
            if ohlcv:
                self.process_pair(symbol, ohlcv=ohlcv, is_primary=is_primary)

        balance = self.get_balance()
        min_order = MIN_ORDER_IDR * 1.5
        if balance < min_order:
            self.logger.info(f"Balance {balance:,.0f} < {min_order:,.0f} IDR, checking rebalance...")
            rebalance_candidates = self.strategy.find_rebalance_sell_candidates(all_results, balance)
            for candidate in rebalance_candidates:
                symbol = candidate["symbol"]
                self.logger.info(f"Rebalance: selling {symbol} to get IDR")
                ticker = self.exchange.fetch_ticker(symbol)
                if ticker:
                    self.execute_sell(symbol, ticker["last"])
                time.sleep(2)

        self.logger.info("-" * 65)
        self.notifier.notify_summary(self.risk_manager)
        self.logger.info(f"Today: PnL={self.daily_pnl:+,.0f} IDR | Trades={self.trades_today}")

        try:
            unrealized = self.risk_manager.get_unrealized_pnl(self.exchange)
            total_portfolio = self.risk_manager.get_total_portfolio_value(self.exchange, balance)
            self.logger.info(f"Unrealized PnL: {unrealized:+,.0f} IDR | Portfolio: {total_portfolio:,.0f} IDR")
        except Exception as e:
            self.logger.warning(f"Portfolio calc error: {e}")

        self.logger.info(f"Uptime: {str(now - self.start_time).split('.')[0]}")
        self.logger.info("-" * 65)

    def _keyboard_listener(self):
        """
        Background listener thread untuk membaca penekanan tombol keyboard 'q' untuk graceful stop.
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
        Memulai eksekusi bot trading (lifecycle main runner loop).
        """
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        keyboard_thread = threading.Thread(target=self._keyboard_listener, daemon=True)
        keyboard_thread.start()

        self.logger.info("=" * 65)
        self.logger.info("PRODUCTION TRADING BOT STARTED")
        self.logger.info(f"Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Pairs: {', '.join(TRADING_PAIRS)}")
        self.logger.info(f"Timeframe: {CANDLESTICK_TIMEFRAME}")
        self.logger.info(f"Interval: {INTERVAL_SECONDS}s ({INTERVAL_SECONDS/60:.0f} min)")
        self.logger.info(f"Max Positions: {MAX_OPEN_POSITIONS}")
        self.logger.info(f"Position Size: {POSITION_SIZE_USDT:,} IDR")
        self.logger.info("=" * 65)

        self.telegram.notify_start(TRADING_PAIRS, CANDLESTICK_TIMEFRAME)
        self.telegram_cmd.start()

        # Cek IP publik saat startup
        changed, old_ip, new_ip = check_ip_change()
        if new_ip:
            self.logger.info(f"Public IP: {new_ip}")
        if changed:
            msg = (
                f"<b>⚠️ IP BERUBAH!</b>\n"
                f"Old: {old_ip}\n"
                f"New: {new_ip}\n\n"
                f"Update registered IP di Indodax API!"
            )
            self.logger.warning(msg)
            self.telegram.send(msg)

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
        Menangkap sinyal OS termination (SIGINT / SIGTERM) untuk graceful shutdown.
        """
        self.logger.info(f"Signal {signum} received")
        self.running = False

    def stop(self):
        """
        Menghentikan bot secara terprogram (misal via Telegram command /stop-indodax).
        """
        self.running = False
        self.logger.info("Bot stopping via Telegram...")
        self._shutdown()
        os._exit(0)

    def _shutdown(self):
        """
        Melakukan prosedur pembersihan dan pelaporan akhir saat bot dimatikan.
        """
        self.logger.info("=" * 65)
        self.logger.info("BOT STOPPED")
        self.logger.info(f"Total cycles: {self.cycle_count}")
        self.logger.info(f"Total trades: {len(self.risk_manager.trade_history)}")
        self.logger.info(f"Final PnL: {self.risk_manager.get_total_pnl():+,.2f} IDR")
        self.logger.info(f"Win rate: {self.risk_manager.get_win_rate()}%")
        self.logger.info("=" * 65)

        self.telegram.notify_stop("User request / Ctrl+C")

        balance = self.get_balance()
        open_pos = self.risk_manager.get_open_positions_count()
        total_pnl = self.risk_manager.get_total_pnl()
        win_rate = self.risk_manager.get_win_rate()
        total_trades = len(self.risk_manager.trade_history)
        self.telegram.notify_summary(balance, open_pos, total_pnl, win_rate, total_trades)


def main():
    """
    Fungsi entri utama program bot Indodax.
    """
    setup_logger()
    bot = ProductionBot()
    bot.start()


if __name__ == "__main__":
    main()

