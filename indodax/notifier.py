"""
Modul Logger dan Notifier Konsol / File untuk Indodax Bot

Menyediakan:
- `DailyFileHandler`: Logging harian otomatis yang terotasi ke file tanggal baru (`YYYY-MM-DD.log`).
- `cleanup_old_logs`: Pembersihan file log usang yang berumur lebih dari 180 hari.
- `setup_logger`: Konfigurasi root logger dengan format waktu WIB Asia/Jakarta.
- `TradeNotifier`: Logger khusus untuk mencetak event sinyal, trade fill, error, dan summary.

Author: AI Trading Bot
"""

import logging
import os
import glob
from datetime import datetime, timedelta
from config import TZ_JAKARTA

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
MAX_LOG_DAYS = 180


class DailyFileHandler(logging.Handler):
    """
    Custom Logging Handler yang otomatis membuat file log baru setiap berganti hari (WIB / UTC+7).
    
    Attributes:
        log_dir (str): Folder direktori tujuan penyimpanan log.
        _current_date (str): Tanggal file log yang saat ini aktif (format YYYY-MM-DD).
        _file_handler (logging.FileHandler): Instansi FileHandler aktual.
    """

    def __init__(self, log_dir):
        """
        Inisialisasi DailyFileHandler.
        
        Args:
            log_dir (str): Path direktori folder log.
        """
        super().__init__()
        self.log_dir = log_dir
        self._current_date = None
        self._file_handler = None
        self._ensure_dir()
        self._rotate_handler()

    def _ensure_dir(self):
        """Memastikan folder direktori log sudah ada di filesystem."""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

    def _today(self):
        """Mengembalikan tanggal hari ini dalam format YYYY-MM-DD zona Jakarta."""
        return datetime.now(TZ_JAKARTA).strftime("%Y-%m-%d")

    def _rotate_handler(self):
        """Memeriksa pergantian hari dan merotasi file log jika tanggal berubah."""
        today = self._today()
        if today == self._current_date:
            return

        if self._file_handler:
            self._file_handler.close()

        log_file = os.path.join(self.log_dir, f"{today}.log")
        self._file_handler = logging.FileHandler(log_file, encoding="utf-8")
        self._file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
            datefmt="%H:%M:%S %A, %d %B %Y",
        )
        formatter.converter = lambda *args: datetime.now(TZ_JAKARTA).timetuple()
        self._file_handler.setFormatter(formatter)
        self._current_date = today

    def emit(self, record):
        """
        Menerima record log, memeriksa rotasi tanggal, dan menulis log ke file.
        
        Args:
            record (logging.LogRecord): Objek data log.
        """
        self._rotate_handler()
        if self._file_handler:
            self._file_handler.emit(record)

    def close(self):
        """Menutup handler file dan membersihkan resource."""
        if self._file_handler:
            self._file_handler.close()
        super().close()


def cleanup_old_logs():
    """
    Menghapus file-file log yang telah berusia lebih dari `MAX_LOG_DAYS` (180 hari) untuk menghemat storage.
    """
    cutoff = datetime.now(TZ_JAKARTA) - timedelta(days=MAX_LOG_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    if not os.path.exists(LOG_DIR):
        return

    for log_file in glob.glob(os.path.join(LOG_DIR, "*.log")):
        basename = os.path.basename(log_file)
        date_str = basename.replace(".log", "")
        try:
            if date_str < cutoff_str:
                os.remove(log_file)
        except Exception:
            pass


def setup_logger():
    """
    Mengonfigurasi dan menginisialisasi root logger aplikasi.
    
    Menghubungkan dua handler:
    1. DailyFileHandler untuk pencatatan persistent ke disk.
    2. StreamHandler untuk output visual langsung ke konsol/terminal.
    
    Returns:
        logging.Logger: Instansi root logger yang telah terkonfigurasi.
    """
    cleanup_old_logs()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    daily_handler = DailyFileHandler(LOG_DIR)
    root_logger.addHandler(daily_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s",
        datefmt="%H:%M:%S %A, %d %B %Y",
    )
    formatter.converter = lambda *args: datetime.now(TZ_JAKARTA).timetuple()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return root_logger


class TradeNotifier:
    """
    Notifier untuk mencetak format event trading terstandarisasi ke log console dan file.
    
    Attributes:
        logger (logging.Logger): Instansi logger bernama 'notifier'.
    """

    def __init__(self):
        """Inisialisasi TradeNotifier."""
        self.logger = logging.getLogger("notifier")

    def notify_trade(self, symbol, action, price, amount=None, pnl=None):
        """
        Mencatat eksekusi transaksi (BUY, SELL, PARTIAL SELL, DCA).
        
        Args:
            symbol (str): Pair crypto.
            action (str): Jenis aksi order.
            price (float): Harga eksekusi.
            amount (float, optional): Kuantitas koin.
            pnl (float, optional): Nominal PnL terealisasi dalam IDR.
        """
        msg = f"TRADE: {action.upper()} {symbol} @ {price:.2f}"
        if amount:
            msg += f" | Amount: {amount}"
        if pnl is not None:
            msg += f" | PnL: {pnl:+.2f} IDR"
        self.logger.info(msg)

    def notify_signal(self, symbol, signal, confidence, indicators, llm_result=None):
        """
        Mencatat deteksi sinyal pasar hasil evaluasi teknikal & LLM.
        
        Args:
            symbol (str): Pair crypto.
            signal (str): Arah sinyal ('BUY', 'SELL', 'HOLD').
            confidence (float): Tingkat keyakinan sinyal (0.0 - 1.0).
            indicators (dict): Nilai indikator teknikal (RSI, MACD).
            llm_result (dict, optional): Hasil evaluasi LLM.
        """
        msg = (
            f"SIGNAL: {signal.upper()} {symbol} | Confidence: {confidence:.1%} | "
            f"RSI={indicators.get('rsi', 'N/A')} MACD={indicators.get('macd_histogram', 'N/A')}"
        )
        if llm_result:
            msg += (
                f" | LLM: {llm_result.get('signal', 'N/A').upper()} "
                f"conf={llm_result.get('confidence', 0):.1%} "
                f"risk={llm_result.get('risk_level', 'N/A')}"
            )
        self.logger.info(msg)

    def notify_error(self, message):
        """
        Mencatat pesan kesalahan atau exception sistem.
        
        Args:
            message (str): Pesan error.
        """
        self.logger.error(f"ERROR: {message}")

    def notify_summary(self, risk_manager):
        """
        Mencatat ringkasan performa portofolio dan akumulasi trading.
        
        Args:
            risk_manager (RiskManager): Instansi pengelola risiko.
        """
        total_pnl = risk_manager.get_total_pnl()
        win_rate = risk_manager.get_win_rate()
        open_count = risk_manager.get_open_positions_count()
        total_trades = len(risk_manager.trade_history)

        self.logger.info(
            f"SUMMARY: Open={open_count} | Total Trades={total_trades} | "
            f"Win Rate={win_rate}% | Total PnL={total_pnl:+.2f} IDR"
        )

