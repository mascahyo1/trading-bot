const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

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
    console.log('');
    console.log('Alur login:');
    console.log('  1. login.ajaib.co.id/login (email/password)');
    console.log('  2. invest.ajaib.co.id/pin (PIN)');
    console.log('  3. invest.ajaib.co.id/home (berhasil)');
    console.log('');

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    });

    const page = await context.newPage();

    // Step 1: Buka halaman login
    console.log('Step 1: Buka login.ajaib.co.id/login');
    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'networkidle',
        timeout: 30000,
    });

    console.log('Input email/password di browser...');
    console.log('(Tunggu sampai redirect ke halaman PIN)');

    // Tunggu redirect ke PIN page atau home (skip PIN)
    await page.waitForURL(/invest\.ajaib\.co\.id\/(pin|home)/, { timeout: 120000 });

    const urlAfterLogin = page.url();
    console.log('Redirect ke:', urlAfterLogin);

    // Step 2: Jika redirect ke PIN page, input PIN
    if (urlAfterLogin.includes('/pin')) {
        console.log('Step 2: Halaman PIN terdeteksi');
        console.log('Input PIN di browser...');
        console.log('(Tunggu sampai redirect ke home)');

        // Tunggu redirect ke home
        await page.waitForURL('**/home', { timeout: 120000 });
    }

    // Step 3: Verifikasi di home page
    const finalUrl = page.url();
    console.log('Final URL:', finalUrl);

    if (!finalUrl.includes('/home')) {
        console.log('Gagal: tidak redirect ke home');
        await browser.close();
        process.exit(1);
    }

    // Verifikasi content home page
    await page.waitForTimeout(2000);
    const title = await page.title();
    const hasContent = await page.evaluate(() => {
        const text = document.body.innerText;
        return text.includes('Buying Power') || text.includes('Portofolio') || text.includes('Beranda');
    });

    if (!hasContent) {
        console.log('Gagal: halaman home tidak punya content yang benar');
        console.log('Title:', title);
        await browser.close();
        process.exit(1);
    }

    console.log('Login berhasil! Content terverifikasi.');

    // Simpan session
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
