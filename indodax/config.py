"""
Konfigurasi Global Bot Trading Crypto Indodax

Modul ini memuat kredensial API, parameter manajemen risiko, bobot strategi hybrid (Teknikal & AI LLM),
daftar pair trading pasar Indodax, serta fungsi utilitas waktu zona Jakarta (WIB / UTC+7).

Author: AI Trading Bot
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# Inisialisasi path direktori kerja dan pemuatan file .env
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(SCRIPT_DIR), ".env"))

# Zona Waktu & Format Tanggal (WIB / UTC+7)
TZ_JAKARTA = timezone(timedelta(hours=7))
DATETIME_FORMAT = "%H:%M:%S %A, %d %B %Y"


def now_jakarta():
    """
    Mengambil objek datetime saat ini dalam zona waktu Asia/Jakarta (WIB / UTC+7).
    
    Returns:
        datetime: Waktu saat ini dengan timezone Jakarta.
    """
    return datetime.now(TZ_JAKARTA)


def format_datetime(dt=None):
    """
    Memformat objek datetime ke dalam representasi string yang rapi.
    
    Args:
        dt (datetime, optional): Objek datetime yang akan diformat. Jika None, menggunakan now_jakarta().
        
    Returns:
        str: String tanggal dan waktu terformat (contoh: '20:30:15 Sunday, 23 August 2026').
    """
    if dt is None:
        dt = now_jakarta()
    return dt.strftime(DATETIME_FORMAT)


# ------------------------------------------------------------------------------
# Kredensial API Indodax (TAPI v2)
# ------------------------------------------------------------------------------
INDODAX_API_KEY = os.getenv("indodax_api_key", "")
INDODAX_API_SECRET = os.getenv("indodax_api_secret", "")

# ------------------------------------------------------------------------------
# Konfigurasi LLM (Artificial Intelligence Market Sentiment Analysis)
# ------------------------------------------------------------------------------
LLM_BASE_URL = os.getenv("llm_base_url", "")
LLM_API_KEY = os.getenv("llm_api_key", "")
LLM_MODEL = os.getenv("llm_model", "LongCat-2.0")

# ------------------------------------------------------------------------------
# Daftar Pasangan Mata Uang Kripto (Trading Pairs)
# ------------------------------------------------------------------------------
# Pasangan utama yang diprioritaskan
TRADING_PAIRS = ["BTC/IDR", "ETH/IDR", "SOL/IDR"]

# Pemetaan simbol CCXT ke format ticker internal Indodax
INDODAX_SYMBOL_MAP = {
    "BTC/IDR": "BTCIDR", "ETH/IDR": "ETHIDR", "SOL/IDR": "SOLIDR",
    "DOGE/IDR": "DOGEIDR", "XRP/IDR": "XRPIDR", "ADA/IDR": "ADAIDR",
    "AVAX/IDR": "AVAXIDR", "DOT/IDR": "DOTIDR", "LINK/IDR": "LINKIDR",
    "LTC/IDR": "LTCIDR", "BCH/IDR": "BCHIDR",
    "UNI/IDR": "UNIIDR", "ATOM/IDR": "ATOMIDR", "FIL/IDR": "FILIDR",
}

# Selang waktu siklus trading loop (dalam detik) dan timeframe candlestick
INTERVAL_SECONDS = 300       # 5 menit per siklus scanning
CANDLESTICK_TIMEFRAME = "15m" # Candlestick 15 menit untuk analisis teknikal

# Universe lengkap aset kripto yang dipantau
ALL_PAIRS = [
    "BTC/IDR", "ETH/IDR", "SOL/IDR", "DOGE/IDR", "XRP/IDR",
    "ADA/IDR", "AVAX/IDR", "DOT/IDR", "LINK/IDR",
    "LTC/IDR", "BCH/IDR", "UNI/IDR", "ATOM/IDR", "FIL/IDR",
]

# Jumlah maksimal aset teratas yang dianalisis oleh AI LLM dalam satu siklus
LLM_TOP_PAIRS = 5

# ------------------------------------------------------------------------------
# Parameter Manajemen Risiko (Risk Management & Position Sizing)
# ------------------------------------------------------------------------------
RISK_PRIMARY_PCT = 0.02      # Alokasi risiko 2% untuk koin utama (BTC, ETH, SOL)
RISK_SECONDARY_PCT = 0.01    # Alokasi risiko 1% untuk koin altcoin sekunder
RISK_PER_TRADE = 0.02        # Batas risiko modal per transaksi tunggal (2%)
STOP_LOSS_PCT = 0.03         # Batas kerugian otomatis: -3% dari harga beli
TAKE_PROFIT_PCT = 0.06       # Target keuntungan otomatis: +6% dari harga beli
TRAILING_STOP_PCT = 0.05     # Trailing stop: 5% di bawah harga puncak tertinggi (high watermark)
MAX_DAILY_LOSS_PCT = 0.05    # Circuit breaker: hentikan trading jika rugi harian mencapai -5%
MAX_OPEN_POSITIONS = 3       # Batas maksimal posisi terbuka secara simultan

# ------------------------------------------------------------------------------
# Ukuran Order & Rebalancing
# ------------------------------------------------------------------------------
POSITION_SIZE_USDT = 500000  # Nilai basis posisi default dalam IDR (500.000 IDR)
MIN_ORDER_IDR = 10000        # Nilai transaksi minimum yang diizinkan sistem Indodax (Rp 10.000)
REBALANCE_PCT = 0.5          # Rasio rebalancing porsi partial sell

# ------------------------------------------------------------------------------
# Bobot Hybrid Scoring Sinyal (Technical vs AI LLM)
# ------------------------------------------------------------------------------
LLM_WEIGHT = 0.40            # Kontribusi 40% dari analisis reasoning LLM
TECHNICAL_WEIGHT = 0.60      # Kontribusi 60% dari indikator teknikal murni (RSI, MACD, EMA, dll.)

# Nama file penyimpanan riwayat transaksi
TRADE_HISTORY_FILE = "trade_history.json"

