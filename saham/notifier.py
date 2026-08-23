"""
Modul Logger dan Notifier Konsol / File untuk Bot Saham Indonesia

Menyediakan:
- `DailyFileHandler`: Custom file logging dengan rotasi tanggal otomatis berbasis WIB Asia/Jakarta.
- `cleanup_old_logs`: Retensi log maksimal 180 hari untuk efisiensi disk.
- `setup_logger`: Inisialisasi logging konsol dan file harian.
- `TradeNotifier`: Logger khusus untuk mencatat event sinyal teknikal, trade fill, error, dan summary portofolio saham.

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
    Custom Logging Handler yang otomatis membuat file log harian baru (YYYY-MM-DD.log).
    
    Attributes:
        log_dir (str): Folder direktori file log.
        _current_date (str): Tanggal file log yang sedang aktif.
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
        """Memastikan folder direktori log ada di filesystem."""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

    def _today(self):
        """Mengembalikan tanggal hari ini dalam format YYYY-MM-DD WIB."""
        return datetime.now(TZ_JAKARTA).strftime("%Y-%m-%d")

    def _rotate_handler(self):
        """Memeriksa pergantian hari dan membuat file log baru jika tanggal berubah."""
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
    Menghapus file-file log yang telah berusia lebih dari MAX_LOG_DAYS (180 hari).
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
    Mengonfigurasi dan menginisialisasi root logger aplikasi bot saham.
    
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
    Notifier untuk mencetak format event trading saham terstandarisasi ke log console dan file.
    
    Attributes:
        logger (logging.Logger): Instansi logger bernama 'notifier'.
    """

    def __init__(self):
        """Inisialisasi TradeNotifier."""
        self.logger = logging.getLogger("notifier")

    def notify_trade(self, symbol, action, price, lots=None, pnl=None):
        """
        Mencatat eksekusi transaksi (BUY, SELL, PARTIAL SELL, DCA).
        
        Args:
            symbol (str): Simbol saham.
            action (str): Aksi transaksi.
            price (float): Harga per lembar.
            lots (int, optional): Jumlah lot saham.
            pnl (float, optional): Net PnL terealisasi dalam IDR.
        """
        msg = f"TRADE: {action.upper()} {symbol} @ {price:,.0f}"
        if lots:
            msg += f" | Lots: {lots}"
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            msg += f" | PnL (net): {sign}{pnl:,.0f} IDR"
        self.logger.info(msg)

    def notify_signal(self, symbol, signal, confidence, indicators):
        """
        Mencatat deteksi sinyal pasar hasil evaluasi teknikal.
        
        Args:
            symbol (str): Simbol saham.
            signal (str): Arah sinyal ('BUY', 'SELL', 'HOLD').
            confidence (float): Tingkat confidence (0.0 - 1.0).
            indicators (dict): Data RSI, MACD, dll.
        """
        msg = (
            f"SIGNAL: {signal.upper()} {symbol} | Confidence: {confidence:.1%} | "
            f"RSI={indicators.get('rsi', 'N/A')} MACD={indicators.get('macd_histogram', 'N/A')}"
        )
        self.logger.info(msg)

    def notify_error(self, message):
        """
        Mencatat pesan error atau exception ke logger.
        
        Args:
            message (str): Pesan kesalahan.
        """
        self.logger.error(f"ERROR: {message}")

    def notify_summary(self, risk_manager, cash_balance=None):
        """
        Mencatat ringkasan akumulasi performa akun dan portofolio saham.
        
        Args:
            risk_manager (RiskManager): Instansi pengelola risiko.
            cash_balance (float, optional): Saldo kas IDR.
        """
        total_pnl = risk_manager.get_total_pnl()
        win_rate = risk_manager.get_win_rate()
        open_count = risk_manager.get_open_positions_count()
        total_trades = len(risk_manager.trade_history)

        msg = (
            f"SUMMARY: Open={open_count} | Total Trades={total_trades} | "
            f"Win Rate={win_rate}% | Total PnL={total_pnl:+,.0f} IDR"
        )
        if cash_balance is not None:
            msg += f" | Cash: {cash_balance:,.0f} IDR"
        self.logger.info(msg)

