#!/usr/bin/env python3
"""
Telegram Bot Command Handler
Listen for commands and respond. Sensitive actions require confirmation.
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

TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
BOT_INSTANCE = None

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
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

def send_telegram(text, reply_markup=None):
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
        logger.error(f"Telegram send error: {e}")

def get_updates(offset=None):
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
    except Exception as e:
        logger.error(f"getUpdates error: {e}")
        return []

def get_portfolio_text():
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
            reasons.append(f"BLOCKED: Win rate {win_rate:.0f}% < 40%")
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
            reasons.append(f"BLOCKED: Balance {balance:,.0f} < {min_order:,.0f} IDR")
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
                lines.append("- Wait for win rate > 40%")
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
        return f"Error: {e}"

PENDING_CONFIRMATION = {}

def handle_command(text, chat_id):
    text = text.strip()
    cmd = text.lower().split()[0] if text else ""
    prefix = "<b>INDODAX</b>\n"

    if cmd == "/status-indodax":
        send_telegram(prefix + get_status_text())
    elif cmd == "/why-idle" or cmd == "/why":
        send_telegram(prefix + get_why_idle_text())
    elif cmd == "/portfolio-indodax":
        send_telegram(prefix + get_portfolio_text())
    elif cmd == "/trades-indodax":
        send_telegram(prefix + get_trades_text())
    elif cmd == "/analytics-indodax" or cmd == "/stats-indodax":
        send_telegram(prefix + get_analytics_text())
    elif cmd == "/analyze-improvement":
        send_telegram(prefix + "Analyzing bot performance...")
        try:
            sys.path.insert(0, SCRIPT_DIR)
            from monitor import run_analysis
            run_analysis()
        except Exception as e:
            send_telegram(prefix + f"Analysis failed: {str(e)[:200]}")
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
            prefix + "<b>BOT COMMANDS</b>\n"
            "/status-indodax - Bot status & balance\n"
            "/portfolio-indodax - All assets & total value\n"
            "/trades-indodax - Recent trade history\n"
            "/analytics-indodax - Win rate, PnL, R/R ratio\n"
            "/why-idle - Why bot is not trading\n"
            "/analyze-improvement - AI analysis & suggestions\n"
            "/stop-indodax - Stop bot (with confirmation)\n"
            "/start-indodax - Start bot (with confirmation)\n"
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
                                handle_command(text, chat_id)
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb.get("message", {}).get("chat", {}).get("id")
                        data = cb.get("data")
                        if chat_id and data:
                            handle_callback(data, chat_id)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                time.sleep(5)
