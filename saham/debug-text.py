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

        title = await page.title()
        url = page.url
        print('Title:', title)
        print('URL:', url)

        # Get text and check for Buying Power
        text = await page.evaluate('''() => {
            const t = document.body.innerText;
            const idx = t.indexOf('Buying Power');
            return {
                hasBuyingPower: idx >= 0,
                context: idx >= 0 ? JSON.stringify(t.substring(idx, idx + 50)) : null,
                textLength: t.length,
                first500: t.substring(0, 500)
            };
        }''')
        print('Text debug:', json.dumps(text, indent=2))

        await context.close()
    finally:
        await browser.close()

asyncio.run(main())
