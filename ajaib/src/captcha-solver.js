/**
 * 2Captcha Solver untuk bypass Cloudflare challenge di Ajaib.
 *
 * Dua tipe challenge Cloudflare:
 * 1. Turnstile (checkbox) - ada sitekey, bisa di-solve via API
 * 2. JS Challenge (browser integrity) - butuh solve dengan browser farm
 *
 * Flow:
 * 1. Detect Cloudflare challenge di page
 * 2. Extract sitekey (jika Turnstile) atau gunakan Task API
 * 3. Kirim ke 2Captcha untuk solve
 * 4. Inject token kembali ke page
 *
 * @module captcha-solver
 */

const TWO_CAPTCHA_API_KEY = process.env.TWO_CAPTCHA_API_KEY || process.env.TWO_CAPTCHA_API_KEY || '';

let Solver = null;
try {
    Solver = require('2captcha');
} catch (e) {
    console.warn('2captcha package not installed');
}

let solver = null;
if (Solver && TWO_CAPTCHA_API_KEY) {
    solver = new Solver.Solver(TWO_CAPTCHA_API_KEY);
    console.log('[Captcha] 2Captcha solver initialized');
}

/**
 * Cek apakah page sedang menampilkan Cloudflare challenge.
 *
 * @param {import('playwright').Page} page - Halaman Playwright
 * @returns {Promise<boolean>} True jika Cloudflare challenge terdeteksi
 */
async function isCloudflareChallenge(page) {
    const title = await page.title();
    if (title.includes('Attention Required') || title.includes('Cloudflare')) {
        return true;
    }
    // Cek elemen challenge
    const hasChallenge = await page.evaluate(() => {
        return !!document.querySelector('#challenge-form') ||
               !!document.querySelector('[id*="challenge"]') ||
               !!document.querySelector('.cf-browser-verification') ||
               !!document.querySelector('[name="cf-turnstile-response"]');
    });
    return hasChallenge;
}

/**
 * Extract Turnstile sitekey dari halaman challenge.
 *
 * @param {import('playwright').Page} page - Halaman challenge
 * @returns {Promise<string|null>} Sitekey atau null jika tidak ditemukan
 */
async function getTurnstileSitekey(page) {
    return await page.evaluate(() => {
        // Cari di data-sitekey attribute
        const el = document.querySelector('[data-sitekey]');
        if (el) return el.getAttribute('data-sitekey');

        // Cari di script tag
        const scripts = Array.from(document.querySelectorAll('script'));
        for (const script of scripts) {
            const text = script.textContent || '';
            const match = text.match(/sitekey["']?\s*[:=]\s*["']([^"']+)["']/);
            if (match) return match[1];
        }

        // Cari di iframe
        const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
        if (iframe) {
            const src = iframe.getAttribute('src') || '';
            const match = src.match(/[?&]sitekey=([^&]+)/);
            if (match) return decodeURIComponent(match[1]);
        }

        return null;
    });
}

/**
 * Solve Cloudflare challenge menggunakan 2Captcha.
 *
 * @param {import('playwright').Page} page - Halaman challenge
 * @param {string} pageUrl - URL halaman yang di-challenge
 * @returns {Promise<boolean>} True jika berhasil solve
 */
async function solveCloudflare(page, pageUrl) {
    if (!solver) {
        console.warn('[Captcha] Solver not initialized');
        return false;
    }

    try {
        // Coba extract Turnstile sitekey
        const sitekey = await getTurnstileSitekey(page);

        if (sitekey) {
            console.log(`[Captcha] Solving Turnstile with sitekey: ${sitekey.substring(0, 20)}...`);
            const result = await solver.turnstile({
                sitekey: sitekey,
                url: pageUrl,
            });
            const token = result.data;
            console.log(`[Captcha] Turnstile solved, token: ${token.substring(0, 30)}...`);

            // Inject token ke page
            await page.evaluate((tkn) => {
                // Set response hidden input
                const input = document.querySelector('[name="cf-turnstile-response"]');
                if (input) input.value = tkn;

                // Atau trigger callback jika ada
                if (typeof window.turnstileCallback === 'function') {
                    window.turnstileCallback(tkn);
                }

                // Submit form jika ada
                const form = document.querySelector('#challenge-form');
                if (form) form.submit();
            }, token);

            // Tunggu navigasi setelah submit
            await page.waitForLoadState('networkidle', { timeout: 30000 });
            return true;
        }

        // Fallback: gunakan Task API untuk JS challenge
        console.log('[Captcha] No Turnstile sitekey found, trying Task API...');
        const result = await solver.task({
            type: 'ChallengeTaskProxyless',
            websiteURL: pageUrl,
        });
        console.log(`[Captcha] Task solved: ${result.data ? 'OK' : 'FAIL'}`);
        return !!result.data;

    } catch (e) {
        console.error(`[Captcha] Solve failed: ${e.message}`);
        return false;
    }
}

module.exports = {
    isCloudflareChallenge,
    solveCloudflare,
    get solver() { return solver; },
};
