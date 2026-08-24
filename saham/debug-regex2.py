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

        result = await page.evaluate('''() => {
            const raw = document.body.innerText;
            const idx = raw.indexOf('Buying Power');
            const context = idx >= 0 ? raw.substring(idx, idx + 40) : 'NOT FOUND';
            const charCodes = [];
            for (let i = 0; i < context.length; i++) charCodes.push(context.charCodeAt(i));

            // Test replace
            const replaced = raw.replace(/\\xa0/g, ' ');
            const bpMatch = replaced.match(/Buying Power\\s*Rp\\s*([\\d.,]+)/i);

            return {
                context,
                charCodes,
                replacedLength: replaced.length,
                bpMatch: bpMatch ? bpMatch[0] : null,
                group1: bpMatch ? bpMatch[1] : null
            };
        }''')
        print(json.dumps(result, indent=2))

        await context.close()
    finally:
        await browser.close()

asyncio.run(main())
