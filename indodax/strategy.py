"""
Trading Strategy & Risk Management untuk Indodax (Crypto)

Mengimplementasikan:
- Position tracking dengan stop-loss, take-profit, trailing stop
- Dollar Cost Averaging (DCA) untuk averaging down
- Partial selling untuk profit taking bertahap
- Risk management dengan position sizing dan daily loss limit
- Win rate tracking dan trade history

Fitur:
- Auto stop-loss pada -3%
- Auto take-profit pada +6%
- Trailing stop 5% dari harga tertinggi
- DCA otomatis saat harga turun 3% dan 6%
- Partial sell 50% saat TP1 (+3%), sisanya saat TP2 (+6%)

Author: AI Trading Bot
"""

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
    RISK_PRIMARY_PCT,
    RISK_SECONDARY_PCT,
    TRADING_PAIRS,
    now_jakarta,
    format_datetime,
)

logger = logging.getLogger(__name__)


class Position:
    """
    Merepresentasikan posisi trading yang terbuka.
    
    Attributes:
        symbol (str): Pair trading (mis. "BTC/IDR")
        entry_price (float): Harga beli rata-rata
        initial_amount (float): Jumlah awal dibeli
        amount (float): Jumlah saat ini (berubah jika partial sell/DCA)
        stop_loss (float): Harga stop loss
        take_profit (float): Harga take profit
        highest_price (float): Highest price untuk trailing stop
        status (str): "open" atau "closed"
        partial_sell_count (int): Jumlah partial sell yang sudah dilakukan
        dca_count (int): Jumlah DCA yang sudah dilakukan
    """

    def __init__(self, symbol, entry_price, amount, side="long"):
        """
        Inisialisasi posisi baru.
        
        Args:
            symbol (str): Pair trading
            entry_price (float): Harga entry
            amount (float): Jumlah asset
            side (str): "long" atau "short"
        """
        self.symbol = symbol
        self.entry_price = entry_price
        self.initial_amount = amount
        self.amount = amount
        self.side = side
        self.stop_loss = entry_price * (1 - STOP_LOSS_PCT)
        self.take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
        self.highest_price = entry_price
        self.trailing_stop_pct = 0.05
        self.entry_time = now_jakarta().isoformat()
        self.status = "open"
        self.partial_sell_count = 0
        self.dca_count = 0
        self.tp1_pct = 0.03
        self.tp2_pct = 0.06
        self.dca1_pct = 0.03
        self.dca2_pct = 0.06

    def get_dca1_price(self):
        return self.entry_price * (1 - self.dca1_pct)

    def get_dca2_price(self):
        return self.entry_price * (1 - self.dca2_pct)

    def should_dca(self, current_price):
        if self.dca_count >= 2:
            return False
        if self.dca_count == 0 and current_price <= self.get_dca1_price():
            return True
        if self.dca_count == 1 and current_price <= self.get_dca2_price():
            return True
        return False

    def dca_amount(self, balance, current_price):
        if self.dca_count == 0:
            return round(self.initial_amount * 0.5, 8)
        return round(self.initial_amount * 0.25, 8)

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

    def get_tp1_price(self):
        return self.entry_price * (1 + self.tp1_pct)

    def get_tp2_price(self):
        return self.entry_price * (1 + self.tp2_pct)

    def should_partial_sell(self, current_price):
        tp1 = self.get_tp1_price()
        if self.partial_sell_count == 0 and current_price >= tp1:
            return True
        return False

    def should_full_sell(self, current_price):
        tp2 = self.get_tp2_price()
        if self.partial_sell_count >= 1 and current_price >= tp2:
            return True
        return False

    def partial_sell_amount(self):
        return round(self.initial_amount * 0.5, 8)

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "amount": self.amount,
            "initial_amount": self.initial_amount,
            "side": self.side,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "highest_price": self.highest_price,
            "entry_time": self.entry_time,
            "status": self.status,
            "partial_sell_count": self.partial_sell_count,
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

    def sync_positions_from_exchange(self, exchange):
        balance = exchange.get_balance()
        if balance.get("error"):
            return

        for b in balance.get("balances", []):
            asset = b["asset"]
            free = float(b.get("free", 0))
            if free > 0 and asset != "IDR":
                symbol = f"{asset}/IDR"
                if symbol not in self.positions or self.positions[symbol].status != "open":
                    ticker = exchange.fetch_ticker(symbol)
                    if ticker and ticker.get("last"):
                        entry_price = ticker["last"]
                        self.positions[symbol] = Position(symbol, entry_price, free)
                        logger.info(f"Loaded position from exchange: {symbol} amount={free} entry={entry_price:.0f}")

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

    def calculate_position_size(self, balance, current_price, is_primary=True):
        risk_pct = RISK_PRIMARY_PCT if is_primary else RISK_SECONDARY_PCT
        risk_amount = balance * risk_pct
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

    def get_avg_win_loss(self):
        if not self.trade_history:
            return 0, 0
        wins = [t["pnl_amount"] for t in self.trade_history if t.get("pnl_amount", 0) > 0]
        losses = [abs(t["pnl_amount"]) for t in self.trade_history if t.get("pnl_amount", 0) <= 0]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        return round(avg_win, 2), round(avg_loss, 2)

    def get_unrealized_pnl(self, exchange):
        total_unrealized = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    current_price = ticker["last"]
                    unrealized = (current_price - pos.entry_price) * pos.amount
                    total_unrealized += unrealized
        return round(total_unrealized, 2)

    def get_total_portfolio_value(self, exchange, idr_balance):
        unrealized = self.get_unrealized_pnl(exchange)
        return idr_balance + unrealized + self._get_open_positions_value(exchange)

    def _get_open_positions_value(self, exchange):
        total = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    total += ticker["last"] * pos.amount
        return total


