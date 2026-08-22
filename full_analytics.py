import json
import os
from datetime import datetime
from config import now_jakarta, format_datetime

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def full_report():
    trades = load_history()
    if not trades:
        return "No trades yet"

    total_trades = len(trades)
    wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
    losses = [t for t in trades if t.get("pnl_amount", 0) <= 0]
    total_pnl = sum(t.get("pnl_amount", 0) for t in trades)
    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0

    avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0

    best = max(trades, key=lambda t: t.get("pnl_amount", 0))
    worst = min(trades, key=lambda t: t.get("pnl_amount", 0))

    lines = [
        "📊 <b>FULL PERFORMANCE REPORT</b>",
        f"Total Trades: {total_trades}",
        f"Wins: {len(wins)} | Losses: {len(losses)}",
        f"Win Rate: {win_rate:.1f}%",
        f"",
        f"Total PnL: {total_pnl:+,.0f} IDR",
        f"Avg Win: {avg_win:+,.0f} IDR",
        f"Avg Loss: {avg_loss:+,.0f} IDR",
        f"Best Trade: {best['symbol']} {best['pnl_amount']:+,.0f} IDR ({best.get('pnl_pct', 0):+.2f}%)",
        f"Worst Trade: {worst['symbol']} {worst['pnl_amount']:+,.0f} IDR ({worst.get('pnl_pct', 0):+.2f}%)",
        f"",
        f"📜 <b>TRADE HISTORY</b>",
    ]
    for t in trades[-10:]:
        pnl = t.get("pnl_amount", 0)
        emoji = "✅" if pnl >= 0 else "❌"
        lines.append(
            f"{emoji} {t['symbol']} {t['side']} @ {t['exit_price']:,.0f}\n"
            f"   PnL: {pnl:+,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
        )
    return "\n".join(lines)

if __name__ == "__main__":
    print(full_report())
