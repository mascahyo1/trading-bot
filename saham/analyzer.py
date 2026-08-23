"""
Market Analyzer untuk Saham Indonesia

Analisis teknikal multi-indikator untuk menghasilkan sinyal trading
(buy/sell/hold) dengan confidence score.

Indikator:
- RSI (14): Overbought/oversold detection
- MACD (12/26/9): Momentum trend
- EMA (9/21/50): Arah trend
- Bollinger Bands (20/2): Volatilitas & price extremes
- ATR (14): Volatility measurement
- Volume: Signal confirmation

Author: AI Trading Bot
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class MarketAnalyzer:
    """
    Technical analysis engine untuk saham Indonesia.
    
    Menghasilkan sinyal buy/sell/hold berdasarkan kombinasi
    multiple technical indicators dengan weighted scoring.
    """

    def __init__(self, use_llm=False):
        """
        Initialize MarketAnalyzer.
        
        Args:
            use_llm (bool): Aktifkan LLM analysis (default False untuk saham)
        """
        self.signal_weights = {
            "rsi": 0.20,
            "macd": 0.20,
            "ema": 0.20,
            "bollinger": 0.15,
            "volume": 0.10,
            "atr": 0.15,
        }
        self.use_llm = use_llm

    def prepare_dataframe(self, ohlcv):
        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def calc_rsi(self, series, period=14):
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calc_macd(self, series, fast=12, slow=26, signal=9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def calc_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()

    def calc_bollinger(self, series, period=20, std_dev=2):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower

    def calc_atr(self, df, period=14):
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr

    def analyze_rsi(self, rsi_series):
        current = rsi_series.iloc[-1]
        if current < 30:
            return "buy", (30 - current) / 30
        elif current > 70:
            return "sell", (current - 70) / 30
        elif current < 45:
            return "buy", 0.3
        elif current > 55:
            return "sell", 0.3
        return "hold", 0.0

    def analyze_macd(self, macd_line, signal_line, histogram):
        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        curr_hist = histogram.iloc[-1]
        prev_hist = histogram.iloc[-2]

        if curr_macd > curr_signal and prev_hist < 0 and curr_hist > 0:
            return "buy", 1.0
        elif curr_macd < curr_signal and prev_hist > 0 and curr_hist < 0:
            return "sell", 1.0
        elif curr_macd > curr_signal:
            return "buy", 0.4
        elif curr_macd < curr_signal:
            return "sell", 0.4
        return "hold", 0.0

    def analyze_ema(self, df):
        ema_9 = self.calc_ema(df["close"], 9)
        ema_21 = self.calc_ema(df["close"], 21)
        ema_50 = self.calc_ema(df["close"], 50)

        curr_price = df["close"].iloc[-1]
        curr_9 = ema_9.iloc[-1]
        curr_21 = ema_21.iloc[-1]
        curr_50 = ema_50.iloc[-1]
        prev_9 = ema_9.iloc[-2]
        prev_21 = ema_21.iloc[-2]

        score = 0.0
        signal = "hold"

        if prev_9 <= prev_21 and curr_9 > curr_21:
            signal = "buy"
            score = 1.0
        elif prev_9 >= prev_21 and curr_9 < curr_21:
            signal = "sell"
            score = 1.0
        else:
            if curr_9 > curr_21:
                signal = "buy"
                score = 0.5
            else:
                signal = "sell"
                score = 0.5

        if curr_price > curr_50:
            score += 0.2
        elif curr_price < curr_50:
            score -= 0.2

        return signal, min(max(score, 0), 1.5)

    def analyze_bollinger(self, df):
        upper, sma, lower = self.calc_bollinger(df["close"])
        curr_price = df["close"].iloc[-1]
        curr_upper = upper.iloc[-1]
        curr_lower = lower.iloc[-1]
        curr_sma = sma.iloc[-1]

        if curr_price <= curr_lower:
            return "buy", 0.8
        elif curr_price >= curr_upper:
            return "sell", 0.8
        elif curr_price < curr_sma:
            return "buy", 0.2
        elif curr_price > curr_sma:
            return "sell", 0.2
        return "hold", 0.0

    def analyze_volume(self, df):
        vol_sma = df["volume"].rolling(window=20).mean()
        curr_vol = df["volume"].iloc[-1]
        avg_vol = vol_sma.iloc[-1]

        ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0

        if ratio > 2.0:
            return "strong", 1.0
        elif ratio > 1.5:
            return "above_avg", 0.6
        elif ratio < 0.5:
            return "weak", 0.3
        return "normal", 0.0

    def analyze(self, ohlcv, symbol="UNKNOWN"):
        if not ohlcv or len(ohlcv) < 50:
            logger.warning(f"Insufficient data for {symbol}")
            return {"signal": "hold", "confidence": 0, "indicators": {}, "symbol": symbol}

        df = self.prepare_dataframe(ohlcv)
        close = df["close"]

        rsi = self.calc_rsi(close)
        macd_line, signal_line, histogram = self.calc_macd(close)
        atr = self.calc_atr(df)

        rsi_signal, rsi_score = self.analyze_rsi(rsi)
        macd_signal, macd_score = self.analyze_macd(macd_line, signal_line, histogram)
        ema_signal, ema_score = self.analyze_ema(df)
        bb_signal, bb_score = self.analyze_bollinger(df)
        vol_signal, vol_score = self.analyze_volume(df)

        indicators = {
            "rsi": round(rsi.iloc[-1], 2),
            "macd": round(macd_line.iloc[-1], 2),
            "macd_signal": round(signal_line.iloc[-1], 2),
            "macd_histogram": round(histogram.iloc[-1], 2),
            "atr": round(atr.iloc[-1], 2),
            "ema_9": round(self.calc_ema(close, 9).iloc[-1], 2),
            "ema_21": round(self.calc_ema(close, 21).iloc[-1], 2),
            "ema_50": round(self.calc_ema(close, 50).iloc[-1], 2),
            "volume_signal": vol_signal,
            "volume_score": round(vol_score, 2),
        }

        buy_score = 0
        sell_score = 0

        if rsi_signal == "buy":
            buy_score += rsi_score * self.signal_weights["rsi"]
        else:
            sell_score += rsi_score * self.signal_weights["rsi"]

        if macd_signal == "buy":
            buy_score += macd_score * self.signal_weights["macd"]
        else:
            sell_score += macd_score * self.signal_weights["macd"]

        if ema_signal == "buy":
            buy_score += ema_score * self.signal_weights["ema"]
        else:
            sell_score += ema_score * self.signal_weights["ema"]

        if bb_signal == "buy":
            buy_score += bb_score * self.signal_weights["bollinger"]
        else:
            sell_score += bb_score * self.signal_weights["bollinger"]

        if vol_signal in ("strong", "above_avg"):
            if buy_score > sell_score:
                buy_score += vol_score * self.signal_weights["volume"]
            elif sell_score > buy_score:
                sell_score += vol_score * self.signal_weights["volume"]

        total_score = buy_score + sell_score
        if total_score == 0:
            return {"signal": "hold", "confidence": 0, "indicators": indicators, "symbol": symbol}

        if buy_score > sell_score:
            signal = "buy"
            confidence = buy_score / total_score
        elif sell_score > buy_score:
            signal = "sell"
            confidence = sell_score / total_score
        else:
            signal = "hold"
            confidence = 0.5

        return {
            "signal": signal,
            "confidence": round(min(confidence, 1.0), 3),
            "buy_score": round(buy_score, 4),
            "sell_score": round(sell_score, 4),
            "indicators": indicators,
            "symbol": symbol,
        }

    def analyze_technical(self, ohlcv, symbol="UNKNOWN"):
        return self.analyze(ohlcv, symbol)
