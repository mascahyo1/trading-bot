import sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(message)s')

from ajaib_trader import AjaibTrader

trader = AjaibTrader()
portfolio = trader.get_portfolio()
print("Result:", json.dumps(portfolio, indent=2) if portfolio else "None")
