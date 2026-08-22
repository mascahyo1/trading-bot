import logging
import os
from datetime import datetime
from config import LOG_FILE


def setup_logger():
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


class TradeNotifier:
    def __init__(self):
        self.logger = logging.getLogger("notifier")

    def notify_trade(self, symbol, action, price, amount=None, pnl=None):
        msg = f"TRADE: {action.upper()} {symbol} @ {price:.2f}"
        if amount:
            msg += f" | Amount: {amount}"
        if pnl is not None:
            msg += f" | PnL: {pnl:+.2f} IDR"
        self.logger.info(msg)

    def notify_signal(self, symbol, signal, confidence, indicators, llm_result=None):
        msg = (
            f"SIGNAL: {signal.upper()} {symbol} | Confidence: {confidence:.1%} | "
            f"RSI={indicators.get('rsi', 'N/A')} MACD={indicators.get('macd_histogram', 'N/A')}"
        )
        if llm_result:
            msg += (
                f" | LLM: {llm_result.get('signal', 'N/A').upper()} "
                f"conf={llm_result.get('confidence', 0):.1%} "
                f"risk={llm_result.get('risk_level', 'N/A')}"
            )
        self.logger.info(msg)

    def notify_error(self, message):
        self.logger.error(f"ERROR: {message}")

    def notify_summary(self, risk_manager):
        total_pnl = risk_manager.get_total_pnl()
        win_rate = risk_manager.get_win_rate()
        open_count = risk_manager.get_open_positions_count()
        total_trades = len(risk_manager.trade_history)

        self.logger.info(
            f"SUMMARY: Open={open_count} | Total Trades={total_trades} | "
            f"Win Rate={win_rate}% | Total PnL={total_pnl:+.2f} IDR"
        )
