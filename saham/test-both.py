import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import seperti di ajaib_trader.py
from ajaib_trader import USER_AGENT, AjaibTrader

async def test_direct():
    """Test langsung seperti test-exact.py"""
    from playwright.async_api import async_playwright
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    try:
        context = await browser.new_context(
            storage_state='/home/cahyo/trading-bot/ajaib/session/storage-state.json',
            user_agent=USER_AGENT,
            viewport={'width': 1920, 'height': 1080},
        )
        page = await context.new_page()
        await page.goto('https://invest.ajaib.co.id/home', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        result = await page.evaluate('''() => {
            const allText = document.body.innerText.replace(/\\xa0/g, ' ');
            const bpMatch = allText.match(/Buying Power\\s*Rp\\s*([\\d.,]+)/i);
            return {cash: bpMatch ? parseFloat(bpMatch[1].replace(/\\./g, '').replace(',', '.')) : 0, bpMatch: bpMatch ? bpMatch[0] : null};
        }''')
        print("Direct test:", json.dumps(result))

        await context.close()
    finally:
        await playwright.stop()

async def test_via_class():
    """Test via AjaibTrader class"""
    trader = AjaibTrader()
    portfolio = trader.get_portfolio()
    print("Via class:", json.dumps(portfolio, indent=2) if portfolio else "None")

async def main():
    print("=== Test Direct ===")
    await test_direct()
    print("\n=== Test Via Class ===")
    await test_via_class()

asyncio.run(main())
