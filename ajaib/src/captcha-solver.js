/**
 * 2Captcha Solver untuk bypass Cloudflare challenge di Ajaib.
 *
 * Menggunakan package @2captcha/captcha-solver (Node.js).
 * Method yang tersedia:
 * - solver.cloudflareTurnstile({pageurl, sitekey}) - untuk Cloudflare Turnstile (checkbox)
 *
 * Catatan: Cloudflare JS Challenge (browser integrity check / "Attention Required")
 * TIDAK bisa di-solve dengan method standar - hanya Turnstile checkbox.
 * Untuk JS Challenge, perlu 2Captcha Browser API (service terpisah).
 *
 * @module captcha-solver
 */

const TWO_CAPTCHA_API_KEY = process.env.TWO_CAPTCHA_API_KEY || process.env.CAPTCHA_API_KEY || '';

let Solver = null;
try {
    Solver = require('@2captcha/captcha-solver');
} catch (e) {
    try {
        Solver = require('2captcha');
    } catch (e2) {
        console.warn('2captcha package not installed. Run: npm install @2captcha/captcha-solver');
    }
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
 * Untuk Cloudflare Turnstile (checkbox challenge):
 * 1. Extract sitekey dari page
 * 2. Kirim ke 2Captcha sebagai turnstile task
 * 3. Inject token kembali ke page
 *
 * NOTE: Cloudflare JS Challenge ("Attention Required") tidak bisa di-solve
 * dengan method standar. Perlu 2Captcha Browser API (service terpisah).
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
        // Extract Turnstile sitekey
        const sitekey = await getTurnstileSitekey(page);

        if (sitekey) {
            console.log(`[Captcha] Solving Turnstile, sitekey: ${sitekey.substring(0, 20)}...`);
            const result = await solver.cloudflareTurnstile({
                pageurl: pageUrl,
                sitekey: sitekey,
            });
            const token = result.data;
            console.log(`[Captcha] Turnstile solved, token: ${token.substring(0, 30)}...`);

            // Inject token ke page
            await page.evaluate((tkn) => {
                // Set response hidden input
                const input = document.querySelector('[name="cf-turnstile-response"]');
                if (input) input.value = tkn;

                // Trigger callback jika ada
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

        // Tidak ada Turnstile - kemungkinan JS Challenge
        console.log('[Captcha] No Turnstile sitekey - JS Challenge detected, cannot solve with standard API');
        return false;

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
