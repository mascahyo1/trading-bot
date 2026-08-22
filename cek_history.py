from exchange import IndodaxExchange
import json

ex = IndodaxExchange()

print("=== myTrades response ===")
trades = ex.get_my_trades(symbol="BTCIDR", limit=10)
print(json.dumps(trades, indent=2)[:1000])
