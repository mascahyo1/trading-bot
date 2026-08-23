import sys
sys.path.insert(0, "/home/cahyo/trading-bot/indodax")

import telegram_commands

print(f"Before load_env:")
print(f"  TELEGRAM_TOKEN: [{telegram_commands.TELEGRAM_TOKEN[:20]}...]")
print(f"  TELEGRAM_CHAT_ID: [{telegram_commands.TELEGRAM_CHAT_ID}]")

telegram_commands.load_env()

print(f"After load_env:")
print(f"  TELEGRAM_TOKEN: [{telegram_commands.TELEGRAM_TOKEN[:20]}...]")
print(f"  TELEGRAM_CHAT_ID: [{telegram_commands.TELEGRAM_CHAT_ID}]")

updates = telegram_commands.get_updates()
print(f"Updates: {len(updates)}")
