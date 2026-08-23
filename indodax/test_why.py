import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from config import MAX_OPEN_POSITIONS, MIN_ORDER_IDR, now_jakarta

history_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
trades = []
if os.path.exists(history_file):
    with open(history_file) as f:
        trades = json.load(f)

total_trades = len(trades)
wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0

print(f"Total trades: {total_trades}")
print(f"Win rate: {win_rate:.1f}%")
print(f"Total PnL: {sum(t.get('pnl_amount', 0) for t in trades):+,.0f} IDR")

from exchange import IndodaxExchange
ex = IndodaxExchange()
balance = ex.get_idr_balance()
print(f"Balance: {balance:,.0f} IDR")

bal = ex.get_balance()
open_count = 0
if bal and not bal.get("error"):
    for b in bal.get("balances", []):
        asset = b.get("asset", "")
        free = float(b.get("free", 0))
        if free > 0 and asset != "IDR":
            open_count += 1
            print(f"  {asset}: {free:.6f}")
print(f"Open positions: {open_count}/{MAX_OPEN_POSITIONS}")
