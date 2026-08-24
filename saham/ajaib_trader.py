"""
Ajaib Trader - Browser Automation untuk Eksekusi Transaksi Saham

Module ini menyediakan interface untuk berinteraksi dengan website Ajaib
(invest.ajaib.co.id) menggunakan Playwright browser automation.

Ajaib TIDAK memiliki trading API publik, sehingga semua operasi
(buy/sell/portfolio) dilakukan melalui otomatisasi browser.

Prasyarat:
    Session login Ajaib harus sudah ada di file storage-state.json.
    Session ini dibuat sekali via Node.js:
        cd ajaib && npm run login

Alur Kerja:
    1. Launch Chromium headless dengan storage_state (session cookies)
    2. Verifikasi masih login (cek redirect ke halaman login)
    3. Navigasi ke halaman target (home / stock detail)
    4. Scrape data portfolio ATAU klik tombol beli/jual + isi form lot
    5. Simpan session state terbaru (refresh cookies)
    6. Tutup browser

Catatan Penting:
    - Playwright Python memakai snake_case: new_page(), storage_state(),
      BUKAN camelCase seperti versi JavaScript (newPage, storageState).
    - Parsing portfolio berbasis regex terhadap innerText halaman,
      sehingga RAPUH jika Ajaib mengubah layout/tampilan website.
    - Setiap operasi membuka & menutup browser baru (isolated),
      aman untuk dipanggil berulang tanpa memory leak.

Struktur Data Portfolio:
    {
        "cash": 1500000,           # Saldo dana menganggur (IDR)
        "stocks": [                 # Daftar kepemilikan saham
            {"code": "BBCA", "lots": 5, "price": 9500},
        ],
        "totalValue": 0,            # (tidak digunakan)
        "totalStockValue": 0        # (tidak digunakan)
    }

Author: AI Trading Bot
"""

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

# User-Agent yang sama dengan browser lokal - bypass Cloudflare
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'


