"""
Exchange Wrapper untuk Indodax (Crypto)

Menyediakan interface untuk berinteraksi dengan API Indodax:
- Public API: Server time, ticker, OHLCV
- Private API: Balance, create order, cancel order, trade history

Fitur:
- Automatic retry (3x) untuk network errors
- HMAC signature untuk autentikasi
- CCXT integration untuk market data
- Rate limiting support

API Endpoints:
- GET /api/v2/serverTime
- GET /api/v2/tickers
- GET /api/v2/trades
- POST /api/v2/order
- DELETE /api/v2/order

Author: AI Trading Bot
"""

import hashlib
import hmac
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import socket
import ccxt
from config import INDODAX_API_KEY, INDODAX_API_SECRET

logger = logging.getLogger(__name__)

BASE_URL = "https://api.indodax.com"
MAX_RETRIES = 3


def api_retry(func):
    """
    Decorator untuk automatic retry pada API calls.
    
    Retry strategy: Exponential backoff (2s, 4s, 8s)
    Max retries: 3 times
    """
    def wrapper(*args, **kwargs):
        """
        Inner function yang menjalankan retry logic.
        
        Menangkap network-related errors (URLError, timeout, ConnectionError)
        lalu melakukan exponential backoff hingga MAX_RETRIES kali.
        Error non-network langsung dilempar sebagai dict error tanpa retry.
        """
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
                wait = (2 ** attempt) * 2
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"API retry {attempt + 1}/{MAX_RETRIES} after {wait}s: {str(e)[:60]}")
                    time.sleep(wait)
                else:
                    logger.error(f"API failed after {MAX_RETRIES} retries: {str(e)[:60]}")
                    return {"error": True, "message": str(e)}
            except Exception as e:
                logger.error(f"API error: {str(e)[:60]}")
                return {"error": True, "message": str(e)}
        return {"error": True, "message": "max_retries_exceeded"}
    return wrapper


