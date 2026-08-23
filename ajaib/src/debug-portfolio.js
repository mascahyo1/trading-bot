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

  // Wait extra for dynamic content
  await page.waitForTimeout(5000);

  // Dump full HTML untuk analisis
  const html = await page.content();
  fs.writeFileSync(path.join(__dirname, '..', 'session', 'page-debug.html'), html);
  console.log('HTML saved to session/page-debug.html, length:', html.length);

  // Cari apapun yang mengandung "Buying Power" atau "Rp" di text content
  const textDebug = await page.evaluate(() => {
    const text = document.body.innerText;
    const lines = text.split('\n').filter(l => l.trim().length > 0);
    const buyingPowerIdx = lines.findIndex(l => l.includes('Buying Power'));
    const rpLines = lines.filter(l => l.includes('Rp'));

    return {
      totalLines: lines.length,
      buyingPowerLine: buyingPowerIdx >= 0 ? lines[buyingPowerIdx] : null,
      contextAroundBP: buyingPowerIdx >= 0 ? lines.slice(Math.max(0, buyingPowerIdx - 3), buyingPowerIdx + 5) : [],
      rpLineCount: rpLines.length,
      rpSample: rpLines.slice(0, 5),
      first20Lines: lines.slice(0, 20)
    };
  });

  console.log(JSON.stringify(textDebug, null, 2));
  await browser.close();
})();