class TradingStrategy:
    def __init__(self, analyzer, risk_manager):
        self.analyzer = analyzer
        self.risk_manager = risk_manager
        self.min_confidence = 0.70
        self.rsi_overbought = 70
        self.rsi_entry_max = 40
        self.min_risk_reward = 2.0
        self.min_win_rate = 40.0

    def evaluate(self, symbol, ohlcv, balance, current_price, is_primary=True):
        analysis = self.analyzer.analyze(ohlcv, symbol=symbol)
        signal = analysis["signal"]
        confidence = analysis["confidence"]
        indicators = analysis.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        atr = indicators.get("atr", 0)

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
                    "amount": pos.amount,
                }

            if pos.should_partial_sell(current_price):
                partial_amount = pos.partial_sell_amount()
                pos.partial_sell_count += 1
                pos.amount -= partial_amount
                return {
                    "action": "partial_sell",
                    "reason": f"tp1_hit (+3% @ {pos.get_tp1_price():,.0f})",
                    "analysis": analysis,
                    "amount": partial_amount,
                }

            if pos.should_full_sell(current_price):
                return {
                    "action": "close",
                    "reason": f"tp2_hit (+6% @ {pos.get_tp2_price():,.0f})",
                    "analysis": analysis,
                    "amount": pos.amount,
                }

            if pos.should_dca(current_price):
                dca_amount = pos.dca_amount(balance, current_price)
                cost = dca_amount * current_price
                if balance >= cost * 1.01:
                    pos.dca_count += 1
                    pos.amount += dca_amount
                    pos.entry_price = (pos.entry_price * (pos.amount - dca_amount) + current_price * dca_amount) / pos.amount
                    return {
                        "action": "buy",
                        "amount": dca_amount,
                        "reason": f"dca_{pos.dca_count} (price dropped {pos.dca_count * 3}%)",
                        "analysis": analysis,
                        "is_dca": True,
                    }
                else:
                    logger.info(f"[{symbol}] DCA skipped: insufficient balance")

            if current_price >= pos.take_profit:
                return {
                    "action": "close",
                    "reason": "take_profit",
                    "analysis": analysis,
                    "amount": pos.amount,
                }

            if rsi >= self.rsi_overbought and confidence > 0.5:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f} overbought)",
                    "analysis": analysis,
                    "amount": pos.amount,
                }

            macd_hist = indicators.get("macd_histogram", 0)
            if rsi > 65 and macd_hist < 0:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f}, MACD bearish)",
                    "analysis": analysis,
                    "amount": pos.amount,
                }

        if signal == "hold" or confidence < self.min_confidence:
            return {"action": "hold", "analysis": analysis}

        if signal == "buy":
            if rsi > self.rsi_entry_max:
                logger.info(f"[{symbol}] Skip buy: RSI {rsi} > {self.rsi_entry_max} (not oversold)")
                return {"action": "hold", "reason": "rsi_too_high", "analysis": analysis}

            win_rate = self.risk_manager.get_win_rate()
            if len(self.risk_manager.trade_history) >= 5 and win_rate < self.min_win_rate:
                logger.info(f"[{symbol}] Skip buy: win rate {win_rate}% < {self.min_win_rate}%")
                return {"action": "hold", "reason": "low_win_rate", "analysis": analysis}

            risk = current_price * STOP_LOSS_PCT
            reward = current_price * TAKE_PROFIT_PCT
            rr_ratio = reward / risk if risk > 0 else 0
            if rr_ratio < self.min_risk_reward:
                logger.info(f"[{symbol}] Skip buy: R/R {rr_ratio:.1f} < {self.min_risk_reward}")
                return {"action": "hold", "reason": "poor_risk_reward", "analysis": analysis}

            min_order = MIN_ORDER_IDR * 1.5
            can_afford = balance >= min_order

            if not can_afford and symbol not in self.risk_manager.positions:
                logger.info(f"[{symbol}] Cannot afford, balance {balance:,.0f} < {min_order:,.0f} IDR")
                return {"action": "hold", "reason": "insufficient_balance", "analysis": analysis}

            if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
                return {"action": "hold", "analysis": analysis}

            if not self.risk_manager.can_open_position():
                logger.info(f"Max positions reached ({MAX_OPEN_POSITIONS}), skipping buy")
                return {"action": "hold", "analysis": analysis}

            if self.risk_manager.is_daily_loss_limit_reached(balance):
                logger.info(f"Daily loss limit reached, skipping buy")
                return {"action": "hold", "reason": "daily_loss_limit", "analysis": analysis}

            amount = self.risk_manager.calculate_position_size(balance, current_price, is_primary=is_primary)
            return {
                "action": "buy",
                "amount": amount,
                "analysis": analysis,
            }

        return {"action": "hold", "analysis": analysis}

    def find_rebalance_sell_candidates(self, all_analyses, balance):
        if balance >= MIN_ORDER_IDR * 1.5:
            return []

        candidates = []
        for analysis in all_analyses:
            symbol = analysis["symbol"]
            if symbol not in self.risk_manager.positions:
                continue
            if self.risk_manager.positions[symbol].status != "open":
                continue

            signal = analysis["signal"]
            confidence = analysis["confidence"]
            rsi = analysis.get("indicators", {}).get("rsi", 50)

            score = 0
            if signal == "sell":
                score += 30 + int(confidence * 30)
            if rsi > 60:
                score += (rsi - 60) * 2
            if rsi > 65:
                score += 10

            if score > 20:
                candidates.append({
                    "symbol": symbol,
                    "score": score,
                    "amount": self.risk_manager.positions[symbol].amount,
                    "reason": f"rebalance (signal: {signal}, RSI: {rsi:.1f})",
                })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:1]
