/**
 * Screener Ajaib SOLID — scrape https://invest.ajaib.co.id/home/stocks 1x sehari 08:40
 * Filter solid: Harga 50-2000, Vol >1M, Change -10%..+20%, Notasi Khusus bersih (skip X)
 * Output: top 10 kode solid untuk merge ke ALL_STOCKS (opsional, untuk referensi)
 *
 * Jalankan manual: node screener-ajaib.js
 * Atau via bot saham: akan dipanggil otomatis pre-market 08:40 jika DISPLAY=:99 tersedia
 * Requires: Playwright persistent profile (sudah login) + storage-state.json
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SOLID = {
  priceMin: 50,
  priceMax: 2000,
  volMin: 1_000_000,
  changeMin: -10,
  changeMax: 20,
};

async function main() {
  const sessionDir = path.join(__dirname, '..', 'ajaib', 'session');
  const storageState = path.join(sessionDir, 'storage-state.json');
  const persistentProfile = path.join(__dirname, '..', 'ajaib', 'persistent-profile');

  let context;
  if (fs.existsSync(persistentProfile) && fs.readdirSync(persistentProfile).length > 0) {
    context = await chromium.launchPersistentContext(persistentProfile, {
      headless: false,
      args: ['--no-sandbox'],
      viewport: { width: 1366, height: 768 },
    });
  } else if (fs.existsSync(storageState)) {
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    context = await browser.newContext({ storageState });
  } else {
    console.error('Tidak ada session: login dulu via node ajaib/src/auto-login.js');
    process.exit(1);
  }

  const page = context.pages()[0] || await context.newPage();
  console.log('[screener] Buka https://invest.ajaib.co.id/home/stocks ...');
  await page.goto('https://invest.ajaib.co.id/home/stocks', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(5000);

  // Coba klik header Harga untuk sort asc (opsional, data sudah bisa di-parse tanpa sort)
  try {
    const hargaHeader = page.locator('th:has-text("Harga")').first();
    if (await hargaHeader.count()) {
      await hargaHeader.click();
      await page.waitForTimeout(2000);
    }
  } catch {}

  // Tunggu tabel
  await page.waitForSelector('table', { timeout: 15000 }).catch(()=>{});
  await page.waitForTimeout(3000);

  // Ambil baris: Kode | Notasi Khusus | Harga | Change | Vol
  const rows = await page.evaluate(() => {
    const tables = document.querySelectorAll('table');
    let best = null, maxRows = 0;
    tables.forEach(t => {
      const r = t.querySelectorAll('tbody tr').length;
      if (r > maxRows) { maxRows = r; best = t; }
    });
    if (!best) return [];
    const out = [];
    best.querySelectorAll('tbody tr').forEach(tr => {
      const tds = tr.querySelectorAll('td');
      if (tds.length < 5) return;
      const kode = tds[0]?.innerText?.trim() || '';
      const notasi = tds[1]?.innerText?.trim() || '';
      const hargaRaw = tds[3]?.innerText?.trim() || tds[4]?.innerText?.trim() || '';
      const changeRaw = tds[5]?.innerText?.trim() || '';
      const volRaw = tds[tds.length-1]?.innerText?.trim() || '';
      out.push({ kode, notasi, hargaRaw, changeRaw, volRaw });
    });
    return out;
  });

  console.log(`[screener] Dapat ${rows.length} baris`);
  const solid = [];
  for (const r of rows) {
    const harga = parseInt(r.hargaRaw.replace(/[^0-9]/g, '') || '0', 10);
    // Vol bisa "1,59 M" atau "0" — parse
    let vol = 0;
    const v = r.volRaw.replace(/,/g, '.').trim();
    if (v.includes('M')) vol = parseFloat(v.replace(/[^0-9.]/g, '')) * 1_000_000;
    else if (v.includes('K')) vol = parseFloat(v.replace(/[^0-9.]/g, '')) * 1_000;
    else vol = parseInt(v.replace(/[^0-9]/g, '') || '0', 10);

    let change = 0;
    const c = r.changeRaw.replace('%','').replace(',','.').trim();
    change = parseFloat(c) || 0;

    const isNotasiBersih = !/[X]/.test(r.notasi); // skip X (suspend), biarkan kosong atau L/M/Y/B
    const ok = harga >= SOLID.priceMin && harga <= SOLID.priceMax
      && vol >= SOLID.volMin
      && change >= SOLID.changeMin && change <= SOLID.changeMax
      && isNotasiBersih
      && r.kode.length >= 3;

    if (ok) solid.push({ kode: r.kode, harga, vol, change, notasi: r.notasi });
  }

  solid.sort((a,b) => b.vol - a.vol);
  const top10 = solid.slice(0, 10);
  console.log(`[screener] SOLID ${solid.length}/${rows.length} lolos, top 10 by Vol:`);
  top10.forEach(s => console.log(`  ${s.kode} ${s.harga} Vol ${(s.vol/1e6).toFixed(2)}M ${s.change}% Notasi:${s.notasi||'-'}`));

  const outPath = path.join(__dirname, 'screener-result.json');
  fs.writeFileSync(outPath, JSON.stringify({ timestamp: new Date().toISOString(), total: rows.length, solid: solid.length, top10 }, null, 2));
  console.log(`[screener] Simpan ${outPath}`);

  await context.close();
}

main().catch(e => { console.error(e); process.exit(1); });
