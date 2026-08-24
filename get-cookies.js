const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();
  await page.goto('https://invest.ajaib.co.id/home', { waitUntil: 'networkidle', timeout: 30000 });

  const title = await page.title();
  const url = page.url();
  console.log('Title:', title);
  console.log('URL:', url);

  if (!title.includes('Cloudflare') && !title.includes('Attention Required')) {
    const cookies = await context.cookies();
    console.log('Cookies count:', cookies.length);
    fs.writeFileSync(
      path.join(__dirname, 'ajaib', 'session', 'storage-state.json'),
      JSON.stringify({ cookies }, null, 2)
    );
    console.log('Cookies saved!');
  } else {
    console.log('Still blocked by Cloudflare');
  }

  await browser.close();
})();
