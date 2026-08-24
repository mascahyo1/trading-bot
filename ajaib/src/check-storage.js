const { chromium } = require('playwright');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: SESSION_FILE });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });

  const title = await page.title();
  console.log('Title:', title);

  // Check localStorage
  const localStorage = await page.evaluate(() => {
    const items = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      items[key] = localStorage.getItem(key);
    }
    return items;
  });
  console.log('\n=== localStorage ===');
  Object.entries(localStorage).forEach(([k, v]) => console.log(`  ${k}: ${v.substring(0, 80)}`));

  // Check sessionStorage
  const sessionStorage = await page.evaluate(() => {
    const items = {};
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      items[key] = sessionStorage.getItem(key);
    }
    return items;
  });
  console.log('\n=== sessionStorage ===');
  Object.entries(sessionStorage).forEach(([k, v]) => console.log(`  ${k}: ${v.substring(0, 80)}`));

  await browser.close();
})();
