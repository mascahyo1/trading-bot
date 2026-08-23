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
    console.log('Browser akan terbuka.');
    console.log('Login manual di browser (email/password/2FA/PIN).');
    console.log('Setelah berhasil, session akan tersimpan otomatis.');
    console.log('');

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    });

    const page = await context.newPage();

    console.log('Navigating to Ajaib login page...');
    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'networkidle',
        timeout: 30000,
    });

    console.log('Waiting for login to complete...');
    console.log('(No timeout - wait until login succeeds)');
    console.log('');

    try {
        await page.waitForURL('**/home', { timeout: 0 });
        console.log('Login berhasil!');
    } catch (e) {
        console.log('Login gagal atau browser ditutup.');
        await browser.close();
        process.exit(1);
    }

    await context.storageState({ path: SESSION_FILE });
    console.log('Session tersimpan di:', SESSION_FILE);

    await page.waitForTimeout(2000);
    await browser.close();
    console.log('Selesai. Jalankan "npm start" untuk mulai trading.');
}

login().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
