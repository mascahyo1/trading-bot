/**
 * Ajaib Keep-Alive & Portfolio Monitor (Cron Job - tiap 3 menit)
 *
 * Dijalankan berkala via crontab dengan environment variables:
 *   TELEGRAM_BOT_TOKEN  - Token bot Telegram untuk notifikasi
 *   TELEGRAM_CHAT_ID    - Chat ID tujuan pesan
 *
 * Contoh entry crontab:
 *   every 10 minutes: cd /path/to/trading-bot/ajaib && \
 *     TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=yyy \
 *     /usr/bin/node src/keep-alive.js >> logs/keep-alive.log 2>&1
 *
 * Anti-detection:
 *   - Interval crontab 10 menit (bukan 3 menit) untuk kurangi fingerprint
 *   - Random delay 0-60 detik sebelum scraping untuk hindari pattern detection
 *   - Retry 3x dengan delay 30 detik jika Cloudflare challenge terjadi
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
const captchaSolver = require('./captcha-solver');

// User-Agent yang sama dengan browser lokal - bypass Cloudflare
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

/** Direktori penyimpanan session browser (storage-state.json). */
const SESSION_DIR = path.join(__dirname, '..', 'session');
/** Path lengkap file session Playwright. */
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
/** Direktori file log harian. */
const LOG_DIR = path.join(__dirname, '..', 'logs');
/** Path file JSON untuk menyimpan hasil scrape portfolio (dibaca Python). */
const PORTFOLIO_FILE = path.join(SESSION_DIR, 'portfolio.json');

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
 * Strategi parsing (dieksekusi DI DALAM konteks browser via page.evaluate()):
 *   1. CASH: prioritaskan selector "Buying Power" (paling reliable).
 *      span.text-body-regular.text-white yang mengandung teks "Buying Power",
 *      lalu ambil nilai <span> di dalamnya (format "Rp 100.000").
 *      Fallback ke regex Saldo/Cash/Dana/Rp jika selector tidak ditemukan.
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

            // PRIORITAS 1: Selector "Buying Power" - paling reliable
            const bpElement = Array.from(
                document.querySelectorAll('span.text-body-regular.text-white')
            ).find(el => el.textContent.includes('Buying Power'));
            if (bpElement) {
                const nominalSpan = bpElement.querySelector('span');
                if (nominalSpan) {
                    const raw = nominalSpan.innerText.replace(/Rp\s*/i, '').replace(/\./g, '').replace(',', '.');
                    data.cash = parseFloat(raw) || 0;
                }
            }

            // FALLBACK: regex lama jika selector tidak ditemukan
            if (data.cash === 0) {
                const allText = document.body.innerText;
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
            }

            // Scan saham - allText harus di-define di scope luar fallback
            const allText = document.body.innerText;
            const lines = allText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (/^[A-Z]{4}$/.test(line)) {
                    const stockCode = line;
                    let lots = 0;
                    let price = 0;
                    for (let j = i + 1; j < Math.min(i + 10, lines.length); j++) {
                        const nextLine = lines[j];
                        const lotMatch = nextLine.match(/(\d+)\s*lot/i);
                        if (lotMatch) lots = parseInt(lotMatch[1]);
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

    // Random delay 0-60 detik untuk hindari pattern detection Cloudflare
    const randomDelay = Math.floor(Math.random() * 60);
    if (randomDelay > 0) {
        log(`Random anti-detection delay: ${randomDelay}s`);
        await new Promise(r => setTimeout(r, randomDelay * 1000));
    }

    log('Starting Ajaib bot check...');

    if (!fs.existsSync(SESSION_FILE)) {
        log('Session not found. Run: npm run login');
        await sendTelegram('<b>AJAIB BOT</b>\nSession not found! Run: npm run login');
        return;
    }

    // Retry logic: Cloudflare kadang block, coba sampai 3x dengan delay
    let success = false;
    let lastError = null;
    for (let attempt = 1; attempt <= 3; attempt++) {
        if (attempt > 1) {
            log(`Retry attempt ${attempt}/3 after 30s...`);
            await new Promise(r => setTimeout(r, 30000));
        }
        const browser = await chromium.launch({ headless: true });
        const context = await browser.newContext({
            storageState: SESSION_FILE,
            userAgent: USER_AGENT,
            viewport: { width: 1920, height: 1080 },
            locale: 'en-US',
        });
        const page = await context.newPage();

        try {
            await page.goto('https://invest.ajaib.co.id/home', {
                waitUntil: 'networkidle',
                timeout: 30000,
            });

            const url = page.url();
            const title = await page.title();
            // Cloudflare challenge: URL tetap /home tapi title berubah
            if (url.includes('login') || title.includes('Cloudflare') || title.includes('Attention Required')) {
                log(`Cloudflare challenge (attempt ${attempt})`);

                // Coba solve dengan 2Captcha
                if (captchaSolver.solver) {
                    log('Trying 2Captcha...');
                    const solved = await captchaSolver.solveCloudflare(page, 'https://invest.ajaib.co.id/home');
                    if (solved) {
                        log('Captcha solved! Checking page...');
                        // Cek apakah sudah bisa akses
                        const newTitle = await page.title();
                        if (!newTitle.includes('Cloudflare') && !newTitle.includes('Attention Required')) {
                            log('Access restored after captcha solve!');
                            // Lanjut ke scraping di bawah
                        } else {
                            log('Still blocked after solve attempt');
                            if (attempt >= 3) {
                                try {
                        const { execSync } = require('child_process');
                        log('Cloudflare/session expired - coba auto-login ...');
                        execSync('node ' + path.join(__dirname, 'auto-login.js'), { timeout: 90000, stdio: 'inherit' });
                        log('auto-login selesai, coba lagi next cycle');
                    } catch(e) { log('auto-login gagal: ' + e.message); }
                    await sendTelegram('<b>AJAIB BOT</b>\nCloudflare blocked! Auto-login dicoba, cek log.');
                            }
                            await browser.close();
                            continue;
                        }
                    } else {
                        log('2Captcha solve failed');
                        if (attempt >= 3) {
                            await sendTelegram('<b>AJAIB BOT</b>\nCloudflare blocked! Run: npm run login');
                        }
                        await browser.close();
                        continue;
                    }
                } else {
                    // Tidak ada solver, langsung retry
                    if (attempt >= 3) {
                        await sendTelegram('<b>AJAIB BOT</b>\nCloudflare blocked! Run: npm run login');
                    }
                    await browser.close();
                    continue;
                }
            }

            // Jika sampai di sini, berarti akses OK (langsung atau setelah solve)
            log('Session OK');
            // Refresh cookies supaya session tetap panjang umurnya
            await context.storageState({ path: SESSION_FILE });

            // Scrape portfolio dari text content
            const portfolio = await page.evaluate(() => {
                const data = { cash: 0, stocks: [], totalValue: 0 };
                // Replace non-breaking space dengan spasi biasa
                const allText = document.body.innerText.replace(/\xa0/g, ' ');

                // Cari Buying Power - format: "Buying Power Rp 100.000"
                const bpMatch = allText.match(/Buying Power\s*Rp\s*([\d.,]+)/i);
                if (bpMatch) {
                    data.cash = parseFloat(bpMatch[1].replace(/\./g, '').replace(',', '.'));
                }

                // Fallback: Total Investasi
                if (data.cash === 0) {
                    const totalInv = allText.match(/Total Investasi\s*Rp\s*([\d.,]+)/i);
                    if (totalInv) {
                        data.cash = parseFloat(totalInv[1].replace(/\./g, '').replace(',', '.'));
                    }
                }

                // Scan saham dari tabel
                const lines = allText.split('\n').map(l => l.trim()).filter(l => l.length > 0);
                for (let i = 0; i < lines.length; i++) {
                    if (/^[A-Z]{4}$/.test(lines[i])) {
                        let price = 0;
                        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                            const priceMatch = lines[j].match(/Rp\s*(\d{3,}(?:[.,]\d+)?)/);
                            if (priceMatch) {
                                price = parseFloat(priceMatch[1].replace(/\./g, '').replace(',', '.'));
                                break;
                            }
                        }
                        data.stocks.push({ code: lines[i], lots: 0, price });
                    }
                }

                return data;
            });

            const now = formatJakartaTime(new Date());
            const lines = [
                '<b>AJAIB PORTFOLIO</b>',
                'WIB ' + now,
                '',
                `<b>CASH: ${portfolio.cash.toLocaleString('id-ID')} IDR</b>`,
                '',
            ];

            let totalStockValue = 0;
            if (portfolio.stocks.length > 0) {
                lines.push('<b>PER SAHAM:</b>');
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
            lines.push(`<b>Total Saham: ${totalStockValue.toLocaleString('id-ID')} IDR</b>`);
            lines.push(`<b>Cash: ${portfolio.cash.toLocaleString('id-ID')} IDR</b>`);
            lines.push('');
            lines.push(`<b>GRAND TOTAL: ${grandTotal.toLocaleString('id-ID')} IDR</b>`);

            await sendTelegram(lines.join('\n'));

            // Simpan hasil scrape ke file JSON untuk dibaca Python telegram_handler
            const portfolioData = {
                timestamp: new Date().toISOString(),
                cash: portfolio.cash,
                stocks: portfolio.stocks,
                totalStockValue,
                grandTotal,
            };
            fs.writeFileSync(PORTFOLIO_FILE, JSON.stringify(portfolioData, null, 2));
            log(`Portfolio saved: cash=${portfolio.cash}, stocks=${portfolio.stocks.length}`);
            success = true;
            break;  // keluar dari loop retry karena sukses
            } catch (e) {
                lastError = e.message;
                log(`Error: ${e.message}`);
            } finally {
                await browser.close();
            }
        }  // end for loop

  if (!success && lastError) {
    await sendTelegram(`<b>AJAIB BOT</b>\nError: ${lastError.substring(0, 200)}`);
  }
}

// Handler fatal error terakhir - exit code 1 agar cron tahu ada kegagalan
main().catch(err => {
    console.error('Fatal error:', err.message);
    process.exit(1);
});