class IndodaxExchange:
    """
    Wrapper class untuk Indodax API.
    
    Attributes:
        api_key (str): API key dari Indodax
        secret_key (str): Secret key dari Indodax
        ccxt (ccxt.exchange): CCXT instance untuk market data
    """

    def __init__(self):
        """Initialize exchange dengan API credentials."""
        self.api_key = INDODAX_API_KEY
        self.secret_key = INDODAX_API_SECRET
        self.ccxt = ccxt.indodax({
            "apiKey": self.api_key,
            "secret": self.secret_key,
            "enableRateLimit": True,
        })

    def _sign(self, query_string):
        """
        Membuat tanda tangan kriptografi HMAC-SHA256 untuk autentikasi Private API Indodax.
        
        Args:
            query_string (str): Parameter query yang sudah di-encode URL.
            
        Returns:
            str: Heksadesimal digest dari tanda tangan HMAC-SHA256.
        """
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    @api_retry
    def _v2_request(self, method, endpoint, params=None):
        """
        Mengirim permintaan HTTP terotentikasi ke endpoint Trade API v2 Indodax.
        
        Args:
            method (str): Metode HTTP ('GET', 'POST', 'DELETE').
            endpoint (str): Jalur endpoint API (misal '/api/v2/account').
            params (dict, optional): Parameter query atau form body.
            
        Returns:
            dict: Respons JSON dari server Indodax.
        """
        url = BASE_URL + endpoint
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        if params is None:
            params = {}

        # Tambahkan timestamp Unix milliseconds dan window toleransi request
        timestamp = int(time.time() * 1000)
        params["timestamp"] = timestamp
        params["recvWindow"] = 5000

        query_string = urllib.parse.urlencode(params)
        signature = self._sign(query_string)

        headers["X-APIKEY"] = self.api_key
        headers["Sign"] = signature

        if method == "GET":
            url = f"{url}?{query_string}"
            data = None
        elif method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = query_string.encode("utf-8")
        elif method == "DELETE":
            url = f"{url}?{query_string}"
            data = None
        else:
            data = None

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def server_time(self):
        """
        Mengambil waktu server resmi dari Indodax untuk sinkronisasi timestamp.
        
        Returns:
            int or None: Timestamp Unix dalam milidetik, atau None jika gagal.
        """
        req = urllib.request.Request(
            f"{BASE_URL}/api/v2/serverTime",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("timestamp")
        except Exception:
            return None

    def fetch_ohlcv(self, symbol, timeframe="15m", limit=100):
        """
        Mengambil data candlestick historis (Open, High, Low, Close, Volume) via library CCXT.
        
        Args:
            symbol (str): Pasangan aset crypto (misal 'BTC/IDR').
            timeframe (str, optional): Interval candlestick ('15m', '1h', '1d'). Default '15m'.
            limit (int, optional): Jumlah bar candlestick yang diambil. Default 100.
            
        Returns:
            list or None: List of [timestamp, open, high, low, close, volume] atau None jika gagal.
        """
        try:
            ohlcv = self.ccxt.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                return ohlcv
            return None
        except Exception:
            return None

    def fetch_ticker(self, symbol):
        """
        Mengambil data harga ticker pasar terkini (last price, bid, ask, high, low, volume) via CCXT.
        
        Args:
            symbol (str): Pasangan aset crypto (misal 'BTC/IDR').
            
        Returns:
            dict or None: Data ticker dari exchange atau None jika terjadi kesalahan.
        """
        try:
            ticker = self.ccxt.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Ticker error for {symbol}: {e}")
            return None

    def get_balance(self):
        """
        Mengambil saldo lengkap semua aset di akun Indodax pengguna melalui endpoint /api/v2/account.
        
        Returns:
            dict: Respons API berisi list saldo seluruh koin dan fiat (free & locked).
        """
        return self._v2_request("GET", "/api/v2/account")

    def get_idr_balance(self):
        """
        Mengambil saldo Rupiah (IDR) bebas yang siap ditradingkan (free balance).
        
        Returns:
            float: Jumlah saldo IDR tersedia (default 0 jika terjadi error atau saldo kosong).
        """
        result = self.get_balance()
        if result.get("error"):
            return 0
        for b in result.get("balances", []):
            if b.get("asset") == "IDR":
                return float(b.get("free", 0))
        return 0

    def create_order(self, symbol, side, order_type, price=None, quantity=None, quote_order_qty=None):
        """
        Membuat order trading baru (Beli atau Jual) di Indodax.
        
        Args:
            symbol (str): Ticker simbol pasangan Indodax tanpa slash (misal 'BTCIDR').
            side (str): Arah transaksi ('BUY' atau 'SELL').
            order_type (str): Tipe order ('LIMIT' atau 'MARKET').
            price (float, optional): Harga per unit untuk order berjenis LIMIT.
            quantity (float, optional): Jumlah koin (base asset) yang akan ditransaksikan.
            quote_order_qty (float, optional): Nominal total IDR untuk MARKET BUY order.
            
        Returns:
            dict: Objek detail order dari server Indodax (orderId, status, executedQty, dll).
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
        }
        if order_type.upper() == "LIMIT":
            params["price"] = str(price)
            params["quantity"] = str(quantity)
        elif order_type.upper() == "MARKET":
            if side.upper() == "BUY" and quote_order_qty:
                params["quoteOrderQty"] = str(int(quote_order_qty))
            elif quantity:
                params["quantity"] = str(quantity)
        return self._v2_request("POST", "/api/v2/order", params)

    def cancel_order(self, symbol, order_id=None, client_order_id=None):
        """
        Membatalkan open order yang masih aktif di exchange.
        
        Args:
            symbol (str): Ticker pasangan Indodax (misal 'BTCIDR').
            order_id (int or str, optional): ID unik order dari Indodax.
            client_order_id (str, optional): Custom ID order dari klien.
            
        Returns:
            dict: Respons pembatalan order dari server.
        """
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        return self._v2_request("DELETE", "/api/v2/order", params)

    def get_open_orders(self, symbol=None):
        """
        Mengambil daftar semua order aktif yang belum selesai tereksekusi.
        
        Args:
            symbol (str, optional): Filter berdasarkan ticker tertentu (misal 'BTCIDR').
            
        Returns:
            dict or list: Daftar objek open orders aktif.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/openOrders", params)

    def get_order(self, symbol, order_id=None, client_order_id=None):
        """
        Mengambil informasi detail dan status eksekusi dari suatu order tertentu.
        
        Args:
            symbol (str): Ticker pasangan Indodax.
            order_id (int or str, optional): ID order Indodax.
            client_order_id (str, optional): Custom client order ID.
            
        Returns:
            dict: Detail status order.
        """
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        return self._v2_request("GET", "/api/v2/order", params)

    def get_my_trades(self, symbol=None, limit=100):
        """
        Mengambil riwayat transaksi individual (trade fills) milik akun pengguna.
        
        Args:
            symbol (str, optional): Filter ticker pasangan Indodax.
            limit (int, optional): Jumlah entri riwayat maksimal. Default 100.
            
        Returns:
            dict or list: Daftar transaksi yang berhasil tereksekusi.
        """
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/myTrades", params)

    def get_order_history(self, symbol=None, limit=100):
        """
        Mengambil riwayat order historis (baik yang filled, cancelled, maupun expired).
        
        Args:
            symbol (str, optional): Filter ticker pasangan Indodax.
            limit (int, optional): Batas jumlah order yang ditampilkan. Default 100.
            
        Returns:
            dict or list: Daftar riwayat order historis.
        """
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/order/histories", params)
