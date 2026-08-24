import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright

async def main():
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        headless=True,
        args=['--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36']
    )
    try:
        context = await browser.new_context(
            storage_state='/home/cahyo/trading-bot/ajaib/session/storage-state.json',
            viewport={'width': 1920, 'height': 1080},
        )
        page = await context.new_page()
        await page.goto('https://invest.ajaib.co.id/home', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        result = await page.evaluate('''() => {
            const allText = document.body.innerText.replace(/\\xa0/g, ' ');
            const bpMatch = allText.match(/Buying Power\\s*Rp\\s*([\\d.,]+)/i);
            return {cash: bpMatch ? parseFloat(bpMatch[1].replace(/\\./g, '').replace(',', '.')) : 0};
        }''')
        print("Result:", json.dumps(result, indent=2))

        await context.close()
    finally:
        await playwright.stop()

asyncio.run(main())
