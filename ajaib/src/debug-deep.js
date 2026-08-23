const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');

(async () => {
  const maxAttempts = 10;
  for (let i = 1; i <= maxAttempts; i++) {
    console.log(`\n=== Attempt ${i}/${maxAttempts} ===`);
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ storageState: SESSION_FILE });
    const page = await context.newPage();

    try {
      await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });
      const title = await page.title();

      if (title.includes('Cloudflare') || title.includes('Attention Required')) {
        console.log(`Cloudflare blocked (attempt ${i})`);
        await browser.close();
        // Random wait 30-90 detik sebelum retry
        const wait = 30 + Math.floor(Math.random() * 60);
        console.log(`Waiting ${wait}s before retry...`);
        await new Promise(r => setTimeout(r, wait * 1000));
        continue;
      }

      console.log('Page loaded! Title:', title);
      // Wait untuk dynamic content
      await page.waitForTimeout(3000);

      const html = await page.content();
      const htmlPath = path.join(__dirname, '..', 'session', 'page-success.html');
      fs.writeFileSync(htmlPath, html);
      console.log('HTML saved (' + html.length + ' bytes) to session/page-success.html');

      // Extract text content
      const textDebug = await page.evaluate(() => {
        const text = document.body.innerText;
        const lines = text.split('\n').filter(l => l.trim().length > 0);
        const bpIdx = lines.findIndex(l => l.includes('Buying Power'));
        const rpLines = lines.filter(l => l.includes('Rp'));
        return {
          totalLines: lines.length,
          bpLine: bpIdx >= 0 ? lines[bpIdx] : null,
          bpContext: bpIdx >= 0 ? lines.slice(Math.max(0, bpIdx - 3), bpIdx + 5) : [],
          rpCount: rpLines.length,
          rpSample: rpLines.slice(0, 10),
          first30Lines: lines.slice(0, 30)
        };
      });
      console.log(JSON.stringify(textDebug, null, 2));
      await browser.close();
      break; // sukses, keluar dari loop

    } catch (e) {
      console.log(`Error: ${e.message}`);
      await browser.close();
    }
  }
})();
