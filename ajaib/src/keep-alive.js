const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const LOG_DIR = path.join(__dirname, '..', 'logs');

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_Token || process.env.TELEGRAM_BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';

async function ensureDirs() {
    for (const dir of [SESSION_DIR, LOG_DIR]) {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }
}

function log(message) {
    const now = new Date();
    const jakarta = new Date(now.getTime() + (7 * 60 * 60 * 1000));
    const timestamp = jakarta.toISOString().replace('T', ' ').substring(0, 19);
    const line = `[${timestamp}] ${message}`;
    console.log(line);
    const date = jakarta.toISOString().substring(0, 10);
    const logFile = path.join(LOG_DIR, `${date}.log`);
    fs.appendFileSync(logFile, line + '\n');
}

function formatJakartaTime(date) {
    const jakarta = new Date(date.getTime() + (7 * 60 * 60 * 1000));
    return jakarta.toISOString().replace('T', ' ').substring(0, 19);
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

async function getPortfolio(page) {
    try {
        const result = await page.evaluate(() => {
            const data = { cash: 0, stocks: [], totalValue: 0 };

            const allText = document.body.innerText;
            const lines = allText.split('\n').map(l => l.trim()).filter(l => l.length > 0);

            const cashPatterns = [
                /Saldo[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Cash[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Dana[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Rp\s*([\d.,]{4,})/,
            ];
            for (const pattern of cashPatterns) {
                const match = allText.match(pattern);
                if (match) {
                    const raw = match[1].replace(/\./g, '').replace(',', '.');
                    const val = parseFloat(raw);
                    if (val > 1000) {
                        data.cash = val;
                        break;
                    }
                }
            }

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (/^[A-Z]{4}$/.test(line)) {
                    const stockCode = line;
                    let lots = 0;
                    let price = 0;
                    for (let j = i + 1; j < Math.min(i + 10, lines.length); j++) {
                        const nextLine = lines[j];
                        const lotMatch = nextLine.match(/(\d+)\s*lot/i);
                        if (lotMatch) {
                            lots = parseInt(lotMatch[1]);
                        }
                        const priceMatch = nextLine.match(/(\d{3,}(?:[.,]\d+)?)/);
                        if (priceMatch) {
                            const p = parseFloat(priceMatch[1].replace(/\./g, '').replace(',', '.'));
                            if (p > 100) price = p;
                        }
                    }
                    if (lots > 0) {
                        data.stocks.push({ code: stockCode, lots, price });
                    }
                }
            }

            return data;
        });

        return result;
    } catch (e) {
        log(`Portfolio parse error: ${e.message}`);
        return { cash: 0, stocks: [], totalValue: 0 };
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

            const portfolio = await getPortfolio(page);

            const now = formatJakartaTime(new Date());
            const lines = [
                '<b>AJAIB PORTFOLIO</b>',
                `⏰ ${now}`,
                '',
                `<b>💰 CASH: ${portfolio.cash.toLocaleString('id-ID')} IDR</b>`,
                '',
            ];

            let totalStockValue = 0;
            if (portfolio.stocks.length > 0) {
                lines.push('<b>📈 PER SAHAM:</b>');
                lines.push('');
                for (const stock of portfolio.stocks) {
                    const value = stock.lots * 100 * stock.price;
                    totalStockValue += value;
                    lines.push(`<b>${stock.code}</b>`);
                    lines.push(`   Lot: ${stock.lots} (${stock.lots * 100} lembar)`);
                    lines.push(`   Harga: ${stock.price.toLocaleString('id-ID')} IDR`);
                    lines.push(`   <b>Total: ${value.toLocaleString('id-ID')} IDR</b>`);
                    lines.push('');
                }
            }

            const grandTotal = portfolio.cash + totalStockValue;
            lines.push(`<b>💵 Total Saham: ${totalStockValue.toLocaleString('id-ID')} IDR</b>`);
            lines.push(`<b>💰 Cash: ${portfolio.cash.toLocaleString('id-ID')} IDR</b>`);
            lines.push('');
            lines.push(`<b>🏦 GRAND TOTAL: ${grandTotal.toLocaleString('id-ID')} IDR</b>`);

            await sendTelegram(lines.join('\n'));
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
