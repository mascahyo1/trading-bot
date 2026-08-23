import sys
sys.path.insert(0, "/home/cahyo/trading-bot/indodax")
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
