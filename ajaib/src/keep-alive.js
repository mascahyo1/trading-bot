/**
 * Ajaib Keep-Alive & Portfolio Monitor (Cron Job - tiap 3 menit)
 *
 * Dijalankan berkala via crontab dengan environment variables:
 *   TELEGRAM_BOT_TOKEN  - Token bot Telegram untuk notifikasi
 *   TELEGRAM_CHAT_ID    - Chat ID tujuan pesan
 *
 * Contoh entry crontab:
 *   *\/3 * * * * cd /path/to/trading/ajaib && \
 *     TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \
 *     /usr/bin/node src/keep-alive.js >> logs/keep-alive.log 2>&1
 *
 * Fungsi utama:
 *   1. SESSION CHECK   - Verifikasi session login Ajaib masih valid.
 *                        Jika expired, kirim alert Telegram agar user
 *                        login ulang manual via `npm run login`.
 *   2. PORTFOLIO SCAN  - Scrape saldo kas + kepemilikan saham dari
 *                        halaman home Ajaib, lalu kirim laporan lengkap
 *                        (per saham + grand total) ke Telegram.
 *   3. SESSION REFRESH - Simpan storage state terbaru supaya cookies
 *                        selalu fresh dan tidak mudah expired.
 *
 * Catatan parsing:
 *   - Scraping berbasis regex terhadap innerText halaman, sehingga
 *     rapuh jika Ajaib mengubah layout website.
 *   - Kode saham dikenali sebagai baris berisi tepat 4 huruf kapital
 *     (mis. "BBCA"), diikuti pencarian pola "N lot" + harga pada
 *     maksimal 10 baris setelahnya.
 *
 * Timezone: Semua timestamp menggunakan Asia/Jakarta (WIB / UTC+7).
 *
 * @module keep-alive
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

/** Direktori penyimpanan session browser (storage-state.json). */
const SESSION_DIR = path.join(__dirname, '..', 'session');
/** Path lengkap file session Playwright. */
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
/** Direktori file log harian. */
const LOG_DIR = path.join(__dirname, '..', 'logs');

/**
 * Token bot Telegram dari environment variable.
 * Mendukung dua penamaan: TELEGRAM_BOT_Token dan TELEGRAM_BOT_TOKEN.
 */
const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_Token || process.env.TELEGRAM_BOT_TOKEN || '';
/** Chat ID penerima notifikasi Telegram dari environment variable. */
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';

/**
 * Pastikan direktori session dan logs sudah ada;
 * buat secara rekursif jika belum ada di filesystem.
 *
 * @returns {Promise<void>}
 */
async function ensureDirs() {
    for (const dir of [SESSION_DIR, LOG_DIR]) {
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
    }
}

/**
 * Tulis log dengan timestamp WIB ke console DAN file log harian
 * (logs/YYYY-MM-DD.log). Rotasi file otomatis mengikuti tanggal WIB.
 *
 * @param {string} message - Pesan yang akan dicatat.
 * @returns {void}
 */
function log(message) {
    const now = new Date();
    const jakarta = new Date(now.getTime() + (7 * 60 * 60 * 1000)); // UTC+7
    const timestamp = jakarta.toISOString().replace('T', ' ').substring(0, 19);
    const line = `[${timestamp}] ${message}`;
    console.log(line);
    const date = jakarta.toISOString().substring(0, 10);
    const logFile = path.join(LOG_DIR, `${date}.log`);
    fs.appendFileSync(logFile, line + '\n');
}

/**
 * Format objek Date menjadi string "YYYY-MM-DD HH:mm:ss" dalam waktu Jakarta (WIB).
 *
 * @param {Date} date - Objek tanggal yang akan diformat.
 * @returns {string} Timestamp terformat dalam zona waktu Asia/Jakarta.
 */
function formatJakartaTime(date) {
    const jakarta = new Date(date.getTime() + (7 * 60 * 60 * 1000)); // UTC+7
    return jakarta.toISOString().replace('T', ' ').substring(0, 19);
}

