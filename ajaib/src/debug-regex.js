const { chromium } = require('playwright');
const path = require('path');
const SESSION_FILE = path.join(__dirname, '..', 'session', 'storage-state.json');
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ storageState: SESSION_FILE, userAgent: USER_AGENT });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });

  await page.waitForTimeout(3000);

  const result = await page.evaluate(() => {
    const allText = document.body.innerText;
    const bpIdx = allText.indexOf('Buying Power');
    const bpContext = allText.substring(bpIdx, bpIdx + 50);
    // Show char codes for debugging
    const charCodes = [];
    for (let i = 0; i < bpContext.length; i++) {
      charCodes.push(bpContext.charCodeAt(i));
    }

    // Try different regex patterns
    const patterns = [
      /Buying Power\s*Rp\s*([\d.,]+)/i,
      /Buying Power[^a-zA-Z]*Rp\s*([\d.,]+)/i,
      /Buying Power.*?([\d.,]+)/,
      /Power\s*Rp\s*([\d.,]+)/i,
    ];

    const matches = [];
    for (const p of patterns) {
      const m = allText.match(p);
      matches.push({ pattern: p.toString(), match: m ? m[0] : null, group1: m ? m[1] : null });
    }

    return { bpContext, charCodes, matches };
  });

  console.log('Context around Buying Power:', JSON.stringify(result.bpContext));
  console.log('Char codes:', JSON.stringify(result.charCodes));
  console.log('\nRegex matches:');
  result.matches.forEach(m => console.log(`  ${m.pattern} => ${m.match} (group1: ${m.group1})`));

  await browser.close();
})();
