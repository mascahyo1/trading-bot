const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

// Proxy configuration - gunakan proxy di VPS
const PROXY_SERVER = process.env.PROXY_SERVER || 'socks5://127.0.0.1:1080';

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

    const launchOptions = {
        headless: false,
        args: [
            '--start-maximized',
            '--enable-gpu',
            '--ignore-gpu-blocklist',
        ],
    };

    // Add proxy if configured
    if (PROXY_SERVER) {
        launchOptions.proxy = { server: PROXY_SERVER };
    }

    const browser = await chromium.launch(launchOptions);

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    });

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
