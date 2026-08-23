import sys
import os
sys.path.insert(0, "/home/cahyo/trading-bot/indodax")
os.chdir("/home/cahyo/trading-bot/indodax")

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
