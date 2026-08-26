/**
 * Inject cookies dari storage-state.json ke persistent browser (port 9222).
 * Jalankan: node src/inject-session.js
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
    const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');
    const state = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'));

    const browser = await chromium.connectOverCDP('http://127.0.0.1:9222');
    const context = browser.contexts()[0] || await browser.newContext();

    // Convert storageState format ke CDP cookies
    if (state.cookies && state.cookies.length > 0) {
        await context.addCookies(state.cookies);
        console.log(`Injected ${state.cookies.length} cookies`);
    }

    // Verifikasi: buka Ajaib
    const page = await context.newPage();
    await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);
    const title = await page.title();
    console.log('Title:', title);

    if (title === 'Ajaib.co.id') {
        console.log('SESSION OK - halaman home DIBIARKAN TERBUKA permanen');
        console.log('(jangan tutup page ini - token auto-refresh selama page hidup)');
        // JANGAN close page - biarkan terbuka agar session awet
    } else {
        console.log('SESSION GAGAL - perlu login ulang');
        await page.close();
        process.exit(1);
    }
})().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
