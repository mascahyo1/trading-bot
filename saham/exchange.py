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
    Wrapper untuk Yahoo Finance (yfinance) khusus saham Indonesia (.JK).

    Menyediakan pengambilan data OHLCV, harga real-time, data intraday,
    dan nama emiten dengan cache berbasis TTL agar hemat request API.

    Attributes:
        _cache (dict): Cache internal (cache_key -> (timestamp, data)).
        _cache_ttl (int): Durasi cache dalam detik (default 60 detik).
    """

    def __init__(self):
        """
        Inisialisasi StockExchange dengan cache kosong dan TTL 60 detik.

        Cache menyimpan hasil fetch_ohlcv agar request berulang dalam
        60 detik tidak memukul Yahoo Finance lagi.
        """
        self._cache = {}
        self._cache_ttl = 60

    def fetch_ohlcv(self, symbol, period=None, interval="1d"):
        """
        Mengambil data OHLCV (Open-High-Low-Close-Volume) untuk satu saham.
        
        Args:
            symbol (str): Kode saham (mis. "BBCA.JK")
            period (str): Periode data (mis. "90d", "1y")
            interval (str): Interval candle ("1d", "1h", "5m")
            
        Returns:
            list | None: Daftar baris [timestamp_ms, open, high, low, close, volume]
                atau None jika data kosong / error. Timestamp dalam milidetik.
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
        """
        Mengambil informasi ticker harga real-time dan statistik harian saham.
        
        Args:
            symbol (str): Simbol saham Yahoo Finance (misal 'BBCA.JK').
            
        Returns:
            dict or None: Dictionary berisi 'symbol', 'last' (harga terkini), 'previous_close',
                          'change', 'change_pct', 'volume', atau None jika gagal.
        """
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
        """
        Mengambil data candlestick intraday jangka pendek (misal 5 menit).
        
        Args:
            symbol (str): Simbol saham (misal 'BBCA.JK').
            period (str, optional): Periode data. Default '1d'.
            interval (str, optional): Interval candlestick. Default '5m'.
            
        Returns:
            list or None: List baris OHLCV [timestamp_ms, open, high, low, close, volume] atau None.
        """
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
        """
        Mengambil nama panjang resmi perusahaan/emiten dari Yahoo Finance metadata.
        
        Args:
            symbol (str): Simbol saham.
            
        Returns:
            str: Nama perusahaan (misal 'Bank Central Asia Tbk') atau kode emiten jika tidak ditemukan.
        """
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
        """
        Mengambil harga pasar terkini untuk sekumpulan kode saham sekaligus secara batch.
        
        Args:
            symbols (list): Daftar simbol saham (misal ['BBCA.JK', 'BMRI.JK']).
            
        Returns:
            dict: Map dari symbol -> harga terakhir (float).
        """
        prices = {}
        for sym in symbols:
            ticker = self.fetch_ticker(sym)
            if ticker:
                prices[sym] = ticker["last"]
            time.sleep(0.3)
        return prices


def main():
    """
    Fungsi pengujian mandiri konektivitas StockExchange ke Yahoo Finance.
    """
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

