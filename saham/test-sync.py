import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from ajaib_trader import AjaibTrader

trader = AjaibTrader()
portfolio = trader.get_portfolio()
print("Result:", json.dumps(portfolio, indent=2) if portfolio else "None")
