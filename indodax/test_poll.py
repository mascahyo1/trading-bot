"""
Script Pengujian Polling Pesan Masuk dari Telegram Bot API

Mengambil dan menampilkan 5 update pesan masuk terakhir dari pengguna Telegram.

Author: AI Trading Bot
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from telegram_commands import get_updates, TELEGRAM_CHAT_ID

print(f"Chat ID configured: {TELEGRAM_CHAT_ID}")
print("Checking for updates...")

updates = get_updates()
print(f"Updates found: {len(updates)}")

for u in updates[:5]:
    uid = u.get("update_id")
    text = u.get("message", {}).get("text", "N/A")
    chat_id = u.get("message", {}).get("chat", {}).get("id")
    print(f"  {uid}: chat={chat_id}, text={text[:50]}")

