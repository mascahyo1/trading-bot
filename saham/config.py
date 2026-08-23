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


LLM_BASE_URL = os.getenv("llm_base_url", "")
LLM_API_KEY = os.getenv("llm_api_key", "")
LLM_MODEL = os.getenv("llm_model", "LongCat-2.0")

TELEGRAM_TOKEN = os.getenv("Telegram_Bot_Token", "")
TELEGRAM_CHAT_ID = os.getenv("Telegram_Chat_ID", "")

TRADING_STOCKS = [
    "BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "INDF.JK", "KLBF.JK", "ICBP.JK", "ANTM.JK",
]

ALL_STOCKS = [
    "BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "INDF.JK", "KLBF.JK", "ICBP.JK", "ANTM.JK",
    "INCO.JK", "PGAS.JK", "PTBA.JK", "SMGR.JK", "ADHI.JK",
    "INTP.JK", "EXCL.JK", "ISAT.JK", "JSMR.JK", "CPIN.JK",
]

STOCK_CODE_MAP = {
    "BBCA.JK": "BBCA", "BMRI.JK": "BMRI", "BBRI.JK": "BBRI",
    "TLKM.JK": "TLKM", "ASII.JK": "ASII", "UNVR.JK": "UNVR",
    "INDF.JK": "INDF", "KLBF.JK": "KLBF", "ICBP.JK": "ICBP",
    "ANTM.JK": "ANTM", "INCO.JK": "INCO", "PGAS.JK": "PGAS",
    "PTBA.JK": "PTBA", "SMGR.JK": "SMGR", "ADHI.JK": "ADHI",
    "INTP.JK": "INTP", "EXCL.JK": "EXCL", "ISAT.JK": "ISAT",
    "JSMR.JK": "JSMR", "CPIN.JK": "CPIN",
}

INTERVAL_SECONDS = 300
LOOKBACK_DAYS = 90

RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.08
TRAILING_STOP_PCT = 0.05
MAX_DAILY_LOSS_PCT = 0.05
MAX_OPEN_POSITIONS = 5

POSITION_SIZE_IDR = 1000000
MIN_ORDER_IDR = 75000
LOT_SIZE = 100

LLM_WEIGHT = 0.30
TECHNICAL_WEIGHT = 0.70

TRADE_HISTORY_FILE = "trade_history.json"

BUY_BROKER_FEE_PCT = 0.0010
BUY_CLEARENCE_FEE_PCT = 0.0002
BUY_TAX_FEE_PCT = 0.0002
BUY_TOTAL_FEE_PCT = BUY_BROKER_FEE_PCT + BUY_CLEARENCE_FEE_PCT + BUY_TAX_FEE_PCT

SELL_BROKER_FEE_PCT = 0.0010
SELL_CLEARENCE_FEE_PCT = 0.0002
SELL_TAX_FEE_PCT = 0.0002
SELL_VAT_FEE_PCT = 0.001
SELL_PPH_FEE_PCT = 0.001
SELL_TOTAL_FEE_PCT = SELL_BROKER_FEE_PCT + SELL_CLEARENCE_FEE_PCT + SELL_TAX_FEE_PCT + SELL_VAT_FEE_PCT + SELL_PPH_FEE_PCT

ROUND_TRIP_FEE_PCT = BUY_TOTAL_FEE_PCT + SELL_TOTAL_FEE_PCT

FEE_WARNING_THRESHOLD_PCT = 0.5

AJAIB_SESSION_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "ajaib", "session")
AJAIB_SESSION_FILE = os.path.join(AJAIB_SESSION_DIR, "storage-state.json")
AJAIB_BASE_URL = "https://invest.ajaib.co.id"
