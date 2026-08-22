import logging
import json
import urllib.request
import urllib.error
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("Telegram_Bot_Token", "")
TELEGRAM_CHAT_ID = os.getenv("Telegram_Chat_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


class TelegramNotifier:
    def __init__(self):
        self.enabled = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
        if self.enabled:
            logger.info("Telegram notifier ENABLED")
        else:
            logger.info("Telegram notifier DISABLED")

    def send(self, text, parse_mode="HTML"):
        if not self.enabled:
            return False

        url = f"{TELEGRAM_API}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return True
                logger.error(f"Telegram API error: {result}")
                return False
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    def notify_trade(self, symbol, side, price, amount=None, pnl=None):
        emoji = "🟢" if side == "BUY" else "🔴"
        msg = (
            f"🏦 <b>INDODAX</b>\n"
            f"{emoji} <b>{side}</b> {symbol}\n"
            f"💰 Price: {price:,.0f} IDR\n"
        )
        if amount:
            msg += f"📊 Amount: {amount:.8f}\n"
        if pnl is not None:
            emoji_pnl = "✅" if pnl >= 0 else "❌"
            msg += f"{emoji_pnl} PnL: {pnl:+,.0f} IDR\n"
        self.send(msg)

    def notify_signal(self, symbol, signal, confidence, indicators):
        emoji = "📈" if signal == "buy" else "📉" if signal == "sell" else "➖"
        msg = (
            f"{emoji} Signal: <b>{signal.upper()}</b> {symbol}\n"
            f"🎯 Confidence: {confidence:.0%}\n"
            f"📊 RSI: {indicators.get('rsi', 'N/A')} | "
            f"MACD: {indicators.get('macd_histogram', 'N/A')}\n"
        )
        self.send(msg)

    def notify_summary(self, balance, positions, total_pnl, win_rate, trades):
        avg_win, avg_loss = 0, 0
        msg = (
            f"🏦 <b>INDODAX SUMMARY</b>\n"
            f"💰 Balance: {balance:,.0f} IDR\n"
            f"📂 Open: {positions} positions\n"
            f"📈 PnL: {total_pnl:+,.0f} IDR\n"
            f"🎯 Win: {win_rate}% ({trades} trades)\n"
        )
        if avg_win > 0 and avg_loss > 0:
            msg += f"📊 Avg Win: {avg_win:,.0f} | Avg Loss: {avg_loss:,.0f}\n"
        self.send(msg)

    def notify_portfolio(self, balance, unrealized, total_portfolio, positions):
        msg = (
            f"🏦 <b>PORTFOLIO</b>\n"
            f"💰 Cash: {balance:,.0f} IDR\n"
            f"📈 Unrealized: {unrealized:+,.0f} IDR\n"
            f"💎 Total: {total_portfolio:,.0f} IDR\n"
        )
        if positions:
            msg += f"\n<b>POSITIONS</b>\n"
            for sym, pos in positions.items():
                if pos.status == "open":
                    msg += f"  {sym}: {pos.amount:.6f} @ {pos.entry_price:,.0f}\n"
        self.send(msg)

    def notify_error(self, message):
        msg = f"⚠️ <b>ERROR</b>\n{message}"
        self.send(msg)

    def notify_start(self, pairs, timeframe):
        msg = (
            f"🏦 <b>INDODAX BOT STARTED</b>\n"
            f"📊 Pairs: {', '.join(pairs)}\n"
            f"⏱ Timeframe: {timeframe}\n"
            f"🔔 Notifications: ON"
        )
        self.send(msg)

    def notify_stop(self, reason="User request"):
        msg = f"🏦 <b>INDODAX</b>\n🛑 <b>BOT STOPPED</b>\n📋 Reason: {reason}"
        self.send(msg)


def test_telegram():
    tg = TelegramNotifier()
    if not tg.enabled:
        print("Telegram not configured!")
        return False

    msg = (
        "✅ <b>Test Notification</b>\n"
        "Trading bot Telegram integration is working!\n"
        f"🕐 Time: working"
    )
    result = tg.send(msg)
    if result:
        print("Telegram test: SUCCESS")
    else:
        print("Telegram test: FAILED")
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_telegram()
