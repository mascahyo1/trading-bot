const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: SESSION_FILE });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });
  console.log('URL:', page.url());
  console.log('Title:', await page.title());

  // Cek semua span dengan class tertentu
  const debug = await page.evaluate(() => {
    const result = {};
    // Cari Buying Power
    const allSpans = Array.from(document.querySelectorAll('span'));
    const bpSpans = allSpans.filter(el => el.textContent.includes('Buying Power'));
    result.buyingPowerCount = bpSpans.length;
    result.buyingPowerTexts = bpSpans.slice(0, 3).map(e => ({
      tag: e.tagName,
      class: e.className,
      text: e.textContent.substring(0, 80),
      innerHTML: e.innerHTML.substring(0, 100)
    }));

    // Cari span dengan class text-body-regular
    const regularSpans = Array.from(document.querySelectorAll('span.text-body-regular'));
    result.regularSpanCount = regularSpans.length;
    result.regularSpanSample = regularSpans.slice(0, 5).map(e => ({
      class: e.className,
      text: e.textContent.substring(0, 50)
    }));

    // Cari semua yang mengandung "Rp"
    const rpElements = allSpans.filter(el => el.textContent.includes('Rp'));
    result.rpCount = rpElements.length;
    result.rpSample = rpElements.slice(0, 5).map(e => ({
      class: e.className,
      text: e.textContent.substring(0, 50)
    }));

    return result;
  });

  console.log(JSON.stringify(debug, null, 2));
  await browser.close();
})();
