const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const cron = require('node-cron');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const KEEP_ALIVE_INTERVAL = 3;

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

async function keepAlive() {
    if (!fs.existsSync(SESSION_FILE)) {
        log('Session not found. Run: npm run login');
        return;
    }

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ storageState: SESSION_FILE });
    const page = await context.newPage();

    try {
        await page.goto('https://invest.ajaib.co.id/home', {
            waitUntil: 'networkidle',
            timeout: 30000,
        });

        const url = page.url();
        if (url.includes('login')) {
            log('SESSION EXPIRED - need to re-login');
        } else {
            log('Session keep-alive OK');
            await context.storageState({ path: SESSION_FILE });
        }
    } catch (e) {
        log(`Keep-alive error: ${e.message}`);
    } finally {
        await browser.close();
    }
}

async function startKeepAlive() {
    await ensureDirs();
    log(`Starting session keep-alive (every ${KEEP_ALIVE_INTERVAL} minutes)`);

    await keepAlive();

    cron.schedule(`*/${KEEP_ALIVE_INTERVAL} * * * *`, async () => {
        await keepAlive();
    });
}

startKeepAlive().catch(err => {
    console.error('Keep-alive error:', err.message);
    process.exit(1);
});
