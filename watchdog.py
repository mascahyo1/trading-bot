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

BOT_LOG = "/home/cahyo/trading-bot/logs/bot_error.log"
HEARTBEAT_FILE = "/home/cahyo/trading-bot/logs/heartbeat.txt"
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

    if not os.path.exists(BOT_LOG):
        errors.append("Log file not found")
    else:
        mod_time = os.path.getmtime(BOT_LOG)
        age_seconds = time.time() - mod_time
        if age_seconds > 1200:
            errors.append(f"Log tidak update {age_seconds/60:.0f} min (bot mungkin stuck)")

        try:
            with open(BOT_LOG, "r") as f:
                lines = f.readlines()
                last_lines = lines[-20:] if len(lines) > 20 else lines
                error_count = sum(1 for l in last_lines if "ERROR" in l)
                if error_count > 10:
                    errors.append(f"Error rate tinggi: {error_count} errors di 20 baris terakhir")
        except Exception:
            pass

    result = os.popen("systemctl is-active trading-bot.service").read().strip()
    if result != "active":
        errors.append(f"Service: {result}")

    return errors

def should_send_heartbeat():
    if not os.path.exists(HEARTBEAT_FILE):
        return True
    last_heartbeat = os.path.getmtime(HEARTBEAT_FILE)
    return (time.time() - last_heartbeat) > 14400

def update_heartbeat():
    with open(HEARTBEAT_FILE, "w") as f:
        f.write(str(int(time.time())))

def main():
    load_env()
    errors = check_bot_health()

    if errors:
        msg = "🔴 <b>BOT DOWN!</b>\n" + "\n".join(f"• {e}" for e in errors)
        send_telegram(msg)
        print(f"ALERT: {errors}")
    elif should_send_heartbeat():
        uptime = os.popen("systemctl show trading-bot.service --property=ActiveEnterTimestamp --value").read().strip()
        msg = (
            f"🟢 <b>BOT ALIVE</b>\n"
            f"✅ Semua sistem normal\n"
            f"⏱ Uptime: {uptime}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        send_telegram(msg)
        update_heartbeat()
        print(f"HEARTBEAT sent - {datetime.now().strftime('%H:%M:%S')}")
    else:
        print(f"OK - {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
