import sys
import os
import json

sys.path.insert(0, "/home/cahyo/trading-bot/indodax")
os.chdir("/home/cahyo/trading-bot/indodax")

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
