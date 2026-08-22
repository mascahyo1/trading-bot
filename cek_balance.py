from exchange import IndodaxExchange

ex = IndodaxExchange()
bal = ex.get_balance()
print("Balance response:")
for b in bal.get("balances", []):
    if float(b.get("free", 0)) > 0:
        print(f"  {b['asset']}: {b['free']} (locked: {b['locked']})")
