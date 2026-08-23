import json
import os
import logging
from datetime import datetime
from config import (
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRAILING_STOP_PCT,
    MAX_OPEN_POSITIONS,
    POSITION_SIZE_IDR,
    MIN_ORDER_IDR,
    LOT_SIZE,
    TRADE_HISTORY_FILE,
    MAX_DAILY_LOSS_PCT,
    BUY_TOTAL_FEE_PCT,
    SELL_TOTAL_FEE_PCT,
    ROUND_TRIP_FEE_PCT,
    now_jakarta,
    format_datetime,
)

logger = logging.getLogger(__name__)


class Position:
    def __init__(self, symbol, entry_price, lots, code=None):
        self.symbol = symbol
        self.code = code or symbol.replace(".JK", "")
        self.entry_price_market = entry_price
        self.entry_price = entry_price * (1 + BUY_TOTAL_FEE_PCT)
        self.initial_lots = lots
        self.lots = lots
        self.shares = lots * LOT_SIZE
        self.stop_loss = self.entry_price * (1 - STOP_LOSS_PCT)
        self.take_profit = self.entry_price * (1 + TAKE_PROFIT_PCT)
        self.break_even_price = self.entry_price * (1 + SELL_TOTAL_FEE_PCT)
        self.highest_price = entry_price
        self.trailing_stop_pct = TRAILING_STOP_PCT
        self.entry_time = now_jakarta().isoformat()
        self.status = "open"
        self.partial_sell_count = 0
        self.dca_count = 0
        self.tp1_pct = 0.04
        self.tp2_pct = 0.08
        self.dca1_pct = 0.03
        self.dca2_pct = 0.06
        self.total_buy_fees = 0
        self.total_sell_fees = 0
        self.total_buy_cost = 0
        self.total_sell_proceeds = 0

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

    def dca_lots(self):
        if self.dca_count == 0:
            return max(1, self.initial_lots // 2)
        return max(1, self.initial_lots // 4)

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
        if self.partial_sell_count == 0 and current_price >= self.get_tp1_price():
            return True
        return False

    def should_full_sell(self, current_price):
        if self.partial_sell_count >= 1 and current_price >= self.get_tp2_price():
            return True
        return False

    def partial_sell_lots(self):
        return max(1, self.initial_lots // 2)

    def current_value(self, current_price):
        return self.lots * LOT_SIZE * current_price

    def unrealized_pnl(self, current_price):
        gross_pnl = (current_price - self.entry_price) * self.lots * LOT_SIZE
        estimated_sell_fees = current_price * self.lots * LOT_SIZE * SELL_TOTAL_FEE_PCT
        return gross_pnl - estimated_sell_fees

    def unrealized_pnl_pct(self, current_price):
        if self.entry_price == 0:
            return 0
        net_pnl = self.unrealized_pnl(current_price)
        total_cost = self.entry_price * self.lots * LOT_SIZE
        return (net_pnl / total_cost) * 100

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "code": self.code,
            "entry_price": self.entry_price,
            "entry_price_market": self.entry_price_market,
            "lots": self.lots,
            "initial_lots": self.initial_lots,
            "shares": self.shares,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "break_even_price": self.break_even_price,
            "highest_price": self.highest_price,
            "entry_time": self.entry_time,
            "status": self.status,
            "partial_sell_count": self.partial_sell_count,
            "total_buy_fees": self.total_buy_fees,
            "total_sell_fees": self.total_sell_fees,
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

    def sync_positions_from_exchange(self, exchange, trader):
        portfolio = trader.get_portfolio()
        if not portfolio:
            return

        cash = portfolio.get("cash", 0)
        stocks = portfolio.get("stocks", [])

        for stock_text in stocks:
            try:
                lines = stock_text.strip().split("\n")
                if len(lines) >= 2:
                    code = lines[0].strip()
                    symbol = f"{code}.JK"
                    for line in lines:
                        if "lot" in line.lower():
                            lots = int("".join(filter(str.isdigit, line)))
                            if symbol not in self.positions or self.positions[symbol].status != "open":
                                ticker = exchange.fetch_ticker(symbol)
                                if ticker and ticker.get("last"):
                                    entry_price = ticker["last"]
                                    self.positions[symbol] = Position(symbol, entry_price, lots, code)
                                    logger.info(f"Loaded position: {symbol} lots={lots} entry={entry_price:,.0f}")
            except Exception as e:
                logger.warning(f"Error parsing stock: {e}")

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

    def calculate_lots(self, balance, current_price, is_primary=True):
        if is_primary:
            risk_amount = balance * RISK_PER_TRADE
        else:
            risk_amount = balance * (RISK_PER_TRADE * 0.5)

        position_value = min(POSITION_SIZE_IDR, risk_amount)
        min_value = MIN_ORDER_IDR * 1.5

        if position_value < min_value:
            if balance >= MIN_ORDER_IDR:
                position_value = balance * 0.95
            else:
                return 0

        cost_per_lot = LOT_SIZE * current_price * (1 + BUY_TOTAL_FEE_PCT)
        lots = int(position_value // cost_per_lot)
        return max(1, lots)

    def add_position(self, symbol, entry_price, lots, code=None):
        position = Position(symbol, entry_price, lots, code)
        self.positions[symbol] = position
        logger.info(
            f"Position opened: {symbol} entry={entry_price:,.0f} lots={lots} "
            f"SL={position.stop_loss:,.0f} TP={position.take_profit:,.0f}"
        )
        return position

    def close_position(self, symbol, exit_price):
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.status = "closed"

            buy_value = pos.entry_price_market * pos.initial_lots * LOT_SIZE
            buy_fees = buy_value * BUY_TOTAL_FEE_PCT
            pos.total_buy_fees = buy_fees
            pos.total_buy_cost = buy_value + buy_fees

            sell_value = exit_price * pos.lots * LOT_SIZE
            sell_fees = sell_value * SELL_TOTAL_FEE_PCT
            pos.total_sell_fees = sell_fees
            pos.total_sell_proceeds = sell_value - sell_fees

            gross_pnl = (exit_price - pos.entry_price_market) * pos.lots * LOT_SIZE
            net_pnl = pos.total_sell_proceeds - (pos.entry_price * pos.lots * LOT_SIZE)
            total_fees = (buy_fees * pos.lots / pos.initial_lots) + sell_fees

            pnl_pct = (net_pnl / (pos.entry_price * pos.lots * LOT_SIZE)) * 100

            trade_record = {
                "symbol": symbol,
                "code": pos.code,
                "entry_price": pos.entry_price,
                "entry_price_market": pos.entry_price_market,
                "exit_price": exit_price,
                "lots": pos.lots,
                "shares": pos.lots * LOT_SIZE,
                "buy_fees": round(buy_fees * pos.lots / pos.initial_lots, 2),
                "sell_fees": round(sell_fees, 2),
                "total_fees": round(total_fees, 2),
                "gross_pnl": round(gross_pnl, 2),
                "pnl_amount": round(net_pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "entry_time": pos.entry_time,
                "exit_time": now_jakarta().isoformat(),
            }

            self.trade_history.append(trade_record)
            self._save_history()

            logger.info(
                f"Position closed: {symbol} exit={exit_price:,.0f} | "
                f"Gross PnL={gross_pnl:+,.0f} | Fees={total_fees:,.0f} | "
                f"Net PnL={net_pnl:+,.0f} ({pnl_pct:+.2f}%)"
            )
            return trade_record
        return None

    def check_stop_loss_take_profit(self, symbol, current_price):
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if pos.status != "open":
            return None

        if current_price <= pos.stop_loss:
            return "stop_loss"
        elif current_price >= pos.take_profit:
            return "take_profit"

        return None

    def get_total_pnl(self):
        return sum(t.get("pnl_amount", 0) for t in self.trade_history)

    def get_win_rate(self):
        if not self.trade_history:
            return 0
        wins = sum(1 for t in self.trade_history if t.get("pnl_amount", 0) > 0)
        return round(wins / len(self.trade_history) * 100, 2)

    def get_unrealized_pnl(self, exchange):
        total_unrealized = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    current_price = ticker["last"]
                    unrealized = pos.unrealized_pnl(current_price)
                    total_unrealized += unrealized
        return round(total_unrealized, 2)

    def get_total_stock_value(self, exchange):
        total = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    total += ticker["last"] * pos.lots * LOT_SIZE
        return total

    def get_position_details(self, exchange):
        details = {}
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    current_price = ticker["last"]
                    net_pnl = pos.unrealized_pnl(current_price)
                    pnl_pct = pos.unrealized_pnl_pct(current_price)
                    est_sell_fees = current_price * pos.lots * LOT_SIZE * SELL_TOTAL_FEE_PCT
                    details[symbol] = {
                        "code": pos.code,
                        "lots": pos.lots,
                        "shares": pos.lots * LOT_SIZE,
                        "entry_price": pos.entry_price,
                        "entry_price_market": pos.entry_price_market,
                        "current_price": current_price,
                        "value": current_price * pos.lots * LOT_SIZE,
                        "net_pnl": net_pnl,
                        "pnl": net_pnl,
                        "pnl_pct": pnl_pct,
                        "est_sell_fees": est_sell_fees,
                        "break_even": pos.break_even_price,
                    }
        return details


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
            f"RSI: {rsi} | Price: {current_price:,.0f}"
        )

        if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
            pos = self.risk_manager.positions[symbol]

            if pos.update_trailing_stop(current_price):
                logger.info(
                    f"[{symbol}] Trailing stop updated: {pos.stop_loss:,.0f} "
                    f"(highest: {pos.highest_price:,.0f})"
                )

            if pos.check_trailing_stop(current_price):
                return {
                    "action": "close",
                    "reason": f"trailing_stop (peak: {pos.highest_price:,.0f})",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            if pos.should_partial_sell(current_price):
                partial_lots = pos.partial_sell_lots()
                pos.partial_sell_count += 1
                pos.lots -= partial_lots
                return {
                    "action": "partial_sell",
                    "reason": f"tp1_hit (+4% @ {pos.get_tp1_price():,.0f})",
                    "analysis": analysis,
                    "lots": partial_lots,
                }

            if pos.should_full_sell(current_price):
                return {
                    "action": "close",
                    "reason": f"tp2_hit (+8% @ {pos.get_tp2_price():,.0f})",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            if pos.should_dca(current_price):
                dca_lots = pos.dca_lots()
                dca_cost = dca_lots * LOT_SIZE * current_price
                dca_fees = dca_cost * BUY_TOTAL_FEE_PCT
                total_dca_cost = dca_cost + dca_fees
                if balance >= total_dca_cost:
                    pos.dca_count += 1
                    pos.lots += dca_lots
                    pos.shares = pos.lots * LOT_SIZE
                    total_cost_with_fees = pos.entry_price * (pos.lots - dca_lots) * LOT_SIZE + current_price * (1 + BUY_TOTAL_FEE_PCT) * dca_lots * LOT_SIZE
                    pos.entry_price = total_cost_with_fees / (pos.lots * LOT_SIZE)
                    pos.break_even_price = pos.entry_price * (1 + SELL_TOTAL_FEE_PCT)
                    return {
                        "action": "buy",
                        "lots": dca_lots,
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
                    "lots": pos.lots,
                }

            if rsi >= self.rsi_overbought and confidence > 0.5:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f} overbought)",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            macd_hist = indicators.get("macd_histogram", 0)
            if rsi > 65 and macd_hist < 0:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f}, MACD bearish)",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

        if signal == "hold" or confidence < self.min_confidence:
            return {"action": "hold", "analysis": analysis}

        if signal == "buy":
            if rsi > self.rsi_entry_max:
                logger.info(f"[{symbol}] Skip buy: RSI {rsi} > {self.rsi_entry_max}")
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

            if not can_afford:
                logger.info(f"[{symbol}] Cannot afford, balance {balance:,.0f} < {min_order:,.0f}")
                return {"action": "hold", "reason": "insufficient_balance", "analysis": analysis}

            if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
                return {"action": "hold", "analysis": analysis}

            if not self.risk_manager.can_open_position():
                logger.info(f"Max positions reached ({MAX_OPEN_POSITIONS})")
                return {"action": "hold", "analysis": analysis}

            if self.risk_manager.is_daily_loss_limit_reached(balance):
                logger.info("Daily loss limit reached")
                return {"action": "hold", "reason": "daily_loss_limit", "analysis": analysis}

            lots = self.risk_manager.calculate_lots(balance, current_price, is_primary=is_primary)
            return {
                "action": "buy",
                "lots": lots,
                "analysis": analysis,
            }

        return {"action": "hold", "analysis": analysis}
