const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, '..', 'logs', 'explore-features.log');

function log(msg) {
    const ts = new Date().toISOString();
    const line = `[${ts}] ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n');
}

async function explore() {
    const browser = await chromium.launch({ headless: false });
    const context = await browser.newContext({
        storageState: path.join(__dirname, '..', 'session', 'storage-state.json'),
    });

    const page = await context.newPage();

    page.on('request', req => {
        if (req.url().includes('/api/')) {
            log(`REQ: ${req.method()} ${req.url()}`);
        }
    });

    page.on('response', async res => {
        if (res.url().includes('/api/')) {
            log(`RES: ${res.status()} ${res.url()}`);
        }
    });

    await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle' });

    await page.waitForTimeout(5000);

    log('=== EXPLORING FEATURES ===');
    log('Waiting for user interactions...');

    await page.waitForTimeout(180000);

    await browser.close();
    log('=== END ===');
}

explore().catch(err => {
    log(`ERROR: ${err.message}`);
    process.exit(1);
});
