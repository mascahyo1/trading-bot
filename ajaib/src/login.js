const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

// Proxy configuration - gunakan proxy di VPS
const PROXY_SERVER = process.env.PROXY_SERVER || '';

async function ensureSessionDir() {
    if (!fs.existsSync(SESSION_DIR)) {
        fs.mkdirSync(SESSION_DIR, { recursive: true });
    }
}

async function login() {
    await ensureSessionDir();

    console.log('========================================');
    console.log('  AJAIB TRADING BOT - LOGIN');
    console.log('========================================');
    if (PROXY_SERVER) {
        console.log(`  Proxy: ${PROXY_SERVER}`);
    }
    console.log('');

    // Fingerprint dari Chrome asli user (copy dari browser yang bisa login), fallback ke default
    let fp = null;
    try {
        const fpPath = path.join(__dirname, '..', 'fingerprint.json');
        if (fs.existsSync(fpPath)) fp = JSON.parse(fs.readFileSync(fpPath, 'utf-8'));
    } catch (e) {}
    const fpUA = fp && fp.userAgent ? fp.userAgent : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

    const launchOptions = {
        headless: false,
        args: [
            '--start-maximized',
            '--enable-gpu',
            '--ignore-gpu-blocklist',
            '--disable-blink-features=AutomationControlled',
        ],
    };

    // Add proxy hanya jika di-set (direct login tanpa tunnel = no proxy, biar tidak proxy failed)
    if (PROXY_SERVER) {
        launchOptions.proxy = { server: PROXY_SERVER };
    }

    const browser = await chromium.launch(launchOptions);

    const context = await browser.newContext({
        viewport: fp && fp.screen ? { width: fp.screen.width, height: fp.screen.height } : { width: 1280, height: 800 },
        userAgent: fpUA,
        locale: fp && fp.language ? fp.language : 'en-US',
        extraHTTPHeaders: {
            'Accept-Language': fp && fp.languages ? fp.languages.join(',') : 'en-US,en;q=0.9,id;q=0.8',
        },
    });
    // Inject fingerprint ke navigator/webgl biar tidak kedetect automation (ht2 403 Forbidden hilang)
    if (fp) {
        await context.addInitScript((f) => {
            try {
                Object.defineProperty(navigator, 'platform', { get: () => f.platform });
                Object.defineProperty(navigator, 'vendor', { get: () => f.vendor });
                Object.defineProperty(navigator, 'language', { get: () => f.language });
                Object.defineProperty(navigator, 'languages', { get: () => f.languages });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => f.hardwareConcurrency });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => f.deviceMemory });
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                // WebGL vendor spoof
                const origGetParam = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(pname) {
                    if (pname === 37445) return f.webgl.vendor; // UNMASKED_VENDOR_WEBGL
                    if (pname === 37446) return f.webgl.renderer; // UNMASKED_RENDERER_WEBGL
                    return origGetParam.apply(this, arguments);
                };
                if (window.WebGL2RenderingContext) {
                    const orig2 = WebGL2RenderingContext.prototype.getParameter;
                    WebGL2RenderingContext.prototype.getParameter = function(pname) {
                        if (pname === 37445) return f.webgl.vendor;
                        if (pname === 37446) return f.webgl.renderer;
                        return orig2.apply(this, arguments);
                    };
                }
                // Hapus flag automation
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            } catch (e) {}
        }, fp);
    }

    const page = await context.newPage();

    console.log('Step 1: Buka login.ajaib.co.id/login');
    console.log('Input email/password di browser...');
    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'networkidle',
        timeout: 0,
    });

    await page.waitForURL(/invest\.ajaib\.co\.id\/(pin|home)/, { timeout: 0 });

    const urlAfterLogin = page.url();
    console.log('Redirect ke:', urlAfterLogin);

    if (urlAfterLogin.includes('/pin')) {
        console.log('Step 2: Halaman PIN terdeteksi');
        console.log('Input PIN di browser...');
        await page.waitForURL('https://invest.ajaib.co.id/home', { timeout: 0 });
    }

    const finalUrl = page.url();
    console.log('Final URL:', finalUrl);

    if (!finalUrl.includes('/home')) {
        console.log('Gagal: tidak redirect ke home');
        await browser.close();
        process.exit(1);
    }

    console.log('Login berhasil!');

    await context.storageState({ path: SESSION_FILE });
    console.log('Session tersimpan di:', SESSION_FILE);

    await page.waitForTimeout(2000);
    await browser.close();
    console.log('Selesai.');
}

login().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
