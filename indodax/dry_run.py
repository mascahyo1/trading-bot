"""
Simulator Trading Bot Crypto Indodax (Dry Run Mode)

Menjalankan bot dalam mode simulasi (paper trading) tanpa melakukan transaksi nyata di exchange:
- Menggunakan saldo virtual awal (default Rp 10.000.000 IDR).
- Mengambil data pasar real-time dari Indodax (candlestick OHLCV dan ticker harga).
- Mensimulasikan biaya transaksi (fee 0.3%) pada setiap pembelian dan penjualan virtual.
- Menghitung performa simulasi (Win Rate, Total Return %, Floating Portfolio Value).

Author: AI Trading Bot
"""

import logging
import time
from datetime import datetime

from config import TRADING_PAIRS, INTERVAL_SECONDS, CANDLESTICK_TIMEFRAME, INDODAX_SYMBOL_MAP
from exchange import IndodaxExchange
from analyzer import MarketAnalyzer
from strategy import RiskManager, TradingStrategy
from notifier import setup_logger, TradeNotifier


class DryRunTradingBot:
    """
    Simulator Bot Trading Kripto Indodax (Paper Trading).
    
    Attributes:
        logger (logging.Logger): Logger instance dryrun.
        exchange (IndodaxExchange): Wrapper API exchange untuk data pasar real-time.
        analyzer (MarketAnalyzer): Engine analisis pasar teknikal.
        risk_manager (RiskManager): Pengelola portofolio dan riwayat simulasi.
        strategy (TradingStrategy): Evaluator strategi trading.
        notifier (TradeNotifier): Pengirim notifikasi log.
        simulated_balance (float): Saldo kas virtual saat ini.
        initial_balance (float): Saldo kas virtual awal untuk benchmark return.
        cycle_count (int): Penghitung siklus simulasi.
        running (bool): Status operasional bot.
    """

    def __init__(self, initial_balance=10_000_000):
        """
        Inisialisasi bot simulator dry run.
        
        Args:
            initial_balance (float, optional): Modal awal virtual dalam Rupiah. Default 10.000.000 IDR.
        """
        self.logger = logging.getLogger("dryrun")
        self.exchange = IndodaxExchange()
        self.analyzer = MarketAnalyzer()
        self.risk_manager = RiskManager()
        self.strategy = TradingStrategy(self.analyzer, self.risk_manager)
        self.notifier = TradeNotifier()
        self.running = False
        self.cycle_count = 0
        self.simulated_balance = initial_balance
        self.initial_balance = initial_balance

    def execute_buy(self, symbol, amount, current_price):
        """
        Mensimulasikan pembelian koin dengan memotong saldo kas virtual dan memperhitungkan fee 0.3%.
        
        Args:
            symbol (str): Simbol pair.
            amount (float): Kuantitas koin yang dibeli.
            current_price (float): Harga koin saat eksekusi.
            
        Returns:
            bool: True jika saldo mencukupi dan order tercatat, False jika tidak.
        """
        cost = amount * current_price
        if cost > self.simulated_balance:
            self.logger.warning(f"[{symbol}] Insufficient simulated balance")
            return False

        fee = cost * 0.003  # Estimasi fee transaksi 0.3%
        self.simulated_balance -= (cost + fee)
        self.risk_manager.add_position(symbol, current_price, amount)
        self.notifier.notify_trade(symbol, "BUY (DRY RUN)", current_price, amount)
        return True

    def execute_sell(self, symbol, current_price):
        """
        Mensimulasikan penjualan koin, menambah saldo kas virtual setelah dipotong fee 0.3%, dan menghitung PnL.
        
        Args:
            symbol (str): Simbol pair.
            current_price (float): Harga koin saat penutupan.
            
        Returns:
            bool: True jika posisi berhasil ditutup, False jika tidak ditemukan.
        """
        if symbol in self.risk_manager.positions:
            pos = self.risk_manager.positions[symbol]
            revenue = pos.amount * current_price
            fee = revenue * 0.003  # Potongan fee 0.3%
            self.simulated_balance += (revenue - fee)
            trade_record = self.risk_manager.close_position(symbol, current_price)
            if trade_record:
                self.notifier.notify_trade(
                    symbol, "SELL (DRY RUN)", current_price,
                    pnl=trade_record["pnl_amount"]
                )
            return True
        return False

    def process_pair(self, symbol):
        """
        Memproses satu pair koin dalam simulasi: fetch market data, evaluasi sinyal, dan jalankan aksi virtual.
        
        Args:
            symbol (str): Simbol pair koin.
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100)
            if not ohlcv or len(ohlcv) < 50:
                return

            ticker = self.exchange.fetch_ticker(symbol)
            if not ticker:
                return

            current_price = ticker["last"]

            decision = self.strategy.evaluate(symbol, ohlcv, self.simulated_balance, current_price)
            action = decision["action"]
            analysis = decision["analysis"]

            self.notifier.notify_signal(
                symbol, analysis["signal"], analysis["confidence"],
                analysis["indicators"], analysis.get("llm")
            )

            if action == "buy":
                amount = decision["amount"]
                self.execute_buy(symbol, amount, current_price)
            elif action == "close":
                self.execute_sell(symbol, current_price)

        except Exception as e:
            self.notifier.notify_error(f"[{symbol}] {str(e)}")

    def run_cycle(self):
        """
        Menjalankan satu iterasi siklus simulasi dan mencetak ringkasan portofolio virtual.
        """
        self.cycle_count += 1
        self.logger.info(f"{'='*60}")
        self.logger.info(f"DRY RUN CYCLE #{self.cycle_count} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Simulated Balance: {self.simulated_balance:,.2f} IDR")

        for symbol in TRADING_PAIRS:
            self.process_pair(symbol)
            time.sleep(1)

        total_pnl = self.risk_manager.get_total_pnl()
        win_rate = self.risk_manager.get_win_rate()
        open_count = self.risk_manager.get_open_positions_count()
        total_trades = len(self.risk_manager.trade_history)
        portfolio_value = self.simulated_balance
        for sym, pos in self.risk_manager.positions.items():
            if pos.status == "open":
                ticker = self.exchange.fetch_ticker(sym)
                if ticker:
                    portfolio_value += pos.amount * ticker["last"]

        total_return = ((portfolio_value - self.initial_balance) / self.initial_balance) * 100

        self.logger.info(
            f"DRY RUN SUMMARY: Open={open_count} | Trades={total_trades} | "
            f"Win Rate={win_rate}% | PnL={total_pnl:+.2f} IDR | "
            f"Portfolio={portfolio_value:,.2f} IDR ({total_return:+.2f}%)"
        )

    def start(self):
        """
        Memulai runner loop simulasi trading dry run.
        """
        self.running = True
        self.logger.info("=" * 60)
        self.logger.info("DRY RUN TRADING BOT STARTED (NO REAL TRADES)")
        self.logger.info(f"Initial Balance: {self.initial_balance:,.2f} IDR")
        self.logger.info(f"Pairs: {', '.join(TRADING_PAIRS)}")
        self.logger.info(f"Interval: {INTERVAL_SECONDS}s | Timeframe: {CANDLESTICK_TIMEFRAME}")
        self.logger.info("=" * 60)

        while self.running:
            try:
                self.run_cycle()
                self.logger.info(f"Next cycle in {INTERVAL_SECONDS}s...")
                time.sleep(INTERVAL_SECONDS)
            except KeyboardInterrupt:
                self.logger.info("Bot stopped by user")
                self.running = False
            except Exception as e:
                self.notifier.notify_error(f"Main loop error: {str(e)}")
                time.sleep(30)


def main():
    """
    Fungsi entri utama eksekusi dry run simulator.
    """
    setup_logger()
    bot = DryRunTradingBot(initial_balance=10_000_000)
    bot.start()


if __name__ == "__main__":
    main()

