#!/usr/bin/env python3
"""
Telegram Bot Command Handler & Response Generator (Indodax & Saham)

Modul pembantu untuk menyusun respons teks HTML perintah Telegram untuk bot Indodax dan Saham:
- Ringkasan status bot, saldo, dan waktu operasional.
- Evaluasi diagnostik mengapa bot tidak trading (`/why_idle`).
- Laporan portofolio koin dan kalkulasi analitik (Win Rate, PnL, Avg Win/Loss, Best/Worst trades).

Author: AI Trading Bot
"""
import json
import os
import sys
import time
import logging
import urllib.request
import urllib.error
import threading
from config import now_jakarta, format_datetime

logger = logging.getLogger(__name__)

SAHAM_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "saham")
SAHAM_STATE_FILE = os.path.join(SAHAM_SCRIPT_DIR, "saham_state.json")

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
BOT_INSTANCE = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_env():
    """
    Memuat variabel lingkungan Telegram dari file `.env`.
    """
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
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
        str: Teks dengan karakter HTML yang di-escape.
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
        text (str): Isi pesan HTML.
        reply_markup (dict or str, optional): Inline keyboard payload jika ada.
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
    Mengambil pesan baru dari Telegram menggunakan long polling.
    
    Args:
        offset (int, optional): Update ID offset.
        
    Returns:
        list: Daftar update Telegram.
    """
    if not TELEGRAM_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    query = "&".join(f"{k}={v}" for k, v in params.items())
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
    Menghapus antrean update lama yang tertumpuk di Telegram server.
    """
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": -1, "timeout": 1}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        pass


