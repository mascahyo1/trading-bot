import os
from dotenv import load_dotenv

load_dotenv()

INDODAX_API_KEY = os.getenv("INDODAX_API_KEY", "")
INDODAX_API_SECRET = os.getenv("INDODAX_API_SECRET", "")

LLM_BASE_URL = os.getenv("llm_base_url", "")
LLM_API_KEY = os.getenv("llm_api_key", "")
LLM_MODEL = os.getenv("llm_model", "LongCat-2.0")

TRADING_PAIRS = ["BTC/IDR", "ETH/IDR", "SOL/IDR"]
INDODAX_SYMBOL_MAP = {"BTC/IDR": "BTCIDR", "ETH/IDR": "ETHIDR", "SOL/IDR": "SOLIDR"}
INTERVAL_SECONDS = 900
CANDLESTICK_TIMEFRAME = "15m"

RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.03
TAKE_PROFIT_PCT = 0.06
MAX_OPEN_POSITIONS = 3

POSITION_SIZE_USDT = 500000
MIN_ORDER_IDR = 10000

LLM_WEIGHT = 0.40
TECHNICAL_WEIGHT = 0.60

LOG_FILE = "trading_bot.log"
TRADE_HISTORY_FILE = "trade_history.json"
