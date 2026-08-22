const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

async function main() {
    if (!fs.existsSync(SESSION_FILE)) {
        console.log('Session not found. Please run: npm run login');
        process.exit(1);
    }

    console.log('Loading session...');

    const browser = await chromium.launch({
        headless: false,
    });

    const context = await browser.newContext({
        storageState: SESSION_FILE,
    });

    const page = await context.newPage();

    await page.goto('https://invest.ajaib.co.id/home', {
        waitUntil: 'networkidle',
        timeout: 30000,
    });

    const url = page.url();
    console.log('Current URL:', url);

    if (url.includes('login')) {
        console.log('Session expired. Please run: npm run login');
        await browser.close();
        process.exit(1);
    }

    console.log('Logged in successfully!');
    console.log('Bot is running... Press Ctrl+C to stop.');

    await page.waitForTimeout(60000);

    await browser.close();
}

main().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
