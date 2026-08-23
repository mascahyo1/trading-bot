import logging
import asyncio
import json
import os
import sys
import time
from datetime import datetime

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from config import (
    AJAIB_SESSION_FILE,
    AJAIB_BASE_URL,
    STOCK_CODE_MAP,
    now_jakarta,
)


class AjaibTrader:
    def __init__(self):
        self.session_file = AJAIB_SESSION_FILE
        self.base_url = AJAIB_BASE_URL
        self._playwright = None
        self._browser = None

    def _check_session(self):
        if not os.path.exists(self.session_file):
            logger.error("Ajaib session not found. Run Node.js login first.")
            return False
        return True

    async def _init_browser(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def _close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _ensure_logged_in(self, context):
        page = await context.new_page()
        await page.goto(f"{self.base_url}/home", wait_until="networkidle", timeout=60000)
        url = page.url
        await page.close()
        return "login" not in url.lower()

    async def get_portfolio_async(self):
        if not self._check_session():
            return None

        browser = await self._init_browser()
        try:
            context = await browser.new_context(storage_state=self.session_file)
            if not await self._ensure_logged_in(context):
                logger.error("Session expired")
                return None

            page = await context.new_page()
            await page.goto(f"{self.base_url}/home", wait_until="networkidle", timeout=30000)

            portfolio = await page.evaluate("""() => {
                const result = {
                    cash: 0,
                    stocks: [],
                    totalValue: 0,
                    totalStockValue: 0,
                };

                const allText = document.body.innerText;
                const cashPatterns = [
                    /Saldo[^:]*:?\\s*Rp?\\s*([\\d.,]+)/i,
                    /Cash[^:]*:?\\s*Rp?\\s*([\\d.,]+)/i,
                    /Dana[^:]*:?\\s*Rp?\\s*([\\d.,]+)/i,
                    /Rp\\s*([\\d.,]{4,})/,
                ];
                for (const pattern of cashPatterns) {
                    const match = allText.match(pattern);
                    if (match) {
                        const raw = match[1].replace(/\\./g, '').replace(',', '.');
                        const val = parseFloat(raw);
                        if (val > 1000) {
                            result.cash = val;
                            break;
                        }
                    }
                }

                const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    if (/^[A-Z]{4}$/.test(line)) {
                        const stockCode = line;
                        let lots = 0;
                        let price = 0;
                        for (let j = i + 1; j < Math.min(i + 10, lines.length); j++) {
                            const nextLine = lines[j];
                            const lotMatch = nextLine.match(/(\\d+)\\s*lot/i);
                            if (lotMatch) {
                                lots = parseInt(lotMatch[1]);
                            }
                            const priceMatch = nextLine.match(/(\\d{3,}(?:[.,]\\d+)?)/);
                            if (priceMatch) {
                                const p = parseFloat(priceMatch[1].replace(/\\./g, '').replace(',', '.'));
                                if (p > 100) price = p;
                            }
                        }
                        if (lots > 0) {
                            result.stocks.push({
                                code: stockCode,
                                lots: lots,
                                price: price,
                            });
                        }
                    }
                }

                return result;
            }""")

            await context.storageState(path=self.session_file)
            await page.close()
            await context.close()
            return portfolio
        except Exception as e:
            logger.error(f"Portfolio fetch error: {e}")
            return None
        finally:
            await self._close()

    async def buy_stock_async(self, stock_code, lots):
        if not self._check_session():
            return {"success": False, "error": "No session"}

        code = STOCK_CODE_MAP.get(stock_code, stock_code.replace(".JK", ""))
        browser = await self._init_browser()
        try:
            context = await browser.new_context(storage_state=self.session_file)
            if not await self._ensure_logged_in(context):
                return {"success": False, "error": "Session expired"}

            page = await context.new_page()
            await page.goto(f"{self.base_url}/stock/{code}", wait_until="networkidle", timeout=30000)

            buy_button = page.locator("button:has-text('Beli'), button:has-text('Buy'), [data-testid='buy-button']")
            if await buy_button.count() == 0:
                buy_button = page.locator("[class*='buy'], [class*='Beli']")

            if await buy_button.count() > 0:
                await buy_button.first.click()
                await page.wait_for_timeout(1000)

            lot_input = page.locator("input[placeholder*='lot'], input[name*='lot'], input[name*='qty'], input[name*='quantity']")
            if await lot_input.count() > 0:
                await lot_input.first.fill(str(lots))
                await page.wait_for_timeout(500)

            confirm_button = page.locator("button:has-text('Beli'), button:has-text('Confirm'), button:has-text('Submit')")
            if await confirm_button.count() > 0:
                await confirm_button.first.click()
                await page.wait_for_timeout(2000)

            await context.storageState(path=self.session_file)
            await page.close()
            await context.close()

            logger.info(f"Buy order placed: {code} x{lots} lots")
            return {"success": True, "code": code, "lots": lots, "side": "BUY"}

        except Exception as e:
            logger.error(f"Buy error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await self._close()

    async def sell_stock_async(self, stock_code, lots):
        if not self._check_session():
            return {"success": False, "error": "No session"}

        code = STOCK_CODE_MAP.get(stock_code, stock_code.replace(".JK", ""))
        browser = await self._init_browser()
        try:
            context = await browser.new_context(storage_state=self.session_file)
            if not await self._ensure_logged_in(context):
                return {"success": False, "error": "Session expired"}

            page = await context.new_page()
            await page.goto(f"{self.base_url}/stock/{code}", wait_until="networkidle", timeout=30000)

            sell_button = page.locator("button:has-text('Jual'), button:has-text('Sell'), [data-testid='sell-button']")
            if await sell_button.count() == 0:
                sell_button = page.locator("[class*='sell'], [class*='Jual']")

            if await sell_button.count() > 0:
                await sell_button.first.click()
                await page.wait_for_timeout(1000)

            lot_input = page.locator("input[placeholder*='lot'], input[name*='lot'], input[name*='qty'], input[name*='quantity']")
            if await lot_input.count() > 0:
                await lot_input.first.fill(str(lots))
                await page.wait_for_timeout(500)

            confirm_button = page.locator("button:has-text('Jual'), button:has-text('Confirm'), button:has-text('Submit')")
            if await confirm_button.count() > 0:
                await confirm_button.first.click()
                await page.wait_for_timeout(2000)

            await context.storageState(path=self.session_file)
            await page.close()
            await context.close()

            logger.info(f"Sell order placed: {code} x{lots} lots")
            return {"success": True, "code": code, "lots": lots, "side": "SELL"}

        except Exception as e:
            logger.error(f"Sell error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await self._close()

    def buy(self, stock_code, lots):
        return asyncio.run(self.buy_stock_async(stock_code, lots))

    def sell(self, stock_code, lots):
        return asyncio.run(self.sell_stock_async(stock_code, lots))

    def get_portfolio(self):
        return asyncio.run(self.get_portfolio_async())


def main():
    trader = AjaibTrader()
    portfolio = trader.get_portfolio()
    if portfolio:
        print(json.dumps(portfolio, indent=2))
    else:
        print("Failed to fetch portfolio")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
