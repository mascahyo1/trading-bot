#!/usr/bin/env python3
"""
Watchdog - Monitor bot health + portfolio every 5 minutes via Telegram
Cron: */5 * * * * /home/cahyo/trading/venv/bin/python3 /home/cahyo/trading/indodax/watchdog.py
"""
import time
import json
import os
import sys
import logging
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from config import now_jakarta, format_datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

def get_today_log():
    today = now_jakarta().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{today}.log")

BOT_LOG = get_today_log()
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

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

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def get_portfolio():
    """Get all balances and calculate IDR value"""
    sys.path.insert(0, SCRIPT_DIR)
    try:
        from exchange import IndodaxExchange
        from strategy import RiskManager
        ex = IndodaxExchange()
        rm = RiskManager()

        bal = ex.get_balance()
        if bal.get("error"):
            return None

        total_idr = 0
        assets = []
        for b in bal.get("balances", []):
            free = float(b.get("free", 0))
            locked = float(b.get("locked", 0))
            total = free + locked
            if total > 0:
                asset = b["asset"]
                idr_val = total if asset == "IDR" else 0
                if asset != "IDR":
                    pair = f"{asset}/IDR"
                    ticker = ex.fetch_ticker(pair)
                    if ticker and ticker.get("last"):
                        idr_val = total * ticker["last"]
                total_idr += idr_val
                assets.append({"asset": asset, "amount": total, "idr": idr_val})

        daily_pnl = rm.get_daily_pnl()
        return {"total_idr": total_idr, "assets": assets, "daily_pnl": daily_pnl}
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        return None

def check_bot_health():
    errors = []
    if not os.path.exists(BOT_LOG):
        errors.append("Log file not found")
    else:
        mod_time = os.path.getmtime(BOT_LOG)
        age_seconds = time.time() - mod_time
        if age_seconds > 1200:
            errors.append(f"Log tidak update {age_seconds/60:.0f} min")
    result = os.popen("systemctl is-active trading-bot.service").read().strip()
    if result != "active":
        errors.append(f"Service: {result}")
    return errors

def main():
    load_env()
    errors = check_bot_health()

    if errors:
        msg = "🏦 <b>INDODAX</b>\n🔴 <b>BOT DOWN!</b>\n" + "\n".join(f"• {e}" for e in errors)
        send_telegram(msg)
        print(f"ALERT: {errors}")
        return

    portfolio = get_portfolio()
    if not portfolio:
        msg = "🏦 <b>INDODAX</b>\n🟡 <b>BOT ALIVE</b>\n⚠️ Gagal cek portfolio"
        send_telegram(msg)
        return

    lines = ["🏦 <b>INDODAX BOT ALIVE</b>"]
    for a in portfolio["assets"]:
        if a["idr"] > 100:
            lines.append(f"  {a['asset']}: {a['amount']:.6f} ≈ {a['idr']:,.0f} IDR")
    lines.append(f"\n💰 <b>Cash: {portfolio['total_idr']:,.0f} IDR</b>")

    daily_pnl = portfolio.get("daily_pnl", 0)
    emoji = "📈" if daily_pnl >= 0 else "📉"
    lines.append(f"{emoji} Daily PnL: {daily_pnl:+,.0f} IDR")

    try:
        history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
        if os.path.exists(history_file):
            with open(history_file) as f:
                trades = json.load(f)
            if trades:
                total_trades = len(trades)
                wins = sum(1 for t in trades if t.get("pnl_amount", 0) > 0)
                total_pnl = sum(t.get("pnl_amount", 0) for t in trades)
                win_rate = wins / total_trades * 100
                lines.append(f"📊 Win: {win_rate:.0f}% ({total_trades} trades)")
                lines.append(f"💹 PnL: {total_pnl:+,.0f} IDR")
    except Exception:
        pass

    lines.append(f"🕐 {format_datetime()}")

    send_telegram("\n".join(lines))
    print(f"HEARTBEAT - {format_datetime()}")

if __name__ == "__main__":
    main()
