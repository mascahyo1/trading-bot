"""
Script Pengujian Pembuatan Format Teks Respon Telegram Bot

Menguji keluaran teks HTML dari fungsi:
- `get_why_idle_text()`
- `get_status_text()`
- `get_analytics_text()`

Author: AI Trading Bot
"""

import sys
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from telegram_commands import get_why_idle_text, get_status_text, get_portfolio_text, get_analytics_text

print("=== WHY IDLE ===")
result = get_why_idle_text()
print(result)
print(f"Length: {len(result)}")
print()

print("=== STATUS ===")
result = get_status_text()
print(result)
print(f"Length: {len(result)}")
print()

print("=== ANALYTICS ===")
result = get_analytics_text()
print(result)
print(f"Length: {len(result)}")

