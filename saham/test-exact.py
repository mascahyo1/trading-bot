import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from ajaib_trader import AjaibTrader, USER_AGENT

async def main():
    trader = AjaibTrader()
    browser = await trader._init_browser()
    try:
        context = await browser.new_context(
            storage_state=trader.session_file,
            user_agent=USER_AGENT,
            viewport={'width': 1920, 'height': 1080},
        )
        page = await context.new_page()
        await page.goto('https://invest.ajaib.co.id/home', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        # Exact same code as ajaib_trader.py
        result = await page.evaluate("""() => {
            try {
                const result = {cash: 0, stocks: [], totalValue: 0, totalStockValue: 0};
                const allText = document.body.innerText.replace(/\\xa0/g, ' ');
                const bpMatch = allText.match(/Buying Power\\s*Rp\\s*([\\d.,]+)/i);
                if (bpMatch) {
                    result.cash = parseFloat(bpMatch[1].replace(/\\./g, '').replace(',', '.'));
                }
                return result;
            } catch (e) {
                return {error: e.message};
            }
        }""")
        print("Result:", json.dumps(result, indent=2))

        await context.close()
    finally:
        await browser.close()

asyncio.run(main())
