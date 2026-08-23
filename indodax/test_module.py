"""
Script Pengujian Pemuatan Variabel Lingkungan & Konektivitas Polling Telegram

Memvalidasi parsing token Telegram dari file .env dan menguji pengambilan update dari API Telegram.

Author: AI Trading Bot
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import telegram_commands

print("Before load_env:")
print(f"  TELEGRAM_TOKEN: [{telegram_commands.TELEGRAM_TOKEN[:20]}...]")
print(f"  TELEGRAM_CHAT_ID: [{telegram_commands.TELEGRAM_CHAT_ID}]")

telegram_commands.load_env()

print("After load_env:")
print(f"  TELEGRAM_TOKEN: [{telegram_commands.TELEGRAM_TOKEN[:20]}...]")
print(f"  TELEGRAM_CHAT_ID: [{telegram_commands.TELEGRAM_CHAT_ID}]")

updates = telegram_commands.get_updates()
print(f"Updates: {len(updates)}")

