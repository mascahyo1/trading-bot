"""
Notifier Telegram Khusus Bot Saham Indonesia (IDX / BEI)

Mengirimkan berbagai format pesan notifikasi terstruktur ke Telegram:
- Notifikasi eksekusi beli/jual dengan rincian biaya fee Ajaib (beli 0.14%, jual 0.34%).
- Laporan rincian aset per emiten beserta estimasi break-even price dan net floating PnL.
- Notifikasi pembukaan (09:00 WIB) & penutupan pasar saham Indonesia (16:00 WIB).
- Ringkasan statistik performa trading saham (Win Rate, Total PnL Net, Total Fees).
- Peringatan error dan event startup/shutdown bot.

Author: AI Trading Bot
"""

import logging
import json
import urllib.request
import urllib.error
import os
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, now_jakarta, format_datetime

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


class TelegramNotifier:
    """
    Klien pengirim notifikasi pesan HTML ke Telegram Bot API untuk trading saham.
    
    Attributes:
        token (str): Token bot Telegram.
        chat_id (str): Chat ID penerima notifikasi.
        enabled (bool): Status apakah kredensial Telegram valid.
    """

    def __init__(self):
        """
        Inisialisasi TelegramNotifier bot saham.
        """
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        if self.enabled:
            logger.info("Telegram notifier ENABLED")
        else:
            logger.info("Telegram notifier DISABLED")

    def send(self, text, parse_mode="HTML"):
        """
        Mengirim pesan teks ke Telegram melalui endpoint sendMessage.
        
        Args:
            text (str): Teks pesan HTML.
            parse_mode (str, optional): Mode parse Telegram. Default 'HTML'.
            
        Returns:
            bool: True jika berhasil, False jika gagal.
        """
        if not self.enabled:
            return False

        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
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

    def notify_trade(self, symbol, side, price, lots=None, pnl=None, fees=None):
        """
        Mengirim notifikasi eksekusi order saham (BUY / SELL / DCA) beserta rincian biaya fee.
        
        Args:
            symbol (str): Simbol saham.
            side (str): Aksi transaksi.
            price (float): Harga per lembar saham.
            lots (int, optional): Jumlah lot saham.
            pnl (float, optional): Net profit/loss jika order jual.
            fees (float, optional): Total nominal biaya transaksi.
        """
        from config import BUY_TOTAL_FEE_PCT, SELL_TOTAL_FEE_PCT
        code = symbol.replace(".JK", "")
        msg = (
            f"<b>SAHAM TRADE</b>\n"
            f"<b>{side}</b> {code}\n"
            f"Price: {price:,.0f} IDR\n"
        )
        if lots:
            shares = lots * 100
            value = price * shares
            msg += f"Lots: {lots} ({shares} shares)\n"
            msg += f"Value: {value:,.0f} IDR\n"
            if side.upper() in ("BUY", "PARTIAL SELL"):
                est_fees = value * BUY_TOTAL_FEE_PCT
                msg += f"Est. Biaya Beli: {est_fees:,.0f} IDR ({BUY_TOTAL_FEE_PCT*100:.2f}%)\n"
            if side.upper() in ("SELL", "PARTIAL SELL"):
                est_fees = value * SELL_TOTAL_FEE_PCT
                msg += f"Est. Biaya Jual: {est_fees:,.0f} IDR ({SELL_TOTAL_FEE_PCT*100:.2f}%)\n"
        if pnl is not None:
            sign = "+" if pnl >= 0 else ""
            msg += f"PnL (net): {sign}{pnl:,.0f} IDR\n"
        if fees is not None:
            msg += f"Total Biaya: {fees:,.0f} IDR\n"
        self.send(msg)

    def notify_signal(self, symbol, signal, confidence, indicators):
        """
        Mengirim notifikasi deteksi sinyal indikator teknikal saham.
        
        Args:
            symbol (str): Simbol saham.
            signal (str): Arah sinyal.
            confidence (float): Tingkat confidence (0.0 - 1.0).
            indicators (dict): Data RSI, MACD, dll.
        """
        code = symbol.replace(".JK", "")
        rsi = str(indicators.get('rsi', 'N/A')).replace('<', '&lt;').replace('>', '&gt;')
        macd = str(indicators.get('macd_histogram', 'N/A')).replace('<', '&lt;').replace('>', '&gt;')
        msg = (
            f"Signal: <b>{signal.upper()}</b> {code}\n"
            f"Confidence: {confidence:.0%}\n"
            f"RSI: {rsi} | MACD: {macd}\n"
        )
        self.send(msg)

    def notify_portfolio_detail(self, cash_balance, position_details, grand_total):
        """
        Mengirim laporan rincian lengkap seluruh aset saham (Lots, Nilai, Net PnL, Break-Even).
        
        Args:
            cash_balance (float): Saldo kas IDR.
            position_details (dict): Map data rincian setiap saham.
            grand_total (float): Total nilai portofolio bruto.
        """
        from config import BUY_TOTAL_FEE_PCT, SELL_TOTAL_FEE_PCT, ROUND_TRIP_FEE_PCT

        lines = [
            f"<b>📊 LAPORAN ASET SAHAM</b>",
            f"⏰ {format_datetime()}",
            f"",
            f"<b>💰 CASH: {cash_balance:,.0f} IDR</b>",
            f"",
        ]

        total_est_sell_fees = 0

        if position_details:
            lines.append("<b>📈 PER SAHAM:</b>")
            lines.append("")

            sorted_positions = sorted(
                position_details.items(),
                key=lambda x: x[1]["value"],
                reverse=True
            )

            for symbol, detail in sorted_positions:
                pnl_sign = "+" if detail["pnl"] >= 0 else ""
                pnl_emoji = "🟢" if detail["pnl"] >= 0 else "🔴"
                est_sell_fees = detail.get("est_sell_fees", 0)
                total_est_sell_fees += est_sell_fees
                break_even = detail.get("break_even", 0)
                entry_market = detail.get("entry_price_market", 0)
                entry_cost = detail.get("entry_price", 0)
                current = detail.get("current_price", 0)

                lines.append(
                    f"{pnl_emoji} <b>{detail['code']}</b>"
                )
                lines.append(
                    f"   Lot: {detail['lots']} ({detail['shares']} lembar)"
                )
                if entry_market and entry_cost and entry_market != entry_cost:
                    lines.append(
                        f"   Harga Beli: {entry_market:,.0f} → "
                        f"Cost: {entry_cost:,.0f}"
                    )
                elif entry_market and current and entry_market != current:
                    lines.append(
                        f"   Beli: {entry_market:,.0f} → "
                        f"Sekarang: {current:,.0f}"
                    )
                else:
                    lines.append(
                        f"   Harga: {current:,.0f} IDR"
                    )
                lines.append(
                    f"   Value: {detail['value']:,.0f} IDR"
                )
                lines.append(
                    f"   PnL (net): {pnl_sign}{detail['pnl']:,.0f} IDR "
                    f"({pnl_sign}{detail['pnl_pct']:.2f}%)"
                )
                lines.append(
                    f"   Break-even: {break_even:,.0f} | "
                    f"Est. biaya jual: {est_sell_fees:,.0f}"
                )
                lines.append("")

        stock_value = grand_total - cash_balance
        net_stock_value = stock_value - total_est_sell_fees

        lines.append(f"<b>💵 Total Saham (gross): {stock_value:,.0f} IDR</b>")
        lines.append(f"   Est. Biaya Jual: {total_est_sell_fees:,.0f} IDR")
        lines.append(f"   Total Saham (net): {net_stock_value:,.0f} IDR")
        lines.append(f"<b>💰 Total Cash: {cash_balance:,.0f} IDR</b>")
        lines.append(f"")
        lines.append(f"<b>🏦 GRAND TOTAL (net): {grand_total - total_est_sell_fees:,.0f} IDR</b>")

        self.send("\n".join(lines))

    def notify_summary(self, cash_balance, positions_count, total_pnl, win_rate, trades, total_fees=None):
        """
        Mengirim pesan ringkasan performa akun bot saham.
        
        Args:
            cash_balance (float): Saldo kas IDR.
            positions_count (int): Jumlah posisi aktif.
            total_pnl (float): Net PnL kumulatif.
            win_rate (float): Win rate persentase.
            trades (int): Jumlah transaksi selesai.
            total_fees (float, optional): Total biaya fee transaksi.
        """
        sign = "+" if total_pnl >= 0 else ""
        msg = (
            f"<b>SAHAM SUMMARY</b>\n"
            f"Cash: {cash_balance:,.0f} IDR\n"
            f"Open: {positions_count} positions\n"
            f"PnL (net): {sign}{total_pnl:,.0f} IDR\n"
            f"Win: {win_rate}% ({trades} trades)\n"
        )
        if total_fees:
            msg += f"Total Biaya (hidup): {total_fees:,.0f} IDR\n"
        self.send(msg)

    def notify_error(self, message):
        """
        Mengirim pesan peringatan kesalahan/error ke Telegram.
        
        Args:
            message (str): Isi pesan error.
        """
        msg = f"<b>ERROR</b>\n{message}"
        self.send(msg)

    def notify_start(self, stocks):
        """
        Mengirim notifikasi saat bot saham mulai berjalan (startup event).
        
        Args:
            stocks (list): Daftar ticker saham yang dipantau.
        """
        from config import (
            BUY_BROKER_FEE_PCT, BUY_CLEARENCE_FEE_PCT, BUY_TAX_FEE_PCT, BUY_TOTAL_FEE_PCT,
            SELL_BROKER_FEE_PCT, SELL_CLEARENCE_FEE_PCT, SELL_TAX_FEE_PCT,
            SELL_VAT_FEE_PCT, SELL_PPH_FEE_PCT, SELL_TOTAL_FEE_PCT,
            ROUND_TRIP_FEE_PCT
        )
        msg = (
            f"<b>SAHAM BOT STARTED</b>\n"
            f"Stocks: {', '.join([s.replace('.JK', '') for s in stocks[:5]])}...\n"
            f"Total: {len(stocks)} stocks monitored\n"
            f"Interval: 5 min\n"
            f"Biaya Beli: {BUY_TOTAL_FEE_PCT*100:.2f}% "
            f"(broker {BUY_BROKER_FEE_PCT*100:.2f}% + clearing {BUY_CLEARENCE_FEE_PCT*100:.2f}% + BEI {BUY_TAX_FEE_PCT*100:.2f}%)\n"
            f"Biaya Jual: {SELL_TOTAL_FEE_PCT*100:.2f}% "
            f"(broker {SELL_BROKER_FEE_PCT*100:.2f}% + clearing {SELL_CLEARENCE_FEE_PCT*100:.2f}% + BEI {SELL_TAX_FEE_PCT*100:.2f}% + PPN {SELL_VAT_FEE_PCT*100:.1f}% + PPh {SELL_PPH_FEE_PCT*100:.1f}%)\n"
            f"Round-trip: {ROUND_TRIP_FEE_PCT*100:.2f}%\n"
            f"Time: {format_datetime()}"
        )
        self.send(msg)

    def notify_stop(self, reason="User request"):
        """
        Mengirim notifikasi saat bot saham berhenti (shutdown event).
        
        Args:
            reason (str, optional): Alasan stop.
        """
        msg = f"<b>SAHAM BOT STOPPED</b>\nReason: {reason}"
        self.send(msg)

    def notify_market_open(self, is_open):
        """
        Mengirim pengumuman status jam bursa BEI / IDX (buka pukul 09:00 WIB, tutup pukul 16:00 WIB).
        
        Args:
            is_open (bool): True jika pasar saham sedang buka.
        """
        if is_open:
            self.send("🟢 <b>PASAR SAHAM BUKA</b>\nBot mulai monitoring...")
        else:
            self.send("🔴 <b>PASAR SAHAM TUTUP</b>\nBot pause sampai jam buka 09:00 WIB")


def test_telegram():
    """
    Fungsi uji coba untuk memverifikasi apakah notifikasi Telegram saham terkirim.
    
    Returns:
        bool: True jika sukses, False jika gagal.
    """
    tg = TelegramNotifier()
    if not tg.enabled:
        print("Telegram not configured!")
        return False

    msg = (
        "<b>Test Notification</b>\n"
        "Saham trading bot Telegram integration is working!\n"
        f"Time: {format_datetime()}"
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

