#!/usr/bin/env python3
"""
Watchdog - Monitor trading bot health and send Telegram alerts
Run via cron every 5 minutes: */5 * * * * /home/cahyo/trading-bot/venv/bin/python3 /home/cahyo/trading-bot/watchdog.py
"""
import time
import json
import os
import urllib.request
from datetime import datetime

BOT_LOG = "/home/cahyo/trading-bot/logs/bot.log"
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

def load_env():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    with open("/home/cahyo/trading-bot/.env") as f:
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

def check_bot_health():
    errors = []

    # Check if log file exists and is recent
    if not os.path.exists(BOT_LOG):
        errors.append("Log file not found")
    else:
        mod_time = os.path.getmtime(BOT_LOG)
        age_seconds = time.time() - mod_time
        if age_seconds > 1200:
            errors.append(f"Log not updated for {age_seconds/60:.0f} min (bot may be stuck)")

        # Check for repeated errors in last few lines
        try:
            with open(BOT_LOG, "r") as f:
                lines = f.readlines()
                last_lines = lines[-20:] if len(lines) > 20 else lines
                error_count = sum(1 for l in last_lines if "ERROR" in l)
                if error_count > 10:
                    errors.append(f"High error rate: {error_count} errors in last 20 lines")
        except Exception:
            pass

    # Check if process is running
    result = os.popen("systemctl is-active trading-bot.service").read().strip()
    if result != "active":
        errors.append(f"Service status: {result}")

    return errors

def main():
    load_env()
    errors = check_bot_health()

    if errors:
        msg = "⚠️ <b>BOT ALERT</b>\n" + "\n".join(f"• {e}" for e in errors)
        send_telegram(msg)
        print(f"ALERT: {errors}")
    else:
        print(f"OK - {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
