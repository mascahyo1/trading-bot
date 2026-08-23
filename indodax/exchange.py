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
        return hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    @api_retry
    def _v2_request(self, method, endpoint, params=None):
        url = BASE_URL + endpoint
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

        if params is None:
            params = {}

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
        try:
            ohlcv = self.ccxt.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            if ohlcv and len(ohlcv) > 0:
                return ohlcv
            return None
        except Exception:
            return None

    def fetch_ticker(self, symbol):
        try:
            ticker = self.ccxt.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"Ticker error for {symbol}: {e}")
            return None

    def get_balance(self):
        return self._v2_request("GET", "/api/v2/account")

    def get_idr_balance(self):
        result = self.get_balance()
        if result.get("error"):
            return 0
        for b in result.get("balances", []):
            if b.get("asset") == "IDR":
                return float(b.get("free", 0))
        return 0

    def create_order(self, symbol, side, order_type, price=None, quantity=None, quote_order_qty=None):
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
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        return self._v2_request("DELETE", "/api/v2/order", params)

    def get_open_orders(self, symbol=None):
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/openOrders", params)

    def get_order(self, symbol, order_id=None, client_order_id=None):
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = str(order_id)
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        return self._v2_request("GET", "/api/v2/order", params)

    def get_my_trades(self, symbol=None, limit=100):
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/myTrades", params)

    def get_order_history(self, symbol=None, limit=100):
        params = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        return self._v2_request("GET", "/api/v2/order/histories", params)
