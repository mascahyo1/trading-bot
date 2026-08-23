const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const cron = require('node-cron');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const LOG_DIR = path.join(__dirname, '..', 'logs');
const KEEP_ALIVE_INTERVAL = 3;
const ALIVE_INTERVAL = 5;

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';

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

async function sendTelegram(text) {
    if (!TELEGRAM_TOKEN || !TELEGRAM_CHAT_ID) return;
    const url = `https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`;
    const payload = { chat_id: TELEGRAM_CHAT_ID, text, parse_mode: 'HTML' };
    try {
        const https = require('https');
        const data = JSON.stringify(payload);
        const req = https.request(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        }, (res) => res.on('data', () => {}));
        req.write(data);
        req.end();
    } catch (e) {
        log(`Telegram send error: ${e.message}`);
    }
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
            await sendTelegram('<b>AJAIB BOT</b>\nSession expired! Run: npm run login');
        } else {
            log('Session keep-alive OK');
            await context.storageState({ path: SESSION_FILE });
        }
    } catch (e) {
        log(`Keep-alive error: ${e.message}`);
        await sendTelegram(`<b>AJAIB BOT</b>\nKeep-alive error: ${e.message.substring(0, 200)}`);
    } finally {
        await browser.close();
    }
}

async function sendAliveNotification() {
    const now = new Date().toISOString().replace('T', ' ').substring(0, 19);
    const msg = `<b>AJAIB BOT ALIVE</b>\nSession OK\n${now}`;
    log('Sending alive notification');
    await sendTelegram(msg);
}

async function startKeepAlive() {
    await ensureDirs();
    log(`Starting session keep-alive (every ${KEEP_ALIVE_INTERVAL} minutes)`);

    await keepAlive();

    cron.schedule(`*/${KEEP_ALIVE_INTERVAL} * * * *`, async () => {
        await keepAlive();
    });

    cron.schedule(`*/${ALIVE_INTERVAL} * * * *`, async () => {
        await sendAliveNotification();
    });
}

startKeepAlive().catch(err => {
    console.error('Keep-alive error:', err.message);
    process.exit(1);
});
