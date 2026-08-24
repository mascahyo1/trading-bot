const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');

async function ensureSessionDir() {
    if (!fs.existsSync(SESSION_DIR)) {
        fs.mkdirSync(SESSION_DIR, { recursive: true });
    }
}

async function login() {
    await ensureSessionDir();

    console.log('========================================');
    console.log('  AJAIB TRADING BOT - LOGIN');
    console.log('========================================');
    console.log('');
    console.log('Browser akan terbuka.');
    console.log('Login manual di browser (email/password/2FA/PIN).');
    console.log('Setelah berhasil, session akan tersimpan otomatis.');
    console.log('');

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized'],
    });

    const context = await browser.newContext({
        viewport: { width: 1280, height: 800 },
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    });

    const page = await context.newPage();

    console.log('Navigating to Ajaib login page...');
    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'networkidle',
        timeout: 30000,
    });

    console.log('Waiting for login to complete...');
    console.log('(Login di browser, script akan deteksi otomatis)');
    console.log('');

    // Tunggu sampai URL berubah DAN bukan halaman login/cloudflare
    let loginSuccess = false;
    let attempts = 0;
    const maxAttempts = 120; // 2 menit max (120 x 1 detik)

    while (!loginSuccess && attempts < maxAttempts) {
        await page.waitForTimeout(1000);
        attempts++;

        const url = page.url();
        const title = await page.title();

        // Cek apakah masih di login page atau cloudflare
        if (url.includes('login') || title.includes('Cloudflare') || title.includes('Attention Required')) {
            process.stdout.write(`\rMenunggu login... (${attempts}s)`);
            continue;
        }

        // Cek apakah sudah di home page Ajaib (title harus "Ajaib.co.id")
        if (title === 'Ajaib.co.id' || url.includes('/home')) {
            // Verifikasi dengan cek content page
            const hasContent = await page.evaluate(() => {
                const text = document.body.innerText;
                return text.includes('Buying Power') || text.includes('Portofolio') || text.includes('Beranda');
            });

            if (hasContent) {
                loginSuccess = true;
                console.log('\nLogin berhasil! Terdeteksi di halaman home Ajaib.');
            }
        }
    }

    if (!loginSuccess) {
        console.log('\nLogin gagal atau timeout (2 menit).');
        await browser.close();
        process.exit(1);
    }

    // Simpan session
    await context.storageState({ path: SESSION_FILE });
    console.log('Session tersimpan di:', SESSION_FILE);

    // Verifikasi session dengan test request
    console.log('Verifikasi session...');
    await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });
    const verifyTitle = await page.title();
    if (verifyTitle.includes('Cloudflare') || verifyTitle.includes('Attention Required')) {
        console.log('WARNING: Session mungkin tidak valid (Cloudflare detected)');
    } else {
        console.log('Session valid! Title:', verifyTitle);
    }

    await page.waitForTimeout(2000);
    await browser.close();
    console.log('Selesai. Jalankan "npm start" untuk mulai trading.');
}

login().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
