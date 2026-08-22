from exchange import IndodaxExchange
import json

ex = IndodaxExchange()

print("=== All Balances ===")
bal = ex.get_balance()
if not bal.get("error"):
    for b in bal.get("balances", []):
        free = float(b.get("free", 0))
        locked = float(b.get("locked", 0))
        if free > 0 or locked > 0:
            print(f"  {b['asset']}: free={b['free']}, locked={b['locked']}")

print()
print("=== Deposit History (IDR) ===")
# Try deposit history
history = ex._v2_request("GET", "/api/v2/capital/deposit/hisrec", {"coin": "idr", "limit": 10})
print(json.dumps(history, indent=2)[:1500])

print()
print("=== Fiat Orders (Deposit/Withdraw) ===")
fiat = ex._v2_request("GET", "/api/v2/fiat/orders", {"limit": 10})
print(json.dumps(fiat, indent=2)[:1500])
