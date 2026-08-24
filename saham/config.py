"""
Konfigurasi Global Bot Saham Indonesia (IDX / BEI via Ajaib & Yahoo Finance)

Menyimpan seluruh konstanta konfigurasi:
- Zona waktu Asia/Jakarta (WIB) dan format waktu standar.
- Kredensial AI LLM (LongCat-2.0 / OpenAI compatible) dan Telegram Bot.
- Daftar ticker saham Indonesia (LQ45 / Bluechip) dan pemetaan kode emiten.
- Manajemen risiko (Risk per trade, Stop Loss 3%, Take Profit 8%, Trailing Stop 5%, Max 5 Posisi).
- Aturan lot bursa (1 Lot = 100 Lembar) dan ukuran posisi per transaksi (Rp 1.000.000).
- Pembobotan sinyal: 70% Analisis Teknikal + 30% AI LLM.
- Perhitungan struktur fee transaksi Ajaib Sekuritas:
  * Beli: Total 0.14% (Broker 0.10% + Kliring/BEI 0.02% + Biaya Pajak 0.02%)
  * Jual: Total 0.34% (Broker 0.10% + Kliring/BEI 0.02% + Pajak 0.02% + PPN 0.10% + PPh Final 0.10%)
  * Round-trip fee: ~0.48%

Author: AI Trading Bot
"""

import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
load_dotenv(os.path.join(os.path.dirname(SCRIPT_DIR), ".env"))

# Konfigurasi Waktu (WIB / UTC+7)
TZ_JAKARTA = timezone(timedelta(hours=7))
DATETIME_FORMAT = "%H:%M:%S %A, %d %B %Y"


def now_jakarta():
    """
    Mendapatkan objek datetime saat ini dalam zona waktu Asia/Jakarta (WIB / UTC+7).
    
    Returns:
        datetime: Waktu lokal Jakarta saat ini dengan informasi timezone.
    """
    return datetime.now(TZ_JAKARTA)


def format_datetime(dt=None):
    """
    Memformat objek datetime menjadi string dengan format standar Indonesia.
    
    Format: HH:MM:SS Hari, DD Bulan YYYY (contoh: '14:30:00 Senin, 23 Agustus 2026').
    
    Args:
        dt (datetime, optional): Objek datetime yang akan diformat. Jika None, menggunakan waktu saat ini.
        
    Returns:
        str: String tanggal dan waktu terformat.
    """
    if dt is None:
        dt = now_jakarta()
    return dt.strftime(DATETIME_FORMAT)


# ==============================================================================
# Konfigurasi Kredensial AI LLM & Telegram
# ==============================================================================
LLM_BASE_URL = os.getenv("llm_base_url", "")
LLM_API_KEY = os.getenv("llm_api_key", "")
LLM_MODEL = os.getenv("llm_model", "LongCat-2.0")

TELEGRAM_TOKEN = os.getenv("Telegram_Bot_Token", "")
TELEGRAM_CHAT_ID = os.getenv("Telegram_Chat_ID", "")

# ==============================================================================
# Daftar Instrumen Saham yang Diperdagangkan (IDX / Yahoo Finance Symbol)
# ==============================================================================
# Saham prioritas utama untuk trading aktif
TRADING_STOCKS = [
    "BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "INDF.JK", "KLBF.JK", "ICBP.JK", "ANTM.JK",
]

# Saham semesta pemindaian pasar lengkap (Universe of Stocks)
ALL_STOCKS = [
    "BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "INDF.JK", "KLBF.JK", "ICBP.JK", "ANTM.JK",
    "INCO.JK", "PGAS.JK", "PTBA.JK", "SMGR.JK", "ADHI.JK",
    "INTP.JK", "EXCL.JK", "ISAT.JK", "JSMR.JK", "CPIN.JK",
]

# Pemetaan dari simbol Yahoo Finance (*.JK) ke kode ticker murni di platform Ajaib Sekuritas
STOCK_CODE_MAP = {
    "BBCA.JK": "BBCA", "BMRI.JK": "BMRI", "BBRI.JK": "BBRI",
    "TLKM.JK": "TLKM", "ASII.JK": "ASII", "UNVR.JK": "UNVR",
    "INDF.JK": "INDF", "KLBF.JK": "KLBF", "ICBP.JK": "ICBP",
    "ANTM.JK": "ANTM", "INCO.JK": "INCO", "PGAS.JK": "PGAS",
    "PTBA.JK": "PTBA", "SMGR.JK": "SMGR", "ADHI.JK": "ADHI",
    "INTP.JK": "INTP", "EXCL.JK": "EXCL", "ISAT.JK": "ISAT",
    "JSMR.JK": "JSMR", "CPIN.JK": "CPIN",
}