class AjaibTrader:
    """
    Automator transaksi saham di website Ajaib via Playwright.

    Semua method publik bersifat synchronous (blocking) dan bisa langsung
    dipanggil dari bot utama. Versi async tersedia untuk penggunaan lanjutan.

    Attributes:
        session_file (str): Path ke file session Playwright (storage-state.json)
        base_url (str): Base URL website Ajaib
        _playwright: Instance playwright yang sedang aktif (internal)
        _browser: Instance browser Chromium yang sedang aktif (internal)
    """

    def __init__(self):
        """
        Inisialisasi trader. Tidak membuka browser di sini;
        browser dibuka per-operasi lalu ditutup setelah selesai.
        """
        self.session_file = AJAIB_SESSION_FILE
        self.base_url = AJAIB_BASE_URL
        self._playwright = None
        self._browser = None

    def _check_session(self):
        """
        Cek apakah file session Ajaib ada.

        Returns:
            bool: True jika file session ada, False jika tidak.
                  Jika False, user harus login manual via `npm run login`.
        """
        if not os.path.exists(self.session_file):
            logger.error("Ajaib session not found. Run Node.js login first.")
            return False
        return True

    async def _init_browser(self):
        """
        Launch Chromium headless baru dengan stealth mode & User-Agent custom
        untuk bypass Cloudflare bot detection.

        User-Agent di-match persis dengan browser lokal user agar Cloudflare
        tidak mendeteksi sebagai headless/automated browser.

        Returns:
            Browser: Instance Chromium headless yang siap dipakai.
        """
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            # User-Agent sama dengan browser lokal untuk hindari deteksi bot
            args=['--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36']
        )
        return self._browser

    async def _apply_stealth(self, page):
        """
        Terapkan stealth mode pada halaman untuk hindari deteksi bot oleh Cloudflare.

        Memodifikasi fingerprint browser (webdriver, plugins, languages, dll)
        agar terlihat seperti user biasa.

        Args:
            page: Halaman Playwright yang akan di-stealth-kan.
        """
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
        except Exception as e:
            logger.warning(f"Stealth apply failed: {e}")

    async def _close(self):
        """Tutup browser dan stop playwright instance (cleanup)."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _ensure_logged_in(self, context):
        """
        Verifikasi session masih valid dengan membuka halaman home.

        Logika: jika Ajaib me-redirect ke halaman login, artinya
        cookie/session sudah expired dan harus login ulang manual.

        Args:
            context: BrowserContext dengan storage_state dimuat

        Returns:
            bool: True jika masih login, False jika session expired.
        """
        page = await context.new_page()
        await self._apply_stealth(page)
        await page.goto(f"{self.base_url}/home", wait_until="networkidle", timeout=60000)
        url = page.url
        title = await page.title()
        await page.close()
        # Cloudflare challenge: URL tetap /home tapi title berubah
        if "login" in url.lower() or "Cloudflare" in title or "Attention Required" in title:
            logger.error(f"Session expired or Cloudflare challenge (title={title})")
            return False
        return True

    async def get_portfolio_async(self):
        """
        Scrape data portfolio dari halaman home Ajaib.

        Parsing dilakukan di dalam browser via page.evaluate() dengan strategi:
          1. CASH: cari angka setelah kata "Saldo"/"Cash"/"Dana" via regex.
             Valid jika nilainya > 1000 (hindari salah ambil harga satuan).
          2. STOCKS: cari baris yang merupakan kode saham valid (4 huruf kapital),
             lalu scan maksimal 10 baris berikutnya untuk mencari jumlah lot
             ("N lot") dan harga (>100).

        Returns:
            dict | None: Portfolio data {cash, stocks: [{code, lots, price}]}
                         atau None jika gagal (no session / expired / error).
        """
        if not self._check_session():
            return None

        browser = await self._init_browser()
        try:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
            if not await self._ensure_logged_in(context):
                logger.error("Session expired")
                return None

            page = await context.new_page()
            await self._apply_stealth(page)
            await page.goto(f"{self.base_url}/home", wait_until="networkidle", timeout=30000)

            # Debug: log URL dan title untuk diagnose masalah scraping
            page_title = await page.title()
            logger.info(f"Ajaib page: url={page.url}, title={page_title}")
            if "Cloudflare" in page_title or "Attention Required" in page_title:
                logger.error("Cloudflare challenge detected during portfolio scrape")
                await context.storage_state(path=self.session_file)
                await page.close()
                await context.close()
                return None

            # JavaScript dieksekusi DI DALAM browser (context halaman).
            # Perhatikan escaping \\s, \\d dsb karena string Python -> JS regex.
            portfolio = await page.evaluate("""() => {
                const result = {
                    cash: 0,
                    stocks: [],
                    totalValue: 0,
                    totalStockValue: 0,
                };

                const allText = document.body.innerText;

                // Cari Buying Power - format: "Buying Power Rp 100.000"
                const bpMatch = allText.match(/Buying Power\\s*Rp\\s*([\\d.,]+)/i);
                if (bpMatch) {
                    result.cash = parseFloat(bpMatch[1].replace(/\\./g, '').replace(',', '.'));
                }

                // Fallback: cari "Total Investasi" atau pola Rp lain
                if (result.cash === 0) {
                    const totalInv = allText.match(/Total Investasi\\s*Rp\\s*([\\d.,]+)/i);
                    if (totalInv) {
                        result.cash = parseFloat(totalInv[1].replace(/\\./g, '').replace(',', '.'));
                    }
                }

                // Scan saham dari tabel - format: KODE  Volume  Harga  Change
                const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i];
                    // Kode saham 4 huruf kapital
                    if (/^[A-Z]{4}$/.test(line)) {
                        let lots = 0;
                        let price = 0;
                        // Cari harga di baris berikutnya (format: Rp xxx)
                        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                            const priceMatch = lines[j].match(/Rp\\s*(\\d{3,}(?:[.,]\\d+)?)/);
                            if (priceMatch) {
                                price = parseFloat(priceMatch[1].replace(/\\./g, '').replace(',', '.'));
                                break;
                            }
                        }
                        // Default 0 lots jika tidak ditemukan
                        result.stocks.push({code: line, lots: 0, price: price});
                    }
                }

                return result;
            }""")

            # Debug: log hasil scraping untuk diagnose
            logger.info(f"Ajaib scrape result: cash={portfolio.get('cash', 0)}, stocks={len(portfolio.get('stocks', []))} items")
            # Debug: log page text jika cash=0
            if portfolio.get('cash', 0) == 0:
                debug_text = await page.evaluate(() => document.body.innerText.substring(0, 500))
                logger.warning(f"DEBUG: Page text when cash=0: {repr(debug_text)}")

            # Simpan session state terbaru supaya cookies selalu fresh
            await context.storage_state(path=self.session_file)
            await page.close()
            await context.close()
            return portfolio
        except Exception as e:
            logger.error(f"Portfolio fetch error: {e}")
            return None
        finally:
            await self._close()

    async def buy_stock_async(self, stock_code, lots):
        """
        Eksekusi order BELI via browser automation.

        Langkah-langkah di halaman detail saham (/{CODE}):
          1. Klik tombol "Beli" (coba beberapa selector umum)
          2. Isi input lot dengan jumlah yang diminta
          3. Klik tombol konfirmasi

        Selector menggunakan fallback berlapis karena struktur HTML Ajaib
        bisa berubah: text button → class attribute → data-testid.

        PERINGATAN:
            - Order dikirim sebagai MARKET/LIMIT sesuai default form Ajaib.
            - Tidak ada verifikasi order sukses di sisi broker!
              Return success hanya berarti klik berhasil dilakukan.
            - Harga eksekusi aktual bisa beda dari current_price bot.

        Args:
            stock_code (str): Kode saham format .JK atau plain (mis. "BBCA.JK")
            lots (int): Jumlah lot yang dibeli (1 lot = 100 lembar)

        Returns:
            dict: {"success": True/False, "code": str, "lots": int, "side": "BUY"}
                  atau {"success": False, "error": str} jika gagal.
        """
        if not self._check_session():
            return {"success": False, "error": "No session"}

        # Konversi "BBCA.JK" -> "BBCA" untuk URL Ajaib
        code = STOCK_CODE_MAP.get(stock_code, stock_code.replace(".JK", ""))
        browser = await self._init_browser()
        try:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
            if not await self._ensure_logged_in(context):
                return {"success": False, "error": "Session expired"}

            page = await context.new_page()
            await self._apply_stealth(page)
            await page.goto(f"{self.base_url}/stock/{code}", wait_until="networkidle", timeout=30000)

            # Step 1: Klik tombol Beli — coba text-based dulu, lalu class-based
            buy_button = page.locator("button:has-text('Beli'), button:has-text('Buy'), [data-testid='buy-button']")
            if await buy_button.count() == 0:
                buy_button = page.locator("[class*='buy'], [class*='Beli']")

            if await buy_button.count() > 0:
                await buy_button.first.click()
                await page.wait_for_timeout(1000)  # tunggu form/order panel muncul

            # Step 2: Isi input jumlah lot
            lot_input = page.locator("input[placeholder*='lot'], input[name*='lot'], input[name*='qty'], input[name*='quantity']")
            if await lot_input.count() > 0:
                await lot_input.first.fill(str(lots))
                await page.wait_for_timeout(500)

            # Step 3: Klik konfirmasi order
            confirm_button = page.locator("button:has-text('Beli'), button:has-text('Confirm'), button:has-text('Submit')")
            if await confirm_button.count() > 0:
                await confirm_button.first.click()
                await page.wait_for_timeout(2000)  # tunggu proses submit

            await context.storage_state(path=self.session_file)
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
        """
        Eksekusi order JUAL via browser automation.

        Alur sama seperti buy_stock_async, tapi klik tombol "Jual".
        Lihat dokumentasi buy_stock_async untuk detail langkah & peringatan.

        Args:
            stock_code (str): Kode saham format .JK atau plain (mis. "BBCA.JK")
            lots (int): Jumlah lot yang dijual

        Returns:
            dict: {"success": True/False, "code": str, "lots": int, "side": "SELL"}
                  atau {"success": False, "error": str} jika gagal.
        """
        if not self._check_session():
            return {"success": False, "error": "No session"}

        code = STOCK_CODE_MAP.get(stock_code, stock_code.replace(".JK", ""))
        browser = await self._init_browser()
        try:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
            if not await self._ensure_logged_in(context):
                return {"success": False, "error": "Session expired"}

            page = await context.new_page()
            await self._apply_stealth(page)
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

            await context.storage_state(path=self.session_file)
            await page.close()
            await context.close()

            logger.info(f"Sell order placed: {code} x{lots} lots")
            return {"success": True, "code": code, "lots": lots, "side": "SELL"}

        except Exception as e:
            logger.error(f"Sell error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            await self._close()

    # ================================================================
    # Synchronous wrappers — dipanggil dari bot.py (blocking style)
    # asyncio.run() membuat event loop baru per panggilan.
    # ================================================================

    def buy(self, stock_code, lots):
        """Wrapper sync untuk buy_stock_async(). Lihat docstring async version."""
        return asyncio.run(self.buy_stock_async(stock_code, lots))

    def sell(self, stock_code, lots):
        """Wrapper sync untuk sell_stock_async(). Lihat docstring async version."""
        return asyncio.run(self.sell_stock_async(stock_code, lots))

    def get_portfolio(self):
        """Wrapper sync untuk get_portfolio_async(). Lihat docstring async version."""
        return asyncio.run(self.get_portfolio_async())


def main():
    """
    Entry point untuk testing standalone.

    Usage:
        python ajaib_trader.py

    Output: JSON portfolio dari Ajaib ke stdout, atau pesan error.
    Berguna untuk debug parsing tanpa harus menjalankan bot penuh.
    """
    trader = AjaibTrader()
    portfolio = trader.get_portfolio()
    if portfolio:
        print(json.dumps(portfolio, indent=2))
    else:
        print("Failed to fetch portfolio")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
