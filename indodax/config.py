import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(SCRIPT_DIR), ".env"))

TZ_JAKARTA = timezone(timedelta(hours=7))
DATETIME_FORMAT = "%H:%M:%S %A, %d %B %Y"

def now_jakarta():
    return datetime.now(TZ_JAKARTA)

def format_datetime(dt=None):
    if dt is None:
        dt = now_jakarta()
    return dt.strftime(DATETIME_FORMAT)

INDODAX_API_KEY = os.getenv("indodax_api_key", "")
INDODAX_API_SECRET = os.getenv("indodax_api_secret", "")

LLM_BASE_URL = os.getenv("llm_base_url", "")
LLM_API_KEY = os.getenv("llm_api_key", "")
LLM_MODEL = os.getenv("llm_model", "LongCat-2.0")

TRADING_PAIRS = ["BTC/IDR", "ETH/IDR", "SOL/IDR"]
INDODAX_SYMBOL_MAP = {
    "BTC/IDR": "BTCIDR", "ETH/IDR": "ETHIDR", "SOL/IDR": "SOLIDR",
    "DOGE/IDR": "DOGEIDR", "XRP/IDR": "XRPIDR", "ADA/IDR": "ADAIDR",
    "AVAX/IDR": "AVAXIDR", "DOT/IDR": "DOTIDR", "LINK/IDR": "LINKIDR",
    "LTC/IDR": "LTCIDR", "BCH/IDR": "BCHIDR",
    "UNI/IDR": "UNIIDR", "ATOM/IDR": "ATOMIDR", "FIL/IDR": "FILIDR",
}
INTERVAL_SECONDS = 300
CANDLESTICK_TIMEFRAME = "15m"

ALL_PAIRS = [
    "BTC/IDR", "ETH/IDR", "SOL/IDR", "DOGE/IDR", "XRP/IDR",
    "ADA/IDR", "AVAX/IDR", "DOT/IDR", "LINK/IDR",
    "LTC/IDR", "BCH/IDR", "UNI/IDR", "ATOM/IDR", "FIL/IDR",
]

LLM_TOP_PAIRS = 5
RISK_PRIMARY_PCT = 0.02
RISK_SECONDARY_PCT = 0.01
RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06
TRAILING_STOP_PCT = 0.05
MAX_DAILY_LOSS_PCT = 0.05
MAX_OPEN_POSITIONS = 3

POSITION_SIZE_USDT = 500000
MIN_ORDER_IDR = 10000

LLM_WEIGHT = 0.40
TECHNICAL_WEIGHT = 0.60

LOG_FILE = "trading_bot.log"
TRADE_HISTORY_FILE = "trade_history.json"
