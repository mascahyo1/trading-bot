"""
Stock Exchange Wrapper untuk Saham Indonesia (yfinance)

Menyediakan data harga saham Indonesia dengan kode .JK (Jakarta Stock Exchange).
Menggunakan yfinance sebagai sumber data dengan caching untuk mengurangi API calls.

Format kode saham: BBCA.JK, BMRI.JK, TLKM.JK, dll

Fitur:
- OHLCV data untuk analisis teknikal
- Real-time price quotes
- Intraday data (5-minute intervals)
- Caching dengan TTL 60 detik
- Multiple stock prices fetching

Author: AI Trading Bot
"""

import logging
import time
import pandas as pd
import yfinance as yf
from config import LOOKBACK_DAYS, STOCK_CODE_MAP

logger = logging.getLogger(__name__)


class StockExchange:
    """
    Wrapper class untuk yfinance (saham Indonesia).
    
    Attributes:
        _cache (dict): Cache untuk menyimpan data OHLCV
        _cache_ttl (int): Cache time-to-live dalam detik
    """

    def __init__(self):
        """Initialize exchange dengan cache kosong."""
        self._cache = {}
        self._cache_ttl = 60

    def fetch_ohlcv(self, symbol, period=None, interval="1d"):
        """
        Fetch OHLCV data untuk satu saham.
        
        Args:
            symbol (str): Kode saham (mis. "BBCA.JK")
            period (str): Periode data (mis. "90d", "1y")
            interval (str): Interval candle ("1d", "1h", "5m")
            
        Returns:
            list: List of [timestamp, open, high, low, close, volume] atau None
        """
        if period is None:
            period = f"{LOOKBACK_DAYS}d"

        cache_key = f"{symbol}_{period}_{interval}"
        now = time.time()
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached_data

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            if hist is None or hist.empty:
                logger.warning(f"No data for {symbol}")
                return None

            ohlcv = []
            for timestamp, row in hist.iterrows():
                ts = int(timestamp.timestamp() * 1000)
                ohlcv.append([
                    ts,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])

            self._cache[cache_key] = (now, ohlcv)
            return ohlcv
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def fetch_ticker(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            if price is None:
                hist = ticker.history(period="5d")
                if hist is not None and not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            if price is None:
                return None

            prev_close = getattr(info, "previous_close", price)
            if prev_close is None:
                prev_close = price

            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close > 0 else 0

            return {
                "symbol": symbol,
                "last": float(price),
                "previous_close": float(prev_close),
                "change": float(change),
                "change_pct": float(change_pct),
                "volume": float(getattr(info, "last_volume", 0) or 0),
            }
        except Exception as e:
            logger.error(f"Ticker error for {symbol}: {e}")
            return None

    def fetch_intraday(self, symbol, period="1d", interval="5m"):
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            if hist is None or hist.empty:
                return None

            ohlcv = []
            for timestamp, row in hist.iterrows():
                ts = int(timestamp.timestamp() * 1000)
                ohlcv.append([
                    ts,
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])
            return ohlcv
        except Exception as e:
            logger.error(f"Intraday error for {symbol}: {e}")
            return None

    def get_stock_name(self, symbol):
        code = STOCK_CODE_MAP.get(symbol, symbol.replace(".JK", ""))
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            name = getattr(info, "long_name", None) or getattr(info, "short_name", None)
            if name:
                return name
        except Exception:
            pass
        return code

    def get_multiple_prices(self, symbols):
        prices = {}
        for sym in symbols:
            ticker = self.fetch_ticker(sym)
            if ticker:
                prices[sym] = ticker["last"]
            time.sleep(0.3)
        return prices


def main():
    ex = StockExchange()
    price = ex.fetch_ticker("BBCA.JK")
    if price:
        print(f"BBCA: {price['last']:,.0f} ({price['change_pct']:+.2f}%)")
    ohlcv = ex.fetch_ohlcv("BBCA.JK", period="30d")
    if ohlcv:
        print(f"Candles: {len(ohlcv)}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
