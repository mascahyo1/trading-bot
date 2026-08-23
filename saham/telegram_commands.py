"""
Telegram Command Handler & Response Formatter untuk Bot Saham Indonesia

Menyediakan fungsi pendukung untuk membaca interaksi perintah dari Telegram dan merespons:
- Status bot, saldo kas Rdn, valuasi portofolio saham real-time.
- Rincian aset per saham dan laporan biaya transaksi (Buy fee 0.14%, Sell fee 0.34%).
- Evaluasi diagnostik mengapa bot tidak membuka posisi (`/why-idle-saham`).
- Riwayat transaksi dan metrik analitik (Win rate, Avg Win/Loss, PnL harian/total).
- Eksekusi perintah kontrol bot (`/start-saham`, `/stop-saham`) dengan konfirmasi interaktif inline keyboard.

Author: AI Trading Bot
"""

import json
import os
import sys
import time
import logging
import urllib.request
import urllib.error
import urllib.parse
import threading
from config import (
    now_jakarta, format_datetime, MAX_OPEN_POSITIONS, MIN_ORDER_IDR,
    BUY_TOTAL_FEE_PCT, SELL_TOTAL_FEE_PCT, ROUND_TRIP_FEE_PCT,
)

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
BOT_INSTANCE = None


def load_env():
    """
    Memuat variabel lingkungan Telegram Token dan Chat ID dari file `.env`.
    """
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "Telegram_Bot_Token":
                    TELEGRAM_TOKEN = v.strip()
                elif k.strip() == "Telegram_Chat_ID":
                    TELEGRAM_CHAT_ID = v.strip()


