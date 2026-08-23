const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const cron = require('node-cron');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const LOG_DIR = path.join(__dirname, '..', 'logs');

async function ensureDirs() {
    for (const dir of [SESSION_DIR, LOG_DIR]) {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }
}

function log(message) {
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const line = `[${timestamp}] ${message}`;
    console.log(line);
    const date = new Date().toISOString().substring(0, 10);
    const logFile = path.join(LOG_DIR, `${date}.log`);
    fs.appendFileSync(logFile, line + '\n');
}

async function checkSession() {
    if (!fs.existsSync(SESSION_FILE)) {
        console.log('Session not found. Please run: npm run login');
        process.exit(1);
    }
}

async function loadSession() {
    await checkSession();

    const browser = await chromium.launch({
        headless: process.env.HEADLESS === 'true',
    });

    const context = await browser.newContext({
        storageState: SESSION_FILE,
    });

    const page = await context.newPage();

    await page.goto('https://invest.ajaib.co.id/home', {
        waitUntil: 'networkidle',
        timeout: 60000,
    });

    const url = page.url();
    if (url.includes('login')) {
        console.log('Session expired. Please run: npm run login');
        await browser.close();
        process.exit(1);
    }

    await context.storageState({ path: SESSION_FILE });
    log('Session refreshed');

    return { browser, context, page };
}

async function getPortfolio(page) {
    log('Fetching portfolio data...');

    try {
        await page.goto('https://invest.ajaib.co.id/home', {
            waitUntil: 'networkidle',
            timeout: 30000,
        });

        const portfolio = await page.evaluate(() => {
            const result = {
                balances: [],
                positions: [],
                totalValue: 0,
            };

            const balanceElements = document.querySelectorAll('[class*="balance"], [class*="saldo"], [class*="asset"]');
            balanceElements.forEach(el => {
                const text = el.textContent?.trim();
                if (text && text.length < 100) {
                    result.balances.push(text);
                }
            });

            const positionElements = document.querySelectorAll('[class*="stock"], [class*="saham"], [class*="portfolio-item"]');
            positionElements.forEach(el => {
                const text = el.textContent?.trim();
                if (text && text.length < 200) {
                    result.positions.push(text);
                }
            });

            return result;
        });

        log(`Found ${portfolio.balances.length} balance entries`);
        log(`Found ${portfolio.positions.length} position entries`);

        return portfolio;
    } catch (e) {
        log(`Portfolio fetch error: ${e.message}`);
        return null;
    }
}

async function run() {
    await ensureDirs();
    log('Starting Ajaib Trading Bot...');

    const { browser, context, page } = await loadSession();
    log('Session loaded successfully!');

    const portfolio = await getPortfolio(page);
    if (portfolio) {
        console.log('\n=== PORTFOLIO DATA ===');
        console.log(JSON.stringify(portfolio, null, 2));
    }

    await browser.close();
    log('Done.');
}

run().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
