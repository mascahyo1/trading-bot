import hashlib
import hmac
import time
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
import ccxt
from config import INDODAX_API_KEY, INDODAX_API_SECRET

logger = logging.getLogger(__name__)

BASE_URL = "https://api.indodax.com"


class IndodaxExchange:
    def __init__(self):
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
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(f"API v2 HTTP {e.code}: {body[:300]}")
            return {"error": True, "code": e.code, "message": body}
        except Exception as e:
            logger.error(f"API v2 error: {e}")
            return {"error": True, "message": str(e)}

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