/**
 * Kirim pesan teks HTML ke Telegram via Bot API sendMessage (fire-and-forget).
 *
 * Pesan dikirim asinkron; error tidak melempar exception, hanya dicatat
 * ke log agar proses utama tetap berjalan normal.
 *
 * @param {string} text - Isi pesan HTML (limit Telegram ~4096 karakter).
 * @returns {Promise<void>}
 */
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

/**
 * Scrape portfolio (saldo kas + daftar saham) dari DOM halaman home Ajaib.
 *
 * Parsing dilakukan DI DALAM konteks browser via page.evaluate():
 *   1. CASH: Coba beberapa pola regex berurutan (Saldo/Cash/Dana/Rp).
 *      Angka valid jika > 1000 agar tidak salah ambil harga satuan.
 *      Format Indonesia: titik sebagai pemisah ribuan (1.500.000).
 *   2. STOCKS: Baris dengan tepat 4 huruf kapital dianggap kode saham,
 *      lalu scan maksimal 10 baris berikutnya untuk mencari jumlah lot
 *      (pola "N lot") dan harga (> 100).
 *
 * @param {import('playwright').Page} page - Halaman Playwright yang sedang
 *        membuka invest.ajaib.co.id/home.
 * @returns {Promise<{cash: number, stocks: Array<{code: string, lots: number, price: number}>, totalValue: number}>}
 *          Data portofolio hasil scraping. Jika gagal parsing, dikembalikan
 *          struktur kosong (cash=0, stocks=[]) agar proses tetap lanjut.
 */
async function getPortfolio(page) {
    try {
        const result = await page.evaluate(() => {
            const data = { cash: 0, stocks: [], totalValue: 0 };

            const allText = document.body.innerText;
            const lines = allText.split('\n').map(l => l.trim()).filter(l => l.length > 0);

            // Pola regex saldo kas - dicoba berurutan, pertama match & valid menang
            const cashPatterns = [
                /Saldo[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Cash[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Dana[^:]*:?\s*Rp?\s*([\d.,]+)/i,
                /Rp\s*([\d.,]{4,})/,
            ];
            for (const pattern of cashPatterns) {
                const match = allText.match(pattern);
                if (match) {
                    // Konversi format Indonesia: hapus titik ribuan, koma jadi desimal
                    const raw = match[1].replace(/\./g, '').replace(',', '.');
                    const val = parseFloat(raw);
                    if (val > 1000) {
                        data.cash = val;
                        break;
                    }
                }
            }

            // Scan baris demi baris mencari kode saham (4 huruf kapital)
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (/^[A-Z]{4}$/.test(line)) {
                    const stockCode = line;
                    let lots = 0;
                    let price = 0;
                    // Cari lot & harga pada maksimal 10 baris setelah kode saham
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

/**
 * Entry point utama keep-alive check.
 *
 * Alur eksekusi:
 *   1. Pastikan direktori session & logs ada.
 *   2. Validasi file session ada; jika tidak, alert Telegram + stop.
 *   3. Launch Chromium headless dengan storage state session.
 *   4. Buka invest.ajaib.co.id/home, cek redirect ke halaman login.
 *      - Redirect login => SESSION EXPIRED, kirim alert Telegram.
 *      - Session OK     => refresh storage state, scrape portfolio,
 *                          format laporan (per saham + grand total),
 *                          kirim ke Telegram.
 *   5. Selalu tutup browser di blok finally (cleanup terjamin).
 *
 * Catatan format angka: toLocaleString('id-ID') menghasilkan pemisah
 * ribuan titik sesuai konvensi Indonesia (mis. 1.500.000).
 *
 * @returns {Promise<void>}
 */
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
            // Refresh cookies supaya session tetap panjang umurnya
            await context.storageState({ path: SESSION_FILE });

            // Scrape dan format laporan portfolio lengkap
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
                    // Nilai posisi = lots x 100 lembar x harga per lembar
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

// Handler fatal error terakhir - exit code 1 agar cron tahu ada kegagalan
main().catch(err => {
    console.error('Fatal error:', err.message);
    process.exit(1);
});
