const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const LOG_FILE = path.join(__dirname, '..', 'logs', 'exploration.log');

function log(msg) {
    const ts = new Date().toISOString();
    const line = `[${ts}] ${msg}`;
    console.log(line);
    fs.appendFileSync(LOG_FILE, line + '\n');
}

async function explore() {
    if (!fs.existsSync(path.dirname(LOG_FILE))) {
        fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    }

    log('=== AJAIB EXPLORATION START ===');

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
    });

    context.on('page', page => {
        log(`New page opened: ${page.url()}`);
    });

    const page = await context.newPage();

    page.on('request', req => {
        log(`REQUEST: ${req.method()} ${req.url()}`);
    });

    page.on('response', async res => {
        log(`RESPONSE: ${res.status()} ${res.url()}`);
    });

    log('Navigating to https://login.ajaib.co.id/login');

    try {
        await page.goto('https://login.ajaib.co.id/login', {
            waitUntil: 'networkidle',
            timeout: 30000,
        });
        log('Page loaded successfully');
    } catch (e) {
        log(`Navigation error: ${e.message}`);
    }

    // Log page structure
    const title = await page.title();
    log(`Page title: ${title}`);

    const url = page.url();
    log(`Current URL: ${url}`);

    // Find all inputs
    const inputs = await page.locator('input').evaluateAll(els =>
        els.map(e => ({
            type: e.type,
            name: e.name,
            placeholder: e.placeholder,
            id: e.id,
            className: e.className,
        }))
    );
    log(`Found ${inputs.length} input elements: ${JSON.stringify(inputs)}`);

    // Find all buttons
    const buttons = await page.locator('button').evaluateAll(els =>
        els.map(e => ({
            text: e.textContent?.trim(),
            type: e.type,
            className: e.className,
        }))
    );
    log(`Found ${buttons.length} button elements: ${JSON.stringify(buttons)}`);

    // Find all links
    const links = await page.locator('a').evaluateAll(els =>
        els.map(e => ({
            text: e.textContent?.trim(),
            href: e.href,
        }))
    );
    log(`Found ${links.length} link elements`);

    // Wait for user to interact
    log('Waiting for user interaction...');

    page.on('close', () => {
        log('Browser closed by user');
        log('=== AJAIB EXPLORATION END ===');
    });

    await page.waitForTimeout(120000);

    log('Exploration timeout reached');
    await browser.close();
    log('=== AJAIB EXPLORATION END ===');
}

explore().catch(err => {
    console.error('Error:', err.message);
    fs.appendFileSync(LOG_FILE, `[ERROR] ${err.message}\n`);
    process.exit(1);
});
