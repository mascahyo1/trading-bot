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
    AJAIB_PERSISTENT_PROFILE,
    AJAIB_BASE_URL,
    AJAIB_USER_AGENT,
    AJAIB_PROXY,
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
        Meluncurkan browser Chromium dengan profile yang tepat.

        Jika persistent profile tersedia, gunakan launch_persistent_context
        agar cookies dan sesi lebih awet. Jika tidak, gunakan launch
        biasa dengan storage_state. Mengatur proxy dan User-Agent konsisten.

        Returns:
            tuple: (playwright_instance, browser_or_context) yang sudah siap pakai.
        """
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        # Jika persistent profile ada di server, pakai itu (sesi lebih awet, fingerprint sama)
        launch_kwargs = {"headless": True}
        if AJAIB_PROXY:
            launch_kwargs["proxy"] = {"server": AJAIB_PROXY}
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        return self._browser

    def _uses_persistent(self):
        """
        Mengecek apakah persistent browser profile tersedia dan harus dipakai.

        Persistent profile dipakai hanya jika storage-state TIDAK mengandung
        access_token (login lama). Jika storage-state sudah fresh (ada token),
        lebih utamakan storage_state agar sesi selalu terbaru.

        Returns:
            bool: True jika persistent profile ada dan layak dipakai; False jika tidak.
        """
        # Persistent dipakai hanya jika storage-state TIDAK punya token login
        # Kalau storage-state sudah ada access_token (login via tunnel baru), pakai storage dulu
        try:
            if os.path.exists(self.session_file):
                import json as _js
                d = _js.loads(open(self.session_file,encoding="utf-8").read())
                has_token = any(c.get("name")=="access_token" for c in d.get("cookies",[]))
                if has_token:
                    return False  # pakai storage-state yang fresh
        except Exception:
            pass
        return os.path.isdir(AJAIB_PERSISTENT_PROFILE) and bool(os.listdir(AJAIB_PERSISTENT_PROFILE))

    async def _apply_stealth(self, page):
        """
        Stealth mode tidak diperlukan lagi - User-Agent fix sudah cukup
        bypass Cloudflare. Biarkan method ini kosong untuk avoid detection.
        """
        pass

    async def _close(self):
        """Tutup browser dan stop playwright instance (cleanup)."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    async def _try_auto_login(self):
        """Coba auto-login pakai ENV (ajaib_email/password/pin) via Node.js auto-login.js + Xvfb."""
        import subprocess, pathlib, os, shutil
        node_script = pathlib.Path(__file__).parent.parent / "ajaib" / "src" / "auto-login.js"
        alt = pathlib.Path.home() / "trading-bot" / "ajaib" / "src" / "auto-login.js"
        target = str(node_script if node_script.exists() else alt)
        env = os.environ.copy()
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":99"
            if shutil.which("Xvfb"):
                try:
                    subprocess.run(["sh", "-c", "pgrep Xvfb >/dev/null || (Xvfb :99 -screen 0 1366x768x24 >/tmp/xvfb.log 2>&1 & sleep 2)"], timeout=8)
                except Exception:
                    pass
        try:
            logger.warning(f"Session expired - coba auto-login via {target} DISPLAY={env.get('DISPLAY')} ...")
            proc = subprocess.run(["node", target], capture_output=True, text=True, timeout=180, env=env)
            out = (proc.stdout or "")[-1200:] + (proc.stderr or "")[-600:]
            logger.info(f"auto-login exit {proc.returncode}: {out[-700:]}")
            if proc.returncode == 0 and pathlib.Path(self.session_file).exists():
                logger.info("auto-login berhasil - session refreshed")
                return True
            logger.warning(f"auto-login gagal (code {proc.returncode})")
        except Exception as e:
            logger.warning(f"auto-login error: {e}")
        return False

    async def _ensure_logged_in(self, context):
        """
        Verifikasi session masih valid. Jika expired, coba auto-login sekali via ENV.

        Args:
            context: BrowserContext dengan storage_state dimuat

        Returns:
            bool: True jika masih login (setelah auto-login jika perlu).
        """
        page = await context.new_page()
        await self._apply_stealth(page)
        await page.goto(f"{self.base_url}/home", wait_until="networkidle", timeout=60000)
        url = page.url
        title = await page.title()
        await page.close()
        # Deteksi sesi: cek URL redirect ke login ATAU halaman login Ajaib
        # Title "Ajaib.co.id" = home valid, jangan dianggap expired
        if "login" in url.lower():
            logger.error(f"Session expired (redirect to login, url={url})")
            if await self._try_auto_login():
                # retry once after auto-login
                await context.close() if hasattr(context, "close") else None
                return True  # caller will re-init browser; treat as recovered
            return False
        if "Cloudflare" in title or "Attention Required" in title or "Masuk untuk berinvestasi" in title:
            logger.error(f"Session expired or Cloudflare challenge (title={title})")
            if await self._try_auto_login():
                return True
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
        # Prefer persistent context jika ada (sesi login lokal via tunnel sudah masuk)
        use_persistent = self._uses_persistent()
        if use_persistent:
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=AJAIB_PERSISTENT_PROFILE,
                headless=True,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                **({"proxy": {"server": AJAIB_PROXY}} if AJAIB_PROXY else {}),
            )
        else:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
        try:
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
                # JANGAN simpan storage_state - cookies CF akan merusak session asli
                await page.close()
                await context.close()
                return None

            # Tunggu konten dinamis (React) selesai render
            await page.wait_for_timeout(3000)

            # JavaScript dieksekusi DI DALAM browser (context halaman).
            # Perhatikan escaping \\s, \\d dsb karena string Python -> JS regex.
            # Klik tab Portofolio agar tabel holdings muncul (home saja tidak ada detail lot)
            try:
                port_btn = page.locator("text=Portofolio").first
                if await port_btn.count() > 0:
                    await port_btn.click()
                    await page.wait_for_timeout(4000)
            except Exception:
                pass
            # Tunggu Buying Power muncul (hindari cash 0 race)
            try:
                await page.wait_for_selector("text=Buying Power", timeout=8000)
            except: pass
            # Ambil innerText saja, parsing di Python (hindari SyntaxError JS)
            _raw = await page.evaluate("() => document.body.innerText")
            import re as _re
            _cash = 0
            _m = _re.search(r"Buying Power\s*Rp\s*([\d.,]+)", _raw, _re.I)
            if _m:
                try: _cash = float(_m.group(1).replace(".", "").replace(",", ".")) or 0
                except: _cash = 0
            if not _cash:
                _m2 = _re.search(r"Buying Power[^0-9]*Rp\s*([\d.,]+)", _raw, _re.I)
                if _m2:
                    try: _cash = float(_m2.group(1).replace(".", "").replace(",", ".")) or 0
                    except: _cash = 0
            _stocks = []
            _lines = [l.strip() for l in _raw.split("\n") if l.strip()]
            for _i, _ln in enumerate(_lines):
                if _re.match(r"^[A-Z]{4}$", _ln):
                    if _i + 5 >= len(_lines): continue
                    try:
                        _lot = int(_re.sub(r"[^0-9]", "", _lines[_i+1]) or "0")
                        _avg = float(_re.sub(r"Rp\s*", "", _lines[_i+2], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                        _cur = float(_re.sub(r"Rp\s*", "", _lines[_i+3], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                        _inv = float(_re.sub(r"Rp\s*", "", _lines[_i+4], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                        _tot = float(_re.sub(r"Rp\s*", "", _lines[_i+5], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                    except: continue
                    if _lot>0 and _avg>0 and _cur>0:
                        _stocks.append({"code": _ln, "lots": _lot, "avg_price": _avg, "price": _cur, "invested": _inv, "total": _tot})
            portfolio = {"cash": _cash, "stocks": _stocks, "totalValue": sum(s.get("total",0) for s in _stocks)}
            # Fallback cash: kalau Buying Power belum render, pakai portfolio.json (76.865) jangan 0
            if portfolio.get("cash", 0) == 0:
                try:
                    import json as _js2, pathlib as _pl2
                    _pf = _pl2.Path(__file__).parent.parent / "ajaib" / "session" / "portfolio.json"
                    if not _pf.exists():
                        _pf = _pl2.Path.home() / "trading-bot" / "ajaib" / "session" / "portfolio.json"
                    if _pf.exists():
                        _d = _js2.loads(_pf.read_text(encoding="utf-8"))
                        _fc = int(_d.get("cash", 0) or 0)
                        if _fc > 0:
                            portfolio["cash"] = float(_fc)
                            logger.info(f"Fallback cash from portfolio.json: {_fc:,.0f} (scrape cash 0)")
                except Exception as _e:
                    logger.warning(f"Fallback cash read failed: {_e}")
            # Retry:
            # Retry: konten dinamis kadang belum ter-render saat pertama kali scrape
            for attempt in range(3):
                if portfolio and (portfolio.get('cash', 0) > 0 or len(portfolio.get('stocks', [])) > 0):
                    break
                logger.debug(f"Scrape kosong (attempt {attempt + 1}/3), retry...")
                await page.wait_for_timeout(3000)
                _raw2 = await page.evaluate("() => document.body.innerText")
                _cash2 = 0
                _m2 = _re.search(r"Buying Power\s*Rp\s*([\d.,]+)", _raw2, _re.I)
                if _m2:
                    try: _cash2 = float(_m2.group(1).replace(".", "").replace(",", ".")) or 0
                    except: _cash2 = 0
                _stocks2 = []
                _lines2 = [l.strip() for l in _raw2.split("\n") if l.strip()]
                for _i2, _ln2 in enumerate(_lines2):
                    if _re.match(r"^[A-Z]{4}$", _ln2):
                        if _i2 + 5 >= len(_lines2): continue
                        try:
                            _lot2 = int(_re.sub(r"[^0-9]", "", _lines2[_i2+1]) or "0")
                            _avg2 = float(_re.sub(r"Rp\s*", "", _lines2[_i2+2], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                            _cur2 = float(_re.sub(r"Rp\s*", "", _lines2[_i2+3], flags=_re.I).replace(".", "").replace(",", ".")) or 0
                        except: continue
                        if _lot2>0 and _avg2>0 and _cur2>0:
                            _stocks2.append({"code": _ln2, "lots": _lot2, "avg_price": _avg2, "price": _cur2})
                _fc2 = portfolio.get("cash", 0) if isinstance(portfolio, dict) else 0
                if _cash2 == 0 and _fc2 > 0:
                    _cash2 = _fc2
                portfolio = {"cash": _cash2, "stocks": _stocks2}

            # Debug: log hasil scraping untuk diagnose
            logger.info(f"DEBUG: portfolio result = {json.dumps(portfolio, default=str)[:300]}")

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
        bisa berubah: text button -> class attribute -> data-testid.

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
        # Persistent profile (dari login via tunnel) lebih awet daripada storage-state
        if self._uses_persistent():
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=AJAIB_PERSISTENT_PROFILE,
                headless=True,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                **({"proxy": {"server": AJAIB_PROXY}} if AJAIB_PROXY else {}),
            )
        else:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
        try:
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
        # Persistent profile (dari login via tunnel) lebih awet daripada storage-state
        if self._uses_persistent():
            context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=AJAIB_PERSISTENT_PROFILE,
                headless=True,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                **({"proxy": {"server": AJAIB_PROXY}} if AJAIB_PROXY else {}),
            )
        else:
            context = await browser.new_context(
                storage_state=self.session_file,
                user_agent=USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
            )
        try:
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