def get_portfolio_text():
    """
    Menyusun laporan portofolio koin dan total saldo IDR di akun Indodax.
    
    Returns:
        str: Pesan HTML ringkasan portofolio.
    """
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from exchange import IndodaxExchange
        ex = IndodaxExchange()
        bal = ex.get_balance()
        if bal.get("error"):
            return "Error fetching portfolio"
        total_idr = 0
        lines = ["<b>PORTFOLIO</b>"]
        for b in bal.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            total = free + locked
            if total > 0:
                asset = b["asset"]
                idr_val = total if asset == "IDR" else 0
                if asset != "IDR":
                    ticker = ex.fetch_ticker(f"{asset}/IDR")
                    if ticker and ticker.get("last"):
                        idr_val = total * ticker["last"]
                total_idr += idr_val
                if idr_val > 100:
                    lines.append(f"  {asset}: {total:.6f} = {idr_val:,.0f} IDR")
        lines.append(f"\n<b>Total: {total_idr:,.0f} IDR</b>")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_status_text():
    """
    Menyusun ringkasan status operasional bot Indodax dan saldo kas IDR.
    
    Returns:
        str: Pesan HTML status bot.
    """
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from exchange import IndodaxExchange
        ex = IndodaxExchange()
        bal = ex.get_idr_balance()
        lines = [
            "<b>BOT STATUS</b>",
            f"Status: Running",
            f"IDR Balance: {bal:,.0f} IDR",
            f"{format_datetime()}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"

def get_trades_text():
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "No trades yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "No trades yet"
        lines = ["<b>RECENT TRADES</b>"]
        for t in trades[-5:]:
            pnl = t.get("pnl_amount", 0)
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"  {t['symbol']} {t['side']} @ {t['exit_price']:,.0f}\n"
                f"     PnL: {sign}{pnl:,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"

def get_why_idle_text():
    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        trades = []
        if os.path.exists(history_file):
            with open(history_file) as f:
                trades = json.load(f)
        sys.path.insert(0, SCRIPT_DIR)
        from config import MAX_OPEN_POSITIONS, MIN_ORDER_IDR, now_jakarta
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
        try:
            from exchange import IndodaxExchange
            ex = IndodaxExchange()
            balance = ex.get_idr_balance()
            bal = ex.get_balance()
            if bal and not bal.get("error"):
                for b in bal.get("balances", []):
                    asset = b.get("asset", "")
                    free = float(b.get("free", 0))
                    if free > 0 and asset != "IDR":
                        open_count += 1
        except Exception:
            balance = 0
        if open_count >= MAX_OPEN_POSITIONS:
            reasons.append(f"BLOCKED: Max positions ({open_count}/{MAX_OPEN_POSITIONS})")
        else:
            reasons.append(f"OK: Positions available ({open_count}/{MAX_OPEN_POSITIONS})")
        min_order = MIN_ORDER_IDR * 1.5
        if balance < min_order:
            reasons.append(f"BLOCKED: Balance {balance:,.0f} &lt; {min_order:,.0f} IDR")
        else:
            reasons.append(f"OK: Balance {balance:,.0f} IDR")
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
                lines.append("- Close positions at profit")
            if open_count >= MAX_OPEN_POSITIONS:
                lines.append("- Wait for TP/SL to hit")
            if balance < min_order:
                lines.append("- Deposit more IDR")
        else:
            lines.append("")
            lines.append("Bot should be active!")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"

def get_analytics_text():
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
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0
        best = max(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        worst = min(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        daily_pnl = 0
        today = now_jakarta().strftime("%Y-%m-%d")
        for t in trades:
            if t.get("exit_time", "").startswith(today):
                daily_pnl += t.get("pnl_amount", 0)
        sign_pnl = "+" if total_pnl >= 0 else ""
        sign_daily = "+" if daily_pnl >= 0 else ""
        sign_win = "+" if avg_win >= 0 else ""
        sign_loss = "+" if avg_loss >= 0 else ""
        lines = [
            "<b>INDODAX ANALYTICS</b>",
            f"Total Trades: {total_trades}",
            f"Win Rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)",
            f"Daily PnL: {sign_daily}{daily_pnl:,.0f} IDR",
            f"Total PnL: {sign_pnl}{total_pnl:,.0f} IDR",
            f"Avg Win: {sign_win}{avg_win:,.0f} IDR",
            f"Avg Loss: {sign_loss}{avg_loss:,.0f} IDR",
        ]
        if avg_loss != 0:
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            lines.append(f"Risk/Reward: 1:{rr:.1f}")
        if best:
            sign_b = "+" if best['pnl_amount'] >= 0 else ""
            lines.append(f"Best: {best['symbol']} {sign_b}{best['pnl_amount']:,.0f}")
        if worst:
            sign_w = "+" if worst['pnl_amount'] >= 0 else ""
            lines.append(f"Worst: {worst['symbol']} {sign_w}{worst['pnl_amount']:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return escape_html(f"Error: {e}")

def read_saham_state():
    try:
        if not os.path.exists(SAHAM_STATE_FILE):
            return None
        with open(SAHAM_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def get_saham_status_text():
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    analytics = state.get("analytics", {})
    prefix = "<b>SAHAM</b>\n"
    lines = [
        prefix + "<b>BOT STATUS</b>",
        f"Status: Running" if state else "Status: Stopped",
        f"Cash: {state.get('cash', 0):,.0f} IDR",
        f"Open Positions: {analytics.get('open_positions', 0)}",
        f"Total PnL (net): {analytics.get('total_pnl', 0):+,.0f} IDR",
        f"Win Rate: {analytics.get('win_rate', 0)}% ({analytics.get('total_trades', 0)} trades)",
        f"Total Fees: {analytics.get('total_fees', 0):,.0f} IDR",
        f"Daily PnL: {analytics.get('daily_pnl', 0):+,.0f} IDR",
        "",
        f"⏰ {format_datetime()}",
    ]
    return "\n".join(lines)


def get_saham_portfolio_text():
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    portfolio = state.get("portfolio", {})
    cash = portfolio.get("cash", 0)
    stocks = portfolio.get("stocks", [])
    prefix = "<b>SAHAM</b>\n"
    lines = [
        prefix + "<b>📊 ASET PER SAHAM</b>",
        f"⏰ {format_datetime()}",
        "",
        f"<b>💰 CASH: {cash:,.0f} IDR</b>",
        "",
    ]
    if stocks:
        lines.append("<b>📈 PER SAHAM:</b>")
        lines.append("")
        total_value = 0
        for s in stocks:
            code = s.get("code", "?")
            lots = s.get("lots", 0)
            price = s.get("price", 0)
            value = lots * 100 * price
            total_value += value
            lines.append(f"<b>{code}</b>")
            lines.append(f"   Lot: {lots} ({lots * 100} lembar)")
            lines.append(f"   Harga: {price:,.0f} IDR")
            lines.append(f"   <b>Total: {value:,.0f} IDR</b>")
            lines.append("")
    lines.append(f"<b>💵 Total Saham: {total_value:,.0f} IDR</b>")
    lines.append(f"<b>💰 Cash: {cash:,.0f} IDR</b>")
    lines.append(f"<b>🏦 GRAND TOTAL: {cash + total_value:,.0f} IDR</b>")
    return "\n".join(lines)


def get_saham_trades_text():
    try:
        history_file = os.path.join(SAHAM_SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "<b>SAHAM</b>\nNo trades yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "<b>SAHAM</b>\nNo trades yet"
        prefix = "<b>SAHAM</b>\n"
        lines = [prefix + "<b>📜 RECENT TRADES</b>"]
        for t in trades[-5:]:
            pnl = t.get("pnl_amount", 0)
            sign = "+" if pnl >= 0 else ""
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{pnl_emoji} {t.get('code', '?')} @ {t.get('exit_price', 0):,.0f}\n"
                f"   PnL (net): {sign}{pnl:,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"<b>SAHAM</b>\nError: {e}"


def get_saham_analytics_text():
    try:
        history_file = os.path.join(SAHAM_SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "<b>SAHAM</b>\nNo trade data yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "<b>SAHAM</b>\nNo trade data yet"
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
        today = now_jakarta().strftime("%Y-%m-%d")
        for t in trades:
            if t.get("exit_time", "").startswith(today):
                daily_pnl += t.get("pnl_amount", 0)
        sign_pnl = "+" if total_pnl >= 0 else ""
        sign_daily = "+" if daily_pnl >= 0 else ""
        prefix = "<b>SAHAM</b>\n"
        lines = [
            prefix + "<b>📊 SAHAM ANALYTICS</b>",
            f"Total Trades: {total_trades}",
            f"Win Rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)",
            f"Daily PnL (net): {sign_daily}{daily_pnl:,.0f} IDR",
            f"Total PnL (net): {sign_pnl}{total_pnl:,.0f} IDR",
            f"Total Fees: {total_fees:,.0f} IDR",
            f"Gross PnL: {gross_pnl:+,.0f} IDR",
        ]
        if avg_loss != 0:
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            lines.append(f"Risk/Reward: 1:{rr:.1f}")
        if best:
            sign_b = "+" if best['pnl_amount'] >= 0 else ""
            lines.append(f"Best: {best.get('code', '?')} {sign_b}{best['pnl_amount']:,.0f}")
        if worst:
            sign_w = "+" if worst['pnl_amount'] >= 0 else ""
            lines.append(f"Worst: {worst.get('code', '?')} {sign_w}{worst['pnl_amount']:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return escape_html(f"<b>SAHAM</b>\nError: {e}")


def get_saham_why_idle_text():
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    analytics = state.get("analytics", {})
    cash = state.get("cash", 0)
    open_count = analytics.get("open_positions", 0)
    total_trades = analytics.get("total_trades", 0)
    win_rate = analytics.get("win_rate", 0)
    reasons = []
    if total_trades >= 5 and win_rate < 40:
        reasons.append(f"BLOCKED: Win rate {win_rate:.0f}% &lt; 40%")
    elif win_rate >= 40:
        reasons.append(f"OK: Win rate {win_rate:.0f}%")
    else:
        reasons.append(f"Win rate {win_rate:.0f}% (need 5+ trades)")
    if open_count >= 5:
        reasons.append(f"BLOCKED: Max positions ({open_count}/5)")
    else:
        reasons.append(f"OK: Positions available ({open_count}/5)")
    min_order = 75000 * 1.5
    if cash < min_order:
        reasons.append(f"BLOCKED: Cash {cash:,.0f} &lt; {min_order:,.0f} IDR")
    else:
        reasons.append(f"OK: Cash {cash:,.0f} IDR")
    reasons.append(f"Today: {analytics.get('trades_today', 0)} trades, {analytics.get('daily_pnl', 0):+,.0f} IDR")
    prefix = "<b>SAHAM</b>\n"
    lines = [prefix + "<b>WHY BOT IS IDLE</b>", "", "<b>FACTORS:</b>"]
    lines.extend(reasons)
    if any("BLOCKED" in r for r in reasons):
        lines.append("")
        lines.append("<b>ACTION:</b>")
        if win_rate < 40 and total_trades >= 5:
            lines.append("- Wait for win rate &gt; 40%")
        if open_count >= 5:
            lines.append("- Wait for TP/SL to hit")
        if cash < min_order:
            lines.append("- Deposit more IDR")
    else:
        lines.append("")
        lines.append("Bot should be active!")
    return "\n".join(lines)


def get_saham_fees_text():
    try:
        history_file = os.path.join(SAHAM_SCRIPT_DIR, "trade_history.json")
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
        prefix = "<b>SAHAM</b>\n"
        lines = [
            prefix + "<b>💰 TRANSACTION FEES</b>",
            "",
            "<b>Per Trade:</b>",
            f"  Biaya Beli: 0.14%",
            f"  Biaya Jual: 0.34%",
            f"  Round-trip: 0.48%",
            "",
            "<b>Breakdown Beli:</b>",
            f"  Broker: 0.10%",
            f"  Clearing: 0.02%",
            f"  BEI: 0.02%",
            f"  <b>Total: 0.14%</b>",
            "",
            "<b>Breakdown Jual:</b>",
            f"  Broker: 0.10%",
            f"  Clearing: 0.02%",
            f"  BEI: 0.02%",
            f"  PPN: 0.10%",
            f"  PPh Final: 0.10%",
            f"  <b>Total: 0.34%</b>",
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
        return f"<b>SAHAM</b>\nError: {e}"


def handle_saham_command(cmd, chat_id):
    prefix = "<b>SAHAM</b>\n"
    if cmd in ("/status-saham", "/status"):
        send_telegram(get_saham_status_text())
    elif cmd in ("/saham", "/portfolio-saham", "/portfolio"):
        send_telegram(get_saham_portfolio_text())
    elif cmd in ("/asset-saham", "/asset", "/aset"):
        send_telegram(get_saham_portfolio_text())
    elif cmd in ("/trades-saham", "/trades"):
        send_telegram(get_saham_trades_text())
    elif cmd in ("/analytics-saham", "/stats-saham", "/analytics", "/stats"):
        send_telegram(get_saham_analytics_text())
    elif cmd in ("/why-idle-saham", "/why-saham", "/why-idle", "/why"):
        send_telegram(get_saham_why_idle_text())
    elif cmd in ("/fees-saham", "/fees", "/biaya"):
        send_telegram(get_saham_fees_text())
    elif cmd in ("/stop-saham", "/stop"):
        send_telegram(prefix + "Saham bot tidak dihandle di sini. Matikan manual via SSH.")
    elif cmd in ("/start-saham", "/start"):
        send_telegram(prefix + "Saham bot tidak dihandle di sini. Nyalakan manual via SSH.")
    else:
        return False
    return True


PENDING_CONFIRMATION = {}

def handle_command(text, chat_id):
    text = text.strip()
    cmd = text.lower().split()[0] if text else ""
    prefix = "<b>INDODAX</b>\n"

    saham_cmds = (
        "/status-saham", "/status",
        "/saham", "/portfolio-saham", "/portfolio",
        "/asset-saham", "/asset", "/aset",
        "/trades-saham", "/trades",
        "/analytics-saham", "/stats-saham", "/analytics", "/stats",
        "/why-idle-saham", "/why-saham", "/why-idle", "/why",
        "/fees-saham", "/fees", "/biaya",
        "/stop-saham", "/start-saham", "/stop", "/start",
    )
    if cmd in saham_cmds:
        if handle_saham_command(cmd, chat_id):
            return

    if cmd == "/status-indodax":
        send_telegram(prefix + get_status_text())

    elif cmd == "/why-idle-indodax" or cmd == "/why-indodax":
        send_telegram(prefix + get_why_idle_text())

    elif cmd == "/portfolio-indodax":
        send_telegram(prefix + get_portfolio_text())

    elif cmd == "/trades-indodax":
        send_telegram(prefix + get_trades_text())

    elif cmd == "/analytics-indodax" or cmd == "/stats-indodax":
        send_telegram(prefix + get_analytics_text())

    elif cmd == "/analyze-improvement-indodax":
        send_telegram(prefix + "Analyzing bot performance...")
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from monitor import run_analysis
            run_analysis()
        except Exception as e:
            send_telegram(prefix + "Analysis failed: " + escape_html(str(e)[:200]))
    elif cmd == "/stop-indodax":
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
    elif cmd == "/start-indodax":
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
    elif cmd == "/help":
        send_telegram(
            "<b>🤖 TRADING BOT COMMANDS</b>\n"
            "\n"
            "<b>═══ INDODAX (Crypto) ═══</b>\n"
            "/status-indodax - Bot status & balance\n"
            "/portfolio-indodax - All assets & total value\n"
            "/trades-indodax - Recent trade history\n"
            "/analytics-indodax - Win rate, PnL, R/R ratio\n"
            "/why-idle-indodax - Why bot is not trading\n"
            "/analyze-improvement-indodax - AI analysis\n"
            "/stop-indodax - Stop bot (with confirmation)\n"
            "/start-indodax - Start bot (with confirmation)\n"
            "\n"
            "<b>═══ SAHAM (Stocks) ═══</b>\n"
            "/status-saham - Bot status & portfolio\n"
            "/saham - Portfolio from Ajaib\n"
            "/asset-saham - Asset per stock + grand total\n"
            "/trades-saham - Recent trade history\n"
            "/analytics-saham - Win rate, PnL, R/R ratio\n"
            "/why-idle-saham - Why bot is not trading\n"
            "/fees-saham - Transaction fees breakdown\n"
            "\n"
            "<b>═══ ALIASES ═══</b>\n"
            "/status, /portfolio, /asset, /aset, /trades\n"
            "/analytics, /stats, /why, /why-idle\n"
            "/fees, /biaya\n"
            "\n"
            "/help - Show this message"
        )
    elif text.startswith("/"):
        send_telegram("Unknown command. Type /help for available commands.")

def handle_callback(data, chat_id):
    prefix = "<b>INDODAX</b>\n"
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
    def __init__(self, bot_instance=None):
        global BOT_INSTANCE
        load_env()
        BOT_INSTANCE = bot_instance
        self.running = False
        self.offset = None
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("Telegram command handler started")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _poll_loop(self):
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
