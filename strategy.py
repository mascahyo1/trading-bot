import json
import os
import logging
from datetime import datetime
from config import (
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    MAX_OPEN_POSITIONS,
    POSITION_SIZE_USDT,
    MIN_ORDER_IDR,
    TRADE_HISTORY_FILE,
    MAX_DAILY_LOSS_PCT,
    now_jakarta,
    format_datetime,
)

logger = logging.getLogger(__name__)


class Position:
    def __init__(self, symbol, entry_price, amount, side="long"):
        self.symbol = symbol
        self.entry_price = entry_price
        self.amount = amount
        self.side = side
        self.stop_loss = entry_price * (1 - STOP_LOSS_PCT)
        self.take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
        self.highest_price = entry_price
        self.trailing_stop_pct = 0.05
        self.entry_time = now_jakarta().isoformat()
        self.status = "open"

    def update_trailing_stop(self, current_price):
        if current_price > self.highest_price:
            self.highest_price = current_price
            new_stop = current_price * (1 - self.trailing_stop_pct)
            if new_stop > self.stop_loss:
                self.stop_loss = new_stop
                return True
        return False

    def check_trailing_stop(self, current_price):
        return current_price <= self.stop_loss

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "amount": self.amount,
            "side": self.side,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "highest_price": self.highest_price,
            "entry_time": self.entry_time,
            "status": self.status,
        }


class RiskManager:
    def __init__(self):
        self.positions = {}
        self.trade_history = self._load_history()
        self.daily_loss_limit_pct = MAX_DAILY_LOSS_PCT
        self.last_check_date = datetime.now().strftime("%Y-%m-%d")

    def _load_history(self):
        if os.path.exists(TRADE_HISTORY_FILE):
            try:
                with open(TRADE_HISTORY_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_history(self):
        try:
            with open(TRADE_HISTORY_FILE, "w") as f:
                json.dump(self.trade_history, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving trade history: {e}")

    def get_daily_pnl(self):
        today = now_jakarta().strftime("%Y-%m-%d")
        pnl = 0
        for t in self.trade_history:
            exit_time = t.get("exit_time", "")
            if exit_time.startswith(today):
                pnl += t.get("pnl_amount", 0)
        return pnl

    def is_daily_loss_limit_reached(self, balance):
        daily_pnl = self.get_daily_pnl()
        if daily_pnl >= 0:
            return False
        loss_pct = abs(daily_pnl) / balance if balance > 0 else 0
        return loss_pct >= self.daily_loss_limit_pct

    def get_open_positions_count(self):
        return sum(1 for p in self.positions.values() if p.status == "open")

    def can_open_position(self):
        return self.get_open_positions_count() < MAX_OPEN_POSITIONS

    def calculate_position_size(self, balance, current_price):
        risk_amount = balance * RISK_PER_TRADE
        position_value = min(POSITION_SIZE_USDT, risk_amount)
        min_value = MIN_ORDER_IDR * 1.5
        if position_value < min_value:
            if balance >= MIN_ORDER_IDR:
                position_value = balance * 0.95
            else:
                return 0
        amount = position_value / current_price
        return round(amount, 8)

    def add_position(self, symbol, entry_price, amount):
        position = Position(symbol, entry_price, amount)
        self.positions[symbol] = position
        logger.info(
            f"Position opened: {symbol} entry={entry_price} amount={amount} "
            f"SL={position.stop_loss:.2f} TP={position.take_profit:.2f}"
        )
        return position

    def close_position(self, symbol, exit_price):
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.status = "closed"

            if pos.side == "long":
                pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
            else:
                pnl_pct = (pos.entry_price - exit_price) / pos.entry_price

            pnl_amount = (exit_price - pos.entry_price) * pos.amount

            trade_record = {
                "symbol": symbol,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "amount": pos.amount,
                "side": pos.side,
                "pnl_pct": round(pnl_pct * 100, 4),
                "pnl_amount": round(pnl_amount, 2),
                "entry_time": pos.entry_time,
                "exit_time": now_jakarta().isoformat(),
            }

            self.trade_history.append(trade_record)
            self._save_history()

            logger.info(
                f"Position closed: {symbol} exit={exit_price} "
                f"PnL={pnl_pct*100:.2f}% ({pnl_amount:.2f} IDR)"
            )
            return trade_record
        return None

    def check_stop_loss_take_profit(self, symbol, current_price):
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if pos.status != "open":
            return None

        if pos.side == "long":
            if current_price <= pos.stop_loss:
                return "stop_loss"
            elif current_price >= pos.take_profit:
                return "take_profit"
        else:
            if current_price >= pos.stop_loss:
                return "stop_loss"
            elif current_price <= pos.take_profit:
                return "take_profit"

        return None

    def get_total_pnl(self):
        return sum(t.get("pnl_amount", 0) for t in self.trade_history)

    def get_win_rate(self):
        if not self.trade_history:
            return 0
        wins = sum(1 for t in self.trade_history if t.get("pnl_amount", 0) > 0)
        return round(wins / len(self.trade_history) * 100, 2)


class TradingStrategy:
    def __init__(self, analyzer, risk_manager):
        self.analyzer = analyzer
        self.risk_manager = risk_manager
        self.min_confidence = 0.65
        self.rsi_overbought = 70
        self.rsi_oversold = 30

    def evaluate(self, symbol, ohlcv, balance, current_price):
        analysis = self.analyzer.analyze(ohlcv, symbol=symbol)
        signal = analysis["signal"]
        confidence = analysis["confidence"]
        indicators = analysis.get("indicators", {})
        rsi = indicators.get("rsi", 50)

        logger.info(
            f"[{symbol}] Signal: {signal.upper()} | Confidence: {confidence:.1%} | "
            f"RSI: {rsi} | Price: {current_price:.2f}"
        )

        if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
            pos = self.risk_manager.positions[symbol]

            if pos.update_trailing_stop(current_price):
                logger.info(
                    f"[{symbol}] Trailing stop updated: {pos.stop_loss:.2f} "
                    f"(highest: {pos.highest_price:.2f})"
                )

            if pos.check_trailing_stop(current_price):
                return {
                    "action": "close",
                    "reason": f"trailing_stop (peak: {pos.highest_price:.0f})",
                    "analysis": analysis,
                }

            if current_price >= pos.take_profit:
                return {
                    "action": "close",
                    "reason": "take_profit",
                    "analysis": analysis,
                }

            if rsi >= self.rsi_overbought and confidence > 0.5:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f} overbought)",
                    "analysis": analysis,
                }

            macd_hist = indicators.get("macd_histogram", 0)
            if rsi > 65 and macd_hist < 0:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f}, MACD bearish)",
                    "analysis": analysis,
                }

        if signal == "hold" or confidence < self.min_confidence:
            return {"action": "hold", "analysis": analysis}

        if signal == "buy":
            if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
                return {"action": "hold", "analysis": analysis}

            if not self.risk_manager.can_open_position():
                logger.info(f"Max positions reached ({MAX_OPEN_POSITIONS}), skipping buy")
                return {"action": "hold", "analysis": analysis}

            if self.risk_manager.is_daily_loss_limit_reached(balance):
                logger.info(f"Daily loss limit reached, skipping buy")
                return {"action": "hold", "reason": "daily_loss_limit", "analysis": analysis}

            amount = self.risk_manager.calculate_position_size(balance, current_price)
            return {
                "action": "buy",
                "amount": amount,
                "analysis": analysis,
            }

        return {"action": "hold", "analysis": analysis}
