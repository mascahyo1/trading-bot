import sys
sys.path.insert(0, "/home/cahyo/trading-bot/indodax")
from telegram_commands import get_why_idle_text
result = get_why_idle_text()
print(result)
