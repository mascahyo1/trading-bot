"""
Skrip Eksekusi Tunggal Analisis Pasar Crypto Indodax (Single Run Mode)

Menjalankan satu putaran analisis pasar instan tanpa loop continuous:
- Mengambil candlestick & harga ticker real-time untuk koin utama (BTC, ETH, SOL).
- Menjalankan analisis hybrid (Multi-Indikator Teknikal + AI LLM Sentiment).
- Menghasilkan rekomendasi sinyal trading (BUY, SELL, HOLD) beserta estimasi biaya dan ukuran order.
- Berguna untuk pengujian cepat atau integrasi dengan cron scheduler eksternal.

Author: AI Trading Bot
"""

import sys
import logging
from datetime import datetime

from config import TRADING_PAIRS, CANDLESTICK_TIMEFRAME, INDODAX_SYMBOL_MAP
from exchange import IndodaxExchange
from analyzer import MarketAnalyzer
from strategy import RiskManager, TradingStrategy
from notifier import setup_logger, TradeNotifier


class SingleRunBot:
    """
    Bot Penguji Analisis Pasar untuk Satu Putaran Eksekusi (Single-Shot Runner).
    
    Attributes:
        logger (logging.Logger): Logger bot.
        exchange (IndodaxExchange): Klien exchange Indodax.
        analyzer (MarketAnalyzer): Engine analisis teknikal & AI LLM.
        risk_manager (RiskManager): Pengelola risiko.
        strategy (TradingStrategy): Evaluator strategi trading.
        notifier (TradeNotifier): Pengirim log event.
    """

    def __init__(self):
        """
        Inisialisasi SingleRunBot.
        """
        self.logger = logging.getLogger("bot")
        self.exchange = IndodaxExchange()
        self.analyzer = MarketAnalyzer(use_llm=True)
        self.risk_manager = RiskManager()
        self.strategy = TradingStrategy(self.analyzer, self.risk_manager)
        self.notifier = TradeNotifier()

    def get_available_balance(self):
        """
        Mengambil saldo IDR aktual yang tersedia di akun Indodax.
        
        Returns:
            float: Saldo Rupiah tersedia.
        """
        return self.exchange.get_idr_balance()

    def process_pair(self, symbol):
        """
        Menganalisis satu pasangan koin dan mencetak rekomendasi aksi trading.
        
        Args:
            symbol (str): Simbol pair (misal 'BTC/IDR').
            
        Returns:
            dict or None: Hasil rekomendasi sinyal dan analisis detail.
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=CANDLESTICK_TIMEFRAME, limit=100)
            if not ohlcv or len(ohlcv) < 50:
                self.logger.warning(f"[{symbol}] Insufficient OHLCV data")
                return None

            ticker = self.exchange.fetch_ticker(symbol)
            if not ticker:
                self.logger.warning(f"[{symbol}] Could not fetch ticker")
                return None

            current_price = ticker["last"]
            balance = self.get_available_balance()
            if balance <= 0:
                balance = 10_000_000

            decision = self.strategy.evaluate(symbol, ohlcv, balance, current_price)
            action = decision["action"]
            analysis = decision["analysis"]

            self.notifier.notify_signal(
                symbol, analysis["signal"], analysis["confidence"],
                analysis["indicators"], analysis.get("llm")
            )

            if action == "buy":
                amount = decision["amount"]
                self.logger.info(
                    f"[REKOMENDASI] BUY {symbol} @ {current_price:,.2f} | "
                    f"Amount: {amount} | Est. Cost: {amount * current_price:,.2f} IDR"
                )
            elif action == "close":
                reason = decision.get("reason", "signal")
                self.logger.info(
                    f"[REKOMENDASI] SELL/CLOSE {symbol} @ {current_price:,.2f} | "
                    f"Reason: {reason}"
                )
            else:
                self.logger.info(f"[REKOMENDASI] HOLD {symbol} @ {current_price:,.2f}")

            return {
                "symbol": symbol,
                "action": action,
                "price": current_price,
                "amount": decision.get("amount"),
                "analysis": analysis,
            }

        except Exception as e:
            self.notifier.notify_error(f"[{symbol}] {str(e)}")
            return None

    def run(self):
        """
        Mengeksekusi analisis pada seluruh TRADING_PAIRS dan menampilkan ringkasan hasil.
        
        Returns:
            list: Daftar hasil rekomendasi untuk semua koin.
        """
        self.logger.info("=" * 60)
        self.logger.info(f"SINGLE RUN | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Timeframe: {CANDLESTICK_TIMEFRAME} | Pairs: {', '.join(TRADING_PAIRS)}")
        self.logger.info("=" * 60)

        balance = self.get_available_balance()
        self.logger.info(f"Balance: {balance:,.2f} IDR")
        self.logger.info("-" * 60)

        results = []
        for symbol in TRADING_PAIRS:
            result = self.process_pair(symbol)
            if result:
                results.append(result)

        self.logger.info("-" * 60)
        self.logger.info("SELESAI. Jalankan lagi setelah 15 menit untuk analisis berikutnya.")
        return results


def main():
    """
    Fungsi entri utama eksekusi single run.
    """
    setup_logger()
    bot = SingleRunBot()
    bot.run()


if __name__ == "__main__":
    main()

