const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');

(async () => {
  for (let i = 1; i <= 20; i++) {
    console.log(`\n=== Attempt ${i}/20 ===`);
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ storageState: SESSION_FILE });
    const page = await context.newPage();

    try {
      await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });
      const title = await page.title();

      if (title.includes('Cloudflare') || title.includes('Attention Required')) {
        console.log(`Cloudflare blocked (attempt ${i})`);
        await browser.close();
        await new Promise(r => setTimeout(r, 60000)); // wait 60s
        continue;
      }

      console.log('SUCCESS! Page loaded. Title:', title);
      await page.waitForTimeout(3000); // wait for dynamic content

      // Dump HTML
      const html = await page.content();
      fs.writeFileSync(path.join(__dirname, '..', 'session', 'page-success.html'), html);
      console.log(`HTML saved (${html.length} bytes)`);

      // Dump text content
      const text = await page.evaluate(() => document.body.innerText);
      fs.writeFileSync(path.join(__dirname, '..', 'session', 'page-text.txt'), text);
      console.log(`Text saved (${text.length} chars)`);

      // Check for key elements
      const debug = await page.evaluate(() => {
        const all = document.querySelectorAll('*');
        const withText = [];
        for (const el of all) {
          const t = el.textContent || '';
          if (t.includes('Buying Power') || t.includes('Rp') || t.includes('BBCA') || t.includes('saham')) {
            withText.push({
              tag: el.tagName,
              class: el.className,
              text: t.substring(0, 100)
            });
          }
          if (withText.length > 20) break;
        }
        return withText;
      });
      console.log('Key elements:', JSON.stringify(debug, null, 2));

      await browser.close();
      break;
    } catch (e) {
      console.log(`Error: ${e.message}`);
      await browser.close();
    }
  }
})();
