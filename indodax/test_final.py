"""
Script Pengujian Akhir Pengiriman Pesan Diagnostik (/why_idle) ke Telegram

Memformat laporan diagnostik bot Indodax dan mengirimkannya langsung ke chat Telegram terkonfigurasi.

Author: AI Trading Bot
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from telegram_commands import get_why_idle_text, send_telegram, escape_html

print("=== WHY IDLE (raw) ===")
result = get_why_idle_text()
print(result)
print()

print("=== Sending to Telegram ===")
prefix = "<b>INDODAX</b>\n"
msg = escape_html(prefix) + result
print(f"Message length: {len(msg)}")
print(f"Message preview: {msg[:200]}")
print()

# Actually send it
send_telegram(msg)
print("Sent!")

