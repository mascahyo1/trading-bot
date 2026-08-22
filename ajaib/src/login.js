const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

async function login() {
    if (!fs.existsSync(SESSION_DIR)) {
        fs.mkdirSync(SESSION_DIR, { recursive: true });
    }

    console.log('========================================');
    console.log('  AJAIB TRADING BOT - LOGIN');
    console.log('========================================');
    console.log('');
    console.log('Browser akan terbuka. Login manual.');
    console.log('Termasuk 2FA dan PIN.');
    console.log('');

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
    });

    const page = await context.newPage();

    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'networkidle',
        timeout: 30000,
    });

    console.log('1. Login di browser (email + password)...');
    console.log('2. Jawab 2FA security question...');
    console.log('3. Input PIN...');
    console.log('4. Tunggu sampai halaman home muncul...');
    console.log('');

    try {
        await page.waitForURL('**/home', { timeout: 180000 });
        console.log('Login berhasil! Menyimpan session...');
    } catch (e) {
        console.log('Timeout atau login gagal.');
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
