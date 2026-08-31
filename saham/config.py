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
  * Beli: Total 0.1513% (broker 0.10% + levy 0.0433% + PPN 12% broker, PMK 131/2024)
  * Jual: Total 0.2513% (beli 0.1513% + PPh Final 0.10%)
  * Round-trip fee: ~0.4026%

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
# Saham murah terjangkau untuk modal kecil (price < 1000 => lot < 100rb)
AFFORDABLE_STOCKS = [
    "KLBF.JK", "ADHI.JK", "BUMI.JK", "BRMS.JK", "DEWA.JK",
    "BRPT.JK", "GOTO.JK", "PADI.JK", "BBRI.JK", "PGAS.JK", "ANTM.JK",
]

ALL_STOCKS = [
    "BBCA.JK", "BMRI.JK", "BBRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "INDF.JK", "KLBF.JK", "ICBP.JK", "ANTM.JK",
    "INCO.JK", "PGAS.JK", "PTBA.JK", "SMGR.JK", "ADHI.JK",
    "INTP.JK", "EXCL.JK", "ISAT.JK", "JSMR.JK", "CPIN.JK",
    "BUMI.JK", "BRMS.JK", "DEWA.JK", "BRPT.JK", "GOTO.JK", "PADI.JK",
]

# ==============================================================================
# Filter SOLID untuk screener (tambahkan 31-08-2026: hindari gocap tidur Vol 0)
# ==============================================================================
# Harga 50-2.000 = murah tapi tidak gocap 2-38, Vol >1M = liquid, Change -10%..+20% = tidak pump/dump
SOLID_PRICE_MIN = 50        # Rp 50  = 1 lot Rp 5.000 (modal 76k masih kebeli)
SOLID_PRICE_MAX = 2000      # Rp 2.000 = 1 lot Rp 200.000 (batas cash 76k akan Cannot afford, auto skip)
SOLID_VOL_MIN = 1000000     # 1 juta lembar/hari (~10 lot) minimal liquid
SOLID_CHANGE_MIN_PCT = -10  # skip dump <-10%
SOLID_CHANGE_MAX_PCT = 20   # skip pump >+20% (hindari FOMO pucuk)

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
INTERVAL_SECONDS = 300   # Interval siklus: 5 menit heartbeat (scan beli hanya saat BEI buka)
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
# Biaya Transaksi - ATURAN TERBARU (ajaib.co.id/biaya, PMK 131/2024 per 1 Jan 2025)
# Beli 0.1513% | Jual 0.2513% | Round-trip 0.4026%
# Rincian: broker 0.10% + levy BEI/KPEI/KSEI 0.0433% + PPN broker 12% + PPh final jual 0.10% (hanya jual)
# Beli = 0.10*1.12 + 0.0433 = 0.1553%? Tapi Ajaib publish 0.1513% (sudah final), pakai angka publish.
# Jual = beli + PPh 0.10% = 0.2513%
BUY_TOTAL_FEE_PCT = 0.001513   # Total beli 0.1513% (sudah termasuk levy + PPN 12% broker)
SELL_TOTAL_FEE_PCT = 0.002513  # Total jual 0.2513% (beli + PPh final 0.10%)
# Komponen derivasi untuk display (tidak dipakai hitung, hanya info)
BUY_BROKER_FEE_PCT = 0.0010
SELL_BROKER_FEE_PCT = 0.0010
BUY_CLEARENCE_FEE_PCT = 0.000433  # levy 0.0433%
SELL_CLEARENCE_FEE_PCT = 0.000433
BUY_TAX_FEE_PCT = 0.00008   # sisa PPN (approx, angka final pakai TOTAL di atas)
SELL_TAX_FEE_PCT = 0.00008
SELL_VAT_FEE_PCT = 0.00012  # PPN 12% dari broker
SELL_PPH_FEE_PCT = 0.001

# Total bolak-balik 0.4026%
ROUND_TRIP_FEE_PCT = 0.004026  # 0.1513 + 0.2513

FEE_WARNING_THRESHOLD_PCT = 0.5 # Ambang batas peringatan jika fee memakan profit

# ==============================================================================
# Path Otomatisasi Browser Ajaib (Playwright Session)
# ==============================================================================
AJAIB_SESSION_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "ajaib", "session")
AJAIB_SESSION_FILE = os.path.join(AJAIB_SESSION_DIR, "storage-state.json")
AJAIB_PERSISTENT_PROFILE = os.path.join(os.path.dirname(SCRIPT_DIR), "ajaib", "persistent-profile")
AJAIB_BASE_URL = "https://invest.ajaib.co.id"
AJAIB_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
AJAIB_PROXY = os.getenv("AJAIB_PROXY", "")  # socks5://127.0.0.1:1080 jika via tunnel

