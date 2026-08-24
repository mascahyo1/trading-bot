const { chromium } = require('playwright');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: SESSION_FILE, userAgent: USER_AGENT });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });

  const title = await page.title();
  const url = page.url();
  console.log('Title:', title);
  console.log('URL:', url);

  await page.waitForTimeout(3000);

  const text = await page.evaluate(() => document.body.innerText.substring(0, 3000));
  console.log('\n=== PAGE TEXT ===\n', text);

  const debug = await page.evaluate(() => {
    const r = {};
    r.hasBuyingPower = Array.from(document.querySelectorAll('*')).some(el => el.textContent && el.textContent.toLowerCase().includes('buying power'));
    r.hasRp = Array.from(document.querySelectorAll('span')).filter(el => el.textContent && el.textContent.includes('Rp')).length;
    r.allRpTexts = Array.from(document.querySelectorAll('span')).filter(el => el.textContent && el.textContent.includes('Rp')).map(e => e.textContent.substring(0, 50)).slice(0, 20);
    r.bodyClasses = document.body.className;
    r.mainContent = document.querySelector('main, #app, #root') ? document.querySelector('main, #app, #root').className : 'NOT FOUND';
    return r;
  });
  console.log('\n=== DEBUG ===\n', JSON.stringify(debug, null, 2));

  await browser.close();
})();
