import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from ajaib_trader import AjaibTrader

trader = AjaibTrader()
portfolio = trader.get_portfolio()
if portfolio:
    print("cash:", portfolio.get("cash"))
    print("stocks:", len(portfolio.get("stocks", [])))
    print("data:", json.dumps(portfolio, indent=2)[:1000])
else:
    print("None - blocked or session expired")
