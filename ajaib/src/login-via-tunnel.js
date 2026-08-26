/**
 * Login Ajaib via SSH SOCKS Tunnel (IP VPS) — Playwright Headed Mode.
 *
 * Modul ini membuka browser Chromium secara visual (headed) di mesin lokal,
 * namun seluruh traffic di-route melalui SSH SOCKS tunnel (localhost:1080)
 * yang terhubung ke VPS. Dengan begitu, website Ajaib melihat IP VPS
 * (110.136.119.82) bukan IP lokal — menghindari deteksi lokasi asing.
 *
 * Alur lengkap:
 *   1. Buka Chromium headed (terlihat di layar) dengan proxy socks5://127.0.0.1:1080.
 *   2. Verifikasi IP via ifconfig.me — pastikan IP VPS yang terdeteksi.
 *   3. Navigasi ke halaman login Ajaib (login.ajaib.co.id/login).
 *   4. Tunggu user input email/password secara manual hingga redirect ke /pin atau /home.
 *   5. Jika redirect ke /pin, tunggu user input PIN hingga masuk /home.
 *   6. Verifikasi URL sudah di /home — jika belum, abort.
 *   7. Simpan session ke storage-state.json (Playwright storageState).
 *   8. Kirim file session ke VPS via scp (smago:~/trading-bot/ajaib/session/).
 *   9. Inject session ke persistent browser di VPS via SSH.
 *
 * Prasyarat:
 *   - SSH tunnel aktif: ssh -D 1080 -N smago (SOCKS proxy di 127.0.0.1:1080)
 *   - SSH alias `smago` terkonfigurasi di ~/.ssh/config
 *   - Persistent browser script tersedia di VPS (persistent-browser.sh)
 *
 * Penggunaan:
 *   node src/login-via-tunnel.js
 *
 * @module login-via-tunnel
 */
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

/** Path file session Playwright (storage-state.json) — dibaca keep-alive & ajaib_trader. */
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');
const PROXY = 'socks5://127.0.0.1:1080';

(async () => {
    console.log('==============================================');
    console.log('  LOGIN AJAIB VIA TUNNEL (IP VPS)');
    console.log('==============================================');
    console.log('Browser akan terbuka. Login manual:');
    console.log('  1. Email/password');
    console.log('  2. PIN');
    console.log('  3. Sampai masuk halaman home');
    console.log('');

    // Fingerprint asli user (biar ht2.ajaib.co.id tidak 403), fallback ke default
    let fp = null;
    try {
        const fpPath = path.join(__dirname, '..', 'fingerprint.json');
        if (fs.existsSync(fpPath)) fp = JSON.parse(fs.readFileSync(fpPath, 'utf-8'));
    } catch (e) {}
    const fpUA = fp && fp.userAgent ? fp.userAgent : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

    const browser = await chromium.launch({
        headless: false,
        args: ['--start-maximized', '--disable-blink-features=AutomationControlled'],
        proxy: { server: PROXY },
    });

    const context = await browser.newContext({
        viewport: fp && fp.screen ? { width: fp.screen.width, height: fp.screen.height } : { width: 1280, height: 800 },
        userAgent: fpUA,
        locale: fp && fp.language ? fp.language : 'en-US',
        extraHTTPHeaders: {
            'Accept-Language': fp && fp.languages ? fp.languages.join(',') : 'en-US,en;q=0.9,id;q=0.8',
        },
    });
    if (fp) {
        await context.addInitScript((f) => {
            try {
                Object.defineProperty(navigator, 'platform', { get: () => f.platform });
                Object.defineProperty(navigator, 'vendor', { get: () => f.vendor });
                Object.defineProperty(navigator, 'language', { get: () => f.language });
                Object.defineProperty(navigator, 'languages', { get: () => f.languages });
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => f.hardwareConcurrency });
                Object.defineProperty(navigator, 'deviceMemory', { get: () => f.deviceMemory });
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                const origGetParam = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(pname) {
                    if (pname === 37445) return f.webgl.vendor;
                    if (pname === 37446) return f.webgl.renderer;
                    return origGetParam.apply(this, arguments);
                };
                if (window.WebGL2RenderingContext) {
                    const orig2 = WebGL2RenderingContext.prototype.getParameter;
                    WebGL2RenderingContext.prototype.getParameter = function(pname) {
                        if (pname === 37445) return f.webgl.vendor;
                        if (pname === 37446) return f.webgl.renderer;
                        return orig2.apply(this, arguments);
                    };
                }
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            } catch (e) {}
        }, fp);
    }

    const page = await context.newPage();

    // Verifikasi dulu: IP yang dilihat Ajaib harus IP VPS
    try {
        await page.goto('https://ifconfig.me', { timeout: 20000 });
        const ip = (await page.textContent('body')).trim();
        console.log(`IP terdeteksi oleh website: ${ip}`);
        if (!ip.includes('110.136')) {
            console.log('PERINGATAN: IP bukan IP VPS!');
        }
    } catch (e) {
        console.log('Skip cek IP:', e.message);
    }

    // Step 1: Halaman login
    console.log('\nMembuka halaman login...');
    await page.goto('https://login.ajaib.co.id/login', {
        waitUntil: 'domcontentloaded',
        timeout: 60000,
    });

    // Tunggu user login sampai redirect ke PIN atau home (TANPA TIMEOUT)
    await page.waitForURL(/invest\.ajaib\.co\.id\/(pin|home)/, { timeout: 0 });
    let url = page.url();
    console.log('Redirect ke:', url);

    // Step 2: PIN
    if (url.includes('/pin')) {
        console.log('Input PIN...');
        await page.waitForURL('https://invest.ajaib.co.id/home', { timeout: 0 });
    }

    // Step 3: Verifikasi home
    url = page.url();
    console.log('Final URL:', url);
    if (!url.includes('/home')) {
        console.log('GAGAL: tidak sampai home.');
        await browser.close();
        process.exit(1);
    }
    console.log('LOGIN BERHASIL!');

    // Simpan session
    fs.mkdirSync(path.dirname(SESSION_FILE), { recursive: true });
    await context.storageState({ path: SESSION_FILE });
    console.log('Session tersimpan:', SESSION_FILE);
    await browser.close();

    // Kirim session ke VPS + inject ke persistent browser
    console.log('\nMengirim session ke VPS...');
    execSync(
        `scp "${SESSION_FILE}" smago:~/trading-bot/ajaib/session/storage-state.json`,
        { stdio: 'inherit' }
    );
    console.log('Session terkirim. Inject ke persistent browser...');
    execSync(
        `ssh smago "cd ~/trading-bot/ajaib && ./persistent-browser.sh > /dev/null 2>&1; node src/inject-session.js"`,
        { stdio: 'inherit' }
    );

    console.log('\nSELESAI. Session hidup di persistent browser 24/7.');
})().catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
