const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const LOG_DIR = path.join(__dirname, '..', 'logs');

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
    if (!TELEGRAM_TOKEN || !TELEGRAM_CHAT_ID) {
        log('Telegram not configured');
        return;
    }
    const url = `https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`;
    const payload = { chat_id: TELEGRAM_CHAT_ID, text, parse_mode: 'HTML' };
    try {
        const https = require('https');
        const data = JSON.stringify(payload);
        const req = https.request(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        }, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                if (res.statusCode === 200) {
                    log('Telegram notification sent');
                } else {
                    log(`Telegram error ${res.statusCode}: ${body.substring(0, 100)}`);
                }
            });
        });
        req.on('error', (e) => log(`Telegram request error: ${e.message}`));
        req.write(data);
        req.end();
    } catch (e) {
        log(`Telegram send error: ${e.message}`);
    }
}

async function main() {
    await ensureDirs();
    log('Starting Ajaib bot check...');

    if (!fs.existsSync(SESSION_FILE)) {
        log('Session not found. Run: npm run login');
        await sendTelegram('<b>AJAIB BOT</b>\nSession not found! Run: npm run login');
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
            log('SESSION EXPIRED');
            await sendTelegram('<b>AJAIB BOT</b>\nSession expired! Run: npm run login');
        } else {
            log('Session OK');
            await context.storageState({ path: SESSION_FILE });
            const now = new Date().toISOString().replace('T', ' ').substring(0, 19);
            await sendTelegram(`<b>AJAIB BOT ALIVE</b>\nSession OK\n${now}`);
        }
    } catch (e) {
        log(`Error: ${e.message}`);
        await sendTelegram(`<b>AJAIB BOT</b>\nError: ${e.message.substring(0, 200)}`);
    } finally {
        await browser.close();
    }
}

main().catch(err => {
    console.error('Fatal error:', err.message);
    process.exit(1);
});
