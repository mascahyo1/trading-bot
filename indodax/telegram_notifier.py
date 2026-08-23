"""
Notifier Telegram Khusus Bot Crypto Indodax

Mengirimkan berbagai format pesan notifikasi langsung ke akun / grup Telegram:
- Notifikasi eksekusi order beli/jual/partial sell.
- Notifikasi deteksi sinyal trading baru.
- Ringkasan statistik performa trading & PnL harian.
- Status startup & shutdown bot.
- Peringatan error dan failure sistem.

Author: AI Trading Bot
"""

import logging
import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Kredensial API Telegram dari file lingkungan .env
TELEGRAM_TOKEN = os.getenv("Telegram_Bot_Token", "")
TELEGRAM_CHAT_ID = os.getenv("Telegram_Chat_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


class TelegramNotifier:
    """
    Klien pengirim notifikasi pesan HTML ke Telegram Bot API.
    
    Attributes:
        enabled (bool): Status apakah Telegram Token dan Chat ID tersedia di konfigurasi.
    """

    def __init__(self):
        """
        Inisialisasi TelegramNotifier dan verifikasi ketersediaan kredensial.
        """
        self.enabled = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
        if self.enabled:
            logger.info("Telegram notifier ENABLED")
        else:
            logger.info("Telegram notifier DISABLED")

    def send(self, text, parse_mode="HTML"):
        """
        Mengirim pesan teks ke Telegram melalui endpoint sendMessage.
        
        Args:
            text (str): Teks pesan (HTML terformat).
            parse_mode (str, optional): Mode parser Telegram ('HTML'). Default 'HTML'.
            
        Returns:
            bool: True jika pesan sukses diterima Telegram, False jika gagal.
        """
        if not self.enabled:
            return False

        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return True
                logger.error(f"Telegram API error: {result}")
                return False
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def notify_trade(self, symbol, side, price, amount=None, pnl=None):
        """
        Mengirim notifikasi eksekusi transaksi trading (BUY / SELL / PARTIAL SELL).
        
        Args:
            symbol (str): Simbol pair (misal 'BTC/IDR').
            side (str): Aksi transaksi ('BUY' atau 'SELL').
            price (float): Harga koin saat eksekusi.
            amount (float, optional): Kuantitas koin yang ditransaksikan.
            pnl (float, optional): Nominal PnL terealisasi jika aksi SELL.
        """
        msg = (
            f"<b>INDODAX TRADE</b>\n"
            f"<b>{side}</b> {symbol}\n"
            f"Price: {price:,.0f} IDR\n"
        )
        if amount:
            msg += f"Amount: {amount:.8f}\n"
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            msg += f"PnL: {sign}{pnl:,.0f} IDR\n"
        self.send(msg)

    def notify_signal(self, symbol, signal, confidence, indicators):
        """
        Mengirim notifikasi deteksi sinyal indikator teknikal.
        
        Args:
            symbol (str): Simbol pair.
            signal (str): Arah sinyal ('buy' / 'sell').
            confidence (float): Tingkat confidence (0.0 - 1.0).
            indicators (dict): Data RSI, MACD, dll.
        """
        rsi = str(indicators.get('rsi', 'N/A')).replace('<', '&lt;').replace('>', '&gt;')
        macd = str(indicators.get('macd_histogram', 'N/A')).replace('<', '&lt;').replace('>', '&gt;')
        msg = (
            f"Signal: <b>{signal.upper()}</b> {symbol}\n"
            f"Confidence: {confidence:.0%}\n"
            f"RSI: {rsi} | "
            f"MACD: {macd}\n"
        )
        self.send(msg)

    def notify_summary(self, balance, positions, total_pnl, win_rate, trades):
        """
        Mengirim notifikasi ringkasan akumulasi performa akun bot.
        
        Args:
            balance (float): Saldo kas IDR.
            positions (int): Jumlah open positions saat ini.
            total_pnl (float): Total PnL kumulatif dalam IDR.
            win_rate (float): Win rate persentase.
            trades (int): Jumlah total trade yang sudah selesai.
        """
        sign = "+" if total_pnl >= 0 else ""
        msg = (
            f"<b>INDODAX SUMMARY</b>\n"
            f"Balance: {balance:,.0f} IDR\n"
            f"Open: {positions} positions\n"
            f"PnL: {sign}{total_pnl:,.0f} IDR\n"
            f"Win: {win_rate}% ({trades} trades)\n"
        )
        self.send(msg)

    def notify_portfolio(self, balance, unrealized, total_portfolio, positions):
        """
        Mengirim notifikasi status portofolio lengkap dan floating profit/loss.
        
        Args:
            balance (float): Saldo kas IDR.
            unrealized (float): Floating PnL posisi terbuka.
            total_portfolio (float): Total estimasi kekayaan portofolio.
            positions (dict): Map dari symbol -> objek Position aktif.
        """
        sign_u = "+" if unrealized >= 0 else ""
        msg = (
            f"<b>PORTFOLIO</b>\n"
            f"Cash: {balance:,.0f} IDR\n"
            f"Unrealized: {sign_u}{unrealized:,.0f} IDR\n"
            f"Total: {total_portfolio:,.0f} IDR\n"
        )
        if positions:
            msg += f"\n<b>POSITIONS</b>\n"
            for sym, pos in positions.items():
                if pos.status == "open":
                    msg += f"  {sym}: {pos.amount:.6f} @ {pos.entry_price:,.0f}\n"
        self.send(msg)

    def notify_error(self, message):
        """
        Mengirim notifikasi error kritis atau kegagalan API.
        
        Args:
            message (str): Pesan teks kesalahan.
        """
        msg = f"<b>ERROR</b>\n{message}"
        self.send(msg)

    def notify_start(self, pairs, timeframe):
        """
        Mengirim notifikasi ketika bot Indodax berhasil dinyalakan (startup event).
        
        Args:
            pairs (list): Daftar pair yang dipantau.
            timeframe (str): Timeframe candlestick (misal '15m').
        """
        msg = (
            f"<b>INDODAX BOT STARTED</b>\n"
            f"Pairs: {', '.join(pairs)}\n"
            f"Timeframe: {timeframe}\n"
            f"Notifications: ON"
        )
        self.send(msg)

    def notify_stop(self, reason="User request"):
        """
        Mengirim notifikasi saat bot berhenti beroperasi (shutdown event).
        
        Args:
            reason (str, optional): Alasan penghentian bot. Default 'User request'.
        """
        msg = f"<b>INDODAX</b>\n<b>BOT STOPPED</b>\nReason: {reason}"
        self.send(msg)


def test_telegram():
    """
    Fungsi uji coba untuk memverifikasi apakah notifikasi Telegram dapat terkirim dengan sukses.
    
    Returns:
        bool: True jika berhasil terkirim, False jika gagal.
    """
    tg = TelegramNotifier()
    if not tg.enabled:
        print("Telegram not configured!")
        return False

    msg = (
        "<b>Test Notification</b>\n"
        "Trading bot Telegram integration is working!\n"
        f"Time: working"
    )
    result = tg.send(msg)
    if result:
        print("Telegram test: SUCCESS")
    else:
        print("Telegram test: FAILED")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_telegram()

