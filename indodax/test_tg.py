import sys
sys.path.insert(0, "/home/cahyo/trading-bot/indodax")
from telegram_notifier import TelegramNotifier

tg = TelegramNotifier()
print("Sending test message...")
result = tg.send("<b>Test</b> Bot is alive!")
print(f"Result: {result}")