# ==============================================================================
# Parameter Siklus & Data Historis
# ==============================================================================
INTERVAL_SECONDS = 1800  # Interval siklus scanning bot (5 menit)
LOOKBACK_DAYS = 90      # Rentang data historis candlestick harian (90 hari)

# ==============================================================================
# Parameter Manajemen Risiko Saham
# ==============================================================================
RISK_PER_TRADE = 0.02       # Maksimal risiko modal per satu transaksi (2%)
STOP_LOSS_PCT = 0.03        # Batas Stop Loss standar (-3%)
TAKE_PROFIT_PCT = 0.08      # Target Take Profit standar (+8%)
TRAILING_STOP_PCT = 0.05    # Toleransi trailing stop dari titik tertinggi (+5%)
MAX_DAILY_LOSS_PCT = 0.05   # Batas kerugian harian sebelum bot berhenti membuka posisi baru (-5%)
MAX_OPEN_POSITIONS = 5      # Maksimal jumlah emiten yang dipegang bersamaan (5 posisi)

POSITION_SIZE_IDR = 1000000 # Alokasi modal beli default per posisi (Rp 1.000.000)
MIN_ORDER_IDR = 75000       # Nilai order minimum untuk beli saham
LOT_SIZE = 100              # Ukuran 1 Lot saham di Bursa Efek Indonesia = 100 lembar

# ==============================================================================
# Bobot Sinyal Hybrid (Teknikal + LLM)
# ==============================================================================
LLM_WEIGHT = 0.30           # Bobot keyakinan AI LLM (30%)
TECHNICAL_WEIGHT = 0.70     # Bobot indikator teknikal murni (70%)

TRADE_HISTORY_FILE = "trade_history.json"

# ==============================================================================
# Struktur Fee Transaksi Saham Ajaib Sekuritas
# ==============================================================================
# Biaya Transaksi Pembelian:
BUY_BROKER_FEE_PCT = 0.0010     # Broker fee beli (0.10%)
BUY_CLEARENCE_FEE_PCT = 0.0002  # BEI / KPEI / KSEI levy (0.02%)
BUY_TAX_FEE_PCT = 0.0002        # Pajak transaksi beli (0.02%)
BUY_TOTAL_FEE_PCT = BUY_BROKER_FEE_PCT + BUY_CLEARENCE_FEE_PCT + BUY_TAX_FEE_PCT # Total Beli: ~0.14%

# Biaya Transaksi Penjualan:
SELL_BROKER_FEE_PCT = 0.0010    # Broker fee jual (0.10%)
SELL_CLEARENCE_FEE_PCT = 0.0002 # BEI / KPEI / KSEI levy (0.02%)
SELL_TAX_FEE_PCT = 0.0002       # Pajak reguler jual (0.02%)
SELL_VAT_FEE_PCT = 0.001        # PPN transaksi jual (0.10%)
SELL_PPH_FEE_PCT = 0.001        # PPh Final penjualan saham (0.10%)
SELL_TOTAL_FEE_PCT = SELL_BROKER_FEE_PCT + SELL_CLEARENCE_FEE_PCT + SELL_TAX_FEE_PCT + SELL_VAT_FEE_PCT + SELL_PPH_FEE_PCT # Total Jual: ~0.34%

# Total biaya bolak-balik (Round-trip fee beli + jual): ~0.48%
ROUND_TRIP_FEE_PCT = BUY_TOTAL_FEE_PCT + SELL_TOTAL_FEE_PCT

FEE_WARNING_THRESHOLD_PCT = 0.5 # Ambang batas peringatan jika fee memakan profit

# ==============================================================================
# Path Otomatisasi Browser Ajaib (Playwright Session)
# ==============================================================================
AJAIB_SESSION_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "ajaib", "session")
AJAIB_SESSION_FILE = os.path.join(AJAIB_SESSION_DIR, "storage-state.json")
AJAIB_BASE_URL = "https://invest.ajaib.co.id"

