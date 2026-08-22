import json
import os
from datetime import datetime

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def analyze_performance():
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

    best_trade = max(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
    worst_trade = min(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None

    lines = [
        "📊 <b>PERFORMANCE ANALYTICS</b>",
        f"Total Trades: {total_trades}",
        f"Win Rate: {win_rate:.1f}%",
        f"Total PnL: {total_pnl:+,.0f} IDR",
        f"Avg Win: {avg_win:+,.0f} IDR",
        f"Avg Loss: {avg_loss:+,.0f} IDR",
    ]
    if best_trade:
        lines.append(f"Best: {best_trade['symbol']} {best_trade['pnl_amount']:+,.0f} IDR")
    if worst_trade:
        lines.append(f"Worst: {worst_trade['symbol']} {worst_trade['pnl_amount']:+,.0f} IDR")

    return "\n".join(lines)

if __name__ == "__main__":
    print(analyze_performance())
