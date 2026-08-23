const { chromium } = require('playwright');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');

// User-Agent yang sama dengan browser lokal user
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState: SESSION_FILE,
    userAgent: USER_AGENT,
    viewport: { width: 1920, height: 1080 },
    locale: 'en-US',
  });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });

  const title = await page.title();
  const url = page.url();
  console.log('URL:', url);
  console.log('Title:', title);

  await page.screenshot({ path: 'session/screenshot-matched-ua.png', fullPage: true });
  console.log('Screenshot saved');

  await browser.close();
})();
