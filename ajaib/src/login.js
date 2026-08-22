const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

async function login() {
    if (!fs.existsSync(SESSION_DIR)) {
        fs.mkdirSync(SESSION_DIR, { recursive: true });
    }

    console.log('Opening Ajaib login page...');

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

    console.log('Browser opened. Please login manually.');
    console.log('Waiting for login to complete...');

    await page.waitForTimeout(60000);

    await context.storageState({ path: SESSION_FILE });
    console.log('Session saved to:', SESSION_FILE);

    await browser.close();
    console.log('Done.');
}

login().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