def escape_html(text):
    """
    Sanitasi karakter khusus HTML untuk parse_mode HTML Telegram.
    
    Args:
        text (str): Teks mentah.
        
    Returns:
        str: Teks dengan entitas HTML ter-escape.
    """
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def send_telegram(text, reply_markup=None):
    """
    Mengirim pesan teks ke Telegram Bot API.
    
    Args:
        text (str): Pesan HTML.
        reply_markup (dict or str, optional): Payload inline keyboard.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"Telegram send error: {e} | Message: {text[:100]}")


def get_updates(offset=None):
    """
    Mengambil pesan update baru dari Telegram menggunakan mekanisme long polling.
    
    Args:
        offset (int, optional): Update ID offset.
        
    Returns:
        list: Daftar update dari Telegram.
    """
    if not TELEGRAM_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": json.dumps(["message"])}
    if offset:
        params["offset"] = offset
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode())
            return data.get("result", [])
    except urllib.error.HTTPError as e:
        if e.code == 409:
            logger.warning("Telegram conflict (409) - clearing pending updates")
            clear_pending_updates()
            return []
        logger.error(f"getUpdates HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        logger.error(f"getUpdates error: {e}")
        return []


def clear_pending_updates():
    """
    Menghapus antrean update Telegram lama yang tertahan di server Telegram.
    """
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": -1, "timeout": 1}
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        pass


def get_portfolio_text():
    """
    Menyusun laporan portofolio dari Ajaib.
    
    Returns:
        str: Pesan HTML laporan portofolio.
    """
    try:
        from portfolio import format_portfolio_report
        return format_portfolio_report()
    except Exception as e:
        return f"Error: {e}"


def get_asset_per_stock():
    """
    Menyusun laporan rincian valuasi per saham dan Grand Total.
    
    Returns:
        str: Pesan HTML laporan rincian aset.
    """
    try:
        from portfolio import get_asset_breakdown
        return get_asset_breakdown()
    except Exception as e:
        return f"Error: {e}"


def get_status_text():
    """
    Menyusun ringkasan status operasional bot saham, kas Rdn, dan posisi terbuka saat ini.
    
    Returns:
        str: Pesan HTML status bot.
    """
    try:
        if not BOT_INSTANCE:
            return "Bot not running"
        rm = BOT_INSTANCE.risk_manager
        ex = BOT_INSTANCE.exchange

        open_count = rm.get_open_positions_count()
        total_pnl = rm.get_total_pnl()
        win_rate = rm.get_win_rate()
        total_trades = len(rm.trade_history)
        position_details = rm.get_position_details(ex)

        total_stock_value = sum(d["value"] for d in position_details.values())
        cash = getattr(BOT_INSTANCE, '_last_cash', 0)
        grand_total = cash + total_stock_value

        sign = "+" if total_pnl >= 0 else ""
        lines = [
            "<b>📊 BOT STATUS</b>",
            f"Status: Running",
            f"Cash: {cash:,.0f} IDR",
            f"Stock Value: {total_stock_value:,.0f} IDR",
            f"Grand Total: {grand_total:,.0f} IDR",
            f"Open Positions: {open_count}/{MAX_OPEN_POSITIONS}",
            f"Total PnL: {sign}{total_pnl:,.0f} IDR",
            f"Win Rate: {win_rate}% ({total_trades} trades)",
            f"",
            f"⏰ {format_datetime()}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_trades_text():
    """
    Menyusun riwayat 5 transaksi saham terakhir yang telah ditutup beserta PnL bersih.
    
    Returns:
        str: Pesan HTML daftar trade.
    """
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "No trades yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "No trades yet"
        lines = ["<b>📜 RECENT TRADES</b>"]
        for t in trades[-5:]:
            pnl = t.get("pnl_amount", 0)
            sign = "+" if pnl >= 0 else ""
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{pnl_emoji} {t['code']} @ {t['exit_price']:,.0f}\n"
                f"   PnL: {sign}{pnl:,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_analytics_text():
    """
    Menghitung dan memformat statistik analitik performa trading saham (Win rate, Net PnL, Total Fees, R/R).
    
    Returns:
        str: Pesan HTML analitik performa saham.
    """
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "No trade data yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "No trade data yet"
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
        losses = [t for t in trades if t.get("pnl_amount", 0) <= 0]
        total_pnl = sum(t.get("pnl_amount", 0) for t in trades)
        total_fees = sum(t.get("total_fees", 0) for t in trades)
        gross_pnl = sum(t.get("gross_pnl", 0) for t in trades)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0
        best = max(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        worst = min(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        daily_pnl = 0
        daily_fees = 0
        today = now_jakarta().strftime("%Y-%m-%d")
        for t in trades:
            if t.get("exit_time", "").startswith(today):
                daily_pnl += t.get("pnl_amount", 0)
                daily_fees += t.get("total_fees", 0)

        sign_pnl = "+" if total_pnl >= 0 else ""
        sign_daily = "+" if daily_pnl >= 0 else ""
        sign_win = "+" if avg_win >= 0 else ""
        sign_loss = "+" if avg_loss >= 0 else ""

        lines = [
            "<b>📊 SAHAM ANALYTICS</b>",
            f"Total Trades: {total_trades}",
            f"Win Rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)",
            f"Daily PnL (net): {sign_daily}{daily_pnl:,.0f} IDR",
            f"Daily Fees: {daily_fees:,.0f} IDR",
            f"Total PnL (net): {sign_pnl}{total_pnl:,.0f} IDR",
            f"Total Fees: {total_fees:,.0f} IDR",
            f"Gross PnL: {gross_pnl:+,.0f} IDR",
            f"Avg Win: {sign_win}{avg_win:,.0f} IDR",
            f"Avg Loss: {sign_loss}{avg_loss:,.0f} IDR",
        ]
        if avg_loss != 0:
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            lines.append(f"Risk/Reward: 1:{rr:.1f}")
        if best:
            sign_b = "+" if best['pnl_amount'] >= 0 else ""
            lines.append(f"Best: {best['code']} {sign_b}{best['pnl_amount']:,.0f}")
        if worst:
            sign_w = "+" if worst['pnl_amount'] >= 0 else ""
            lines.append(f"Worst: {worst['code']} {sign_w}{worst['pnl_amount']:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return escape_html(f"Error: {e}")


def get_why_idle_text():
    """
    Mengevaluasi faktor penghambat trading (Win rate rendah, kuota posisi penuh, saldo kas minim).
    
    Returns:
        str: Pesan HTML diagnostik idle bot saham.
    """
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        trades = []
        if os.path.exists(history_file):
            with open(history_file) as f:
                trades = json.load(f)
        reasons = []
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0

        if total_trades >= 5 and win_rate < 40:
            reasons.append(f"BLOCKED: Win rate {win_rate:.0f}% &lt; 40%")
        elif win_rate >= 40:
            reasons.append(f"OK: Win rate {win_rate:.0f}%")
        else:
            reasons.append(f"Win rate {win_rate:.0f}% (need 5+ trades)")

        open_count = 0
        cash = 0
        if BOT_INSTANCE:
            open_count = BOT_INSTANCE.risk_manager.get_open_positions_count()
            cash = getattr(BOT_INSTANCE, '_last_cash', 0)

        if open_count >= MAX_OPEN_POSITIONS:
            reasons.append(f"BLOCKED: Max positions ({open_count}/{MAX_OPEN_POSITIONS})")
        else:
            reasons.append(f"OK: Positions available ({open_count}/{MAX_OPEN_POSITIONS})")

        min_order = MIN_ORDER_IDR * 1.5
        if cash < min_order:
            reasons.append(f"BLOCKED: Cash {cash:,.0f} &lt; {min_order:,.0f} IDR")
        else:
            reasons.append(f"OK: Cash {cash:,.0f} IDR")

        today = now_jakarta().strftime("%Y-%m-%d")
        today_trades = [t for t in trades if t.get("exit_time", "").startswith(today)]
        today_pnl = sum(t.get("pnl_amount", 0) for t in today_trades)
        reasons.append(f"Today: {len(today_trades)} trades, {today_pnl:+,.0f} IDR")

        lines = ["<b>WHY BOT IS IDLE</b>", "", "<b>FACTORS:</b>"]
        lines.extend(reasons)
        if any("BLOCKED" in r for r in reasons):
            lines.append("")
            lines.append("<b>ACTION:</b>")
            if win_rate < 40 and total_trades >= 5:
                lines.append("- Wait for win rate &gt; 40%")
            if open_count >= MAX_OPEN_POSITIONS:
                lines.append("- Wait for TP/SL to hit")
            if cash < min_order:
                lines.append("- Deposit more IDR")
        else:
            lines.append("")
            lines.append("Bot should be active!")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_fees_text():
    """
    Menyusun rincian struktur fee transaksi saham Ajaib (beli 0.14%, jual 0.34%) dan akumulasi biaya seumur hidup.
    
    Returns:
        str: Pesan HTML rincian biaya fee.
    """
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        total_fees = 0
        total_buy_fees = 0
        total_sell_fees = 0
        if os.path.exists(history_file):
            with open(history_file) as f:
                trades = json.load(f)
            for t in trades:
                total_buy_fees += t.get("buy_fees", 0)
                total_sell_fees += t.get("sell_fees", 0)
                total_fees += t.get("total_fees", 0)

        lines = [
            "<b>💰 TRANSACTION FEES</b>",
            "",
            "<b>Per Trade:</b>",
            f"  Biaya Beli: {BUY_TOTAL_FEE_PCT*100:.2f}%",
            f"  Biaya Jual: {SELL_TOTAL_FEE_PCT*100:.2f}%",
            f"  Round-trip: {ROUND_TRIP_FEE_PCT*100:.2f}%",
            "",
            "<b>Breakdown Beli:</b>",
            f"  Broker: 0.10%",
            f"  Clearing: 0.02%",
            f"  BEI: 0.02%",
            f"  <b>Total: {BUY_TOTAL_FEE_PCT*100:.2f}%</b>",
            "",
            "<b>Breakdown Jual:</b>",
            f"  Broker: 0.10%",
            f"  Clearing: 0.02%",
            f"  BEI: 0.02%",
            f"  PPN: 0.10%",
            f"  PPh Final: 0.10%",
            f"  <b>Total: {SELL_TOTAL_FEE_PCT*100:.2f}%</b>",
            "",
            "<b>Lifetime Stats:</b>",
            f"  Total Biaya: {total_fees:,.0f} IDR",
            f"  Biaya Beli: {total_buy_fees:,.0f} IDR",
            f"  Biaya Jual: {total_sell_fees:,.0f} IDR",
            "",
            "<i>Semua PnL di bot ini sudah NET (setelah potong biaya)</i>",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


PENDING_CONFIRMATION = {}


def handle_command(text, chat_id):
    """
    Memproses teks perintah yang dikirim oleh pengguna via Telegram.
    
    Args:
        text (str): Perintah teks Telegram.
        chat_id (str or int): Chat ID pengirim.
    """
    text = text.strip()
    cmd = text.lower().split()[0] if text else ""
    prefix = "<b>SAHAM</b>\n"

    if cmd == "/status-saham" or cmd == "/status":
        send_telegram(prefix + get_status_text())

    elif cmd == "/saham" or cmd == "/portfolio-saham" or cmd == "/portfolio":
        send_telegram(prefix + get_portfolio_text())

    elif cmd == "/asset-saham" or cmd == "/asset" or cmd == "/aset":
        send_telegram(prefix + get_asset_per_stock())

    elif cmd == "/trades-saham" or cmd == "/trades":
        send_telegram(prefix + get_trades_text())

    elif cmd == "/analytics-saham" or cmd == "/stats-saham" or cmd == "/analytics" or cmd == "/stats":
        send_telegram(prefix + get_analytics_text())

    elif cmd == "/why-idle-saham" or cmd == "/why-saham" or cmd == "/why-idle" or cmd == "/why":
        send_telegram(prefix + get_why_idle_text())

    elif cmd == "/analyze-improvement-saham" or cmd == "/improve" or cmd == "/improvement":
        send_telegram(prefix + "Analyzing bot performance...")
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from monitor import run_analysis
            run_analysis()
        except ImportError:
            send_telegram(prefix + "Monitor module not available. Add monitor.py for AI analysis.")
        except Exception as e:
            send_telegram(prefix + "Analysis failed: " + escape_html(str(e)[:200]))

    elif cmd == "/fees-saham" or cmd == "/fees" or cmd == "/biaya":
        send_telegram(prefix + get_fees_text())

    elif cmd == "/stop-saham" or cmd == "/stop":
        if chat_id in PENDING_CONFIRMATION and PENDING_CONFIRMATION[chat_id] == "stop":
            send_telegram(prefix + "Bot stopping...")
            if BOT_INSTANCE:
                BOT_INSTANCE.stop()
            PENDING_CONFIRMATION.pop(chat_id, None)
        else:
            PENDING_CONFIRMATION[chat_id] = "stop"
            keyboard = json.dumps({
                "inline_keyboard": [[
                    {"text": "Yes, Stop Bot", "callback_data": "confirm_stop"},
                    {"text": "Cancel", "callback_data": "cancel"}
                ]]
            })
            send_telegram(prefix + "Are you sure you want to STOP the bot?", reply_markup=keyboard)

    elif cmd == "/start-saham" or cmd == "/start":
        if chat_id in PENDING_CONFIRMATION and PENDING_CONFIRMATION[chat_id] == "start":
            send_telegram(prefix + "Bot starting...")
            if BOT_INSTANCE:
                BOT_INSTANCE.start()
            PENDING_CONFIRMATION.pop(chat_id, None)
        else:
            PENDING_CONFIRMATION[chat_id] = "start"
            keyboard = json.dumps({
                "inline_keyboard": [[
                    {"text": "Yes, Start Bot", "callback_data": "confirm_start"},
                    {"text": "Cancel", "callback_data": "cancel"}
                ]]
            })
            send_telegram(prefix + "Are you sure you want to START the bot?", reply_markup=keyboard)

    elif cmd == "/help-saham" or cmd == "/help":
        send_telegram(
            prefix + "<b>BOT COMMANDS</b>\n"
            "/status-saham - Bot status & portfolio\n"
            "/saham - Portfolio from Ajaib\n"
            "/asset-saham - Asset per stock + grand total\n"
            "/trades-saham - Recent trade history\n"
            "/analytics-saham - Win rate, PnL, R/R ratio\n"
            "/why-idle-saham - Why bot is not trading\n"
            "/analyze-improvement-saham - AI analysis & suggestions\n"
            "/fees-saham - Transaction fees breakdown\n"
            "/stop-saham - Stop bot (with confirmation)\n"
            "/start-saham - Start bot (with confirmation)\n"
            "/help-saham - Show this message\n"
            "\n"
            "<b>ALIASES:</b>\n"
            "/status, /portfolio, /asset, /aset, /trades\n"
            "/analytics, /stats, /why, /why-idle\n"
            "/improve, /improvement, /fees, /biaya\n"
            "/stop, /start"
        )
    elif text.startswith("/"):
        send_telegram("Unknown command. Type /help-saham for available commands.")


def handle_callback(data, chat_id):
    """
    Memproses tombol inline keyboard callback (konfirmasi start/stop bot).
    
    Args:
        data (str): Callback data ('confirm_stop', 'confirm_start', 'cancel').
        chat_id (str or int): Chat ID pengguna.
    """
    prefix = "<b>SAHAM</b>\n"
    if data == "confirm_stop":
        send_telegram(prefix + "Bot stopping...")
        if BOT_INSTANCE:
            BOT_INSTANCE.stop()
        PENDING_CONFIRMATION.pop(chat_id, None)
    elif data == "confirm_start":
        send_telegram(prefix + "Bot starting...")
        if BOT_INSTANCE:
            BOT_INSTANCE.start()
        PENDING_CONFIRMATION.pop(chat_id, None)
    elif data == "cancel":
        send_telegram("Cancelled")
        PENDING_CONFIRMATION.pop(chat_id, None)


class TelegramCommandHandler:
    """
    Background polling listener thread untuk memproses perintah Telegram bot saham.
    
    Attributes:
        running (bool): Status apakah polling sedang berjalan.
        offset (int): Offset ID update Telegram.
        thread (threading.Thread): Thread background poller.
    """

    def __init__(self, bot_instance=None):
        """
        Inisialisasi TelegramCommandHandler.
        
        Args:
            bot_instance (ProductionStockBot, optional): Instance bot saham aktif.
        """
        global BOT_INSTANCE
        load_env()
        BOT_INSTANCE = bot_instance
        self.running = False
        self.offset = None
        self.thread = None

    def start(self):
        """Memulai background listener thread."""
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("Telegram command handler started")

    def stop(self):
        """Menghentikan background listener thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _poll_loop(self):
        """Loop polling berkala untuk membaca update pesan baru dari Telegram."""
        while self.running:
            try:
                updates = get_updates(self.offset)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg.get("chat", {}).get("id")
                        if chat_id and TELEGRAM_CHAT_ID and str(chat_id) == TELEGRAM_CHAT_ID:
                            text = msg.get("text", "")
                            if text:
                                logger.info(f"Received command: {text}")
                                handle_command(text, chat_id)
                        else:
                            logger.warning(f"Chat ID mismatch: {chat_id} vs {TELEGRAM_CHAT_ID}")
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb.get("message", {}).get("chat", {}).get("id")
                        data = cb.get("data")
                        if chat_id and data:
                            handle_callback(data, chat_id)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                time.sleep(5)

