/**
 * Auto-Login Ajaib FRESH - tanpa fingerprint/sesi lama
 * Fokus: tembus Turnstile + 403 Gangguan
 * Eksekusi: DISPLAY=:99 node src/auto-login-fresh.js (dari VPS via Xvfb)
 */
require('dotenv').config({ path: require('path').join(__dirname, '..', '..', '..', '.env') });
require('dotenv').config({ path: require('path').join(__dirname, '..', '..', '.env') });
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const SESSION_DIR = path.join(__dirname, '..', 'session');
const SESSION_FILE = path.join(SESSION_DIR, 'storage-state.json');
const PORTFOLIO_FILE = path.join(SESSION_DIR, 'portfolio.json');
const EMAIL = process.env.ajaib_email || process.env.AJAIB_EMAIL || '';
const NIK = process.env.ajaib_nik || process.env.AJAIB_NIK || '';
const PASSWORD = process.env.ajaib_password || process.env.AJAIB_PASSWORD || '';
const PIN = process.env.ajaib_pin || process.env.AJAIB_PIN || '';
function log(m){ console.log(`[auto-login-fresh] ${m}`); }
async function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
async function run(){
const PASSWORD = process.env.ajaib_password || process.env.AJAIB_PASSWORD || '';
  if(!fs.existsSync(SESSION_DIR)) fs.mkdirSync(SESSION_DIR,{recursive:true});
  log(`Login fresh sebagai ${EMAIL} | DISPLAY=${process.env.DISPLAY||'(none)'}`);
  const browser = await chromium.launch({
    headless: false,
    channel: 'chrome',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled','--use-gl=egl','--enable-gpu-rasterization','--ignore-gpu-blocklist','--disable-infobars','--window-size=1366,768','--disable-features=IsolateOrigins,site-per-process','--disable-dev-tools','--no-first-run','--no-default-browser-check'],
  });
  const context = await browser.newContext({
    viewport: {width:1366, height:768},
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    locale: 'id-ID', timezoneId: 'Asia/Jakarta',
    extraHTTPHeaders: {'Accept-Language':'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'},
  });
  await context.addInitScript(()=>{
    try{
      Object.defineProperty(navigator,'webdriver',{get:()=>false});
      Object.defineProperty(navigator,'plugins',{get:()=>[{name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'},{name:'Native Client'},{name:'WebKit'},{name:'Chrome'}]});
      Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en-US','en']});
      window.chrome = { runtime:{}, loadTimes:function(){}, csi:function(){} };
      const orig = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(p){ return orig.apply(this, arguments); };
    }catch(e){}
  });
  const page = await context.newPage();
  page.setDefaultTimeout(35000);
  let loginResp=null;
  page.on('response', async r=>{
    if(r.url().includes('ht2.ajaib.co.id') && r.url().includes('/login')){
      loginResp={status:r.status(), url:r.url()};
      try{ const j=await r.json(); loginResp.body=JSON.stringify(j).slice(0,800); }catch(e){ try{ loginResp.body=(await r.text()).slice(0,800);}catch(_){} }
      log(`[ht2 login] ${loginResp.status} ${loginResp.body}`);
    }
  });
  try{
    log('Buka login.ajaib.co.id/login ...');
    await page.goto('https://login.ajaib.co.id/login', {waitUntil:'domcontentloaded', timeout:35000});
    await sleep(4500);
    log('Tunggu Turnstile + mouse move ...');
    await page.mouse.move(400, 300); await sleep(300);
    await page.mouse.move(620, 410); await sleep(300);
    await page.mouse.move(520, 480); await sleep(500);
    let ready=false;
    for(let i=0;i<20;i++){
      const has = await page.evaluate(()=>{
        const inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
        for(const t of inputs) if(t.value && t.value.length>20) return true;
        const iframes = document.querySelectorAll('iframe[src*="challenges.cloudflare.com"]');
        return iframes.length>0;
      }).catch(()=>false);
      if(has){ ready=true; log(`Turnstile ready iter ${i}`); break; }
      await sleep(700);
      if(i%5==4) await page.mouse.move(300+Math.random()*400, 300+Math.random()*300);
    }
    if(!ready) log('Turnstile belum ready - lanjut');
    else await sleep(1500);
    log('Ketik email & password pelan ...');
    await page.click('input[name="email"]', {delay:80}); await sleep(300);
    await page.keyboard.type(EMAIL, {delay: 95+Math.random()*80}); await sleep(600);
    await page.click('input[name="password"]', {delay:80}); await sleep(300);
    await page.keyboard.type(PASSWORD, {delay: 95+Math.random()*80}); await sleep(1400);
    await sleep(2500);
    for(let i=0;i<10;i++){
      const has = await page.evaluate(()=>{
        const inputs = document.querySelectorAll('input[name="cf-turnstile-response"]');
        for(const t of inputs) if(t.value && t.value.length>20) return true;
        return false;
      }).catch(()=>false);
      if(has){ log(`Turnstile re-ready ${i}`); break; }
      await sleep(700);
    }
    await page.mouse.wheel(0, 80); await sleep(400);
    await page.mouse.wheel(0, -40); await sleep(400);
    log('Klik Masuk ...');
    await page.click('button[type="submit"]', {delay:100});
    await sleep(3500);
    const alertText = await page.evaluate(()=>{ const el=document.querySelector('.alert.alert-danger'); return el? el.innerText.trim().slice(0,300):''; }).catch(()=>'');
    if(alertText.includes('Gangguan')){
      log(`GAGUAN: ${alertText}`);
      const html=await page.content();
      fs.writeFileSync(path.join(SESSION_DIR,'auto-login-fresh-gangguan.html'), html);
      if(loginResp) log(`ht2 ${loginResp.status} ${loginResp.body}`);
      await browser.close(); process.exit(5);
    }
    log('Tunggu redirect pin/home atau verifikasi perangkat ...');
    let verified = false;
    try{ await page.waitForURL(/invest\.ajaib\.co\.id\/(pin|home)/,{timeout:15000}); verified = true; }
    catch(e){ log('Belum ke pin/home - cek verifikasi perangkat...'); }
    if(!verified){
      const bodyText = await page.evaluate(()=>document.body.innerText).catch(()=>'');
      if(bodyText.includes('Perangkat') || bodyText.includes('Konfirmasi') || bodyText.includes('Verifikasi') || page.url().includes('/2fa')){
        log('Halaman verifikasi perangkat terdeteksi - langsung Coba Cara Lain -> NIK (HP belum matang)...');
        try{ const h=await page.content(); require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-device-verify.html'), h); }catch(_){}
        // JANGAN klik Konfirmasi Percobaan Masuk - langsung Coba Cara Lain biar via NIK/email
        // tunggu 3 menit polling - user harus approve di HP
        log('>>> Coba Cara Lain -> verifikasi via Email (HP belum matang) <<<');
        // langsung coba Coba Cara Lain -> NIK verifikasi
        try{
          const cobaBtn = page.locator('text=Coba Cara Lain').first();
          if(await cobaBtn.count()>0){
            await cobaBtn.click({timeout:5000}); await sleep(4000);
            log('Klik Coba Cara Lain OK');
            const h=await page.content(); require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-coba-cara-lain.html'), h);
            const txt2=await page.evaluate(()=>document.body.innerText.slice(0,1500)).catch(()=>'');
            log(`Opsi setelah Coba Cara Lain: ${txt2.slice(0,800)}`);
            // cek apakah ada input NIK
            const hasNik = await page.evaluate(()=> document.body.innerText.includes('NIK')).catch(()=>false);
            if(hasNik){
              log(`Menemukan halaman NIK - isi NIK ${NIK.slice(0,4)}****`);
              if(!NIK){ log('NIK kosong di env!'); } else {
                // isi NIK
                const nikSelectors = ['input[name="nik"]','input[placeholder*="NIK"]','input[type="text"]'];
                let filled=false;
                for(const sel of nikSelectors){
                  try{
                    const loc=page.locator(sel).first();
                    if(await loc.count()>0){ await loc.click(); await sleep(300); await loc.fill(NIK); log(`Isi NIK via ${sel}`); filled=true; break; }
                  }catch(_){}
                }
                if(!filled){
                  // fallback: find by label
                  await page.evaluate((nik)=>{
                    const inputs=[...document.querySelectorAll('input')];
                    const target=inputs.find(i=> /nik/i.test(i.placeholder||'') || /nik/i.test(i.name||''));
                    if(target){ target.focus(); target.value=nik; target.dispatchEvent(new Event('input',{bubbles:true})); }
                  }, NIK);
                  log('Isi NIK via evaluate fallback');
                }
                await sleep(1000);
                // klik Konfirmasi
                try{
                  const konf = page.locator('button:has-text("Konfirmasi")').first();
                  if(await konf.count()>0){ await konf.click(); log('Klik Konfirmasi NIK'); await sleep(4000); }
                  else{
                    await page.evaluate(()=>{ const b=[...document.querySelectorAll('button')].find(x=>/Konfirmasi/i.test(x.innerText)); if(b) b.click(); });
                    log('Klik Konfirmasi via evaluate');
                    await sleep(4000);
                  }
                }catch(e){ log('Konfirmasi click gagal: '+e.message); }
                const afterNik = await page.evaluate(()=>document.body.innerText.slice(0,1500)).catch(()=>'');
                log(`Setelah Konfirmasi NIK: ${afterNik.slice(0,600)}`);
                const h2=await page.content(); require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-after-nik.html'), h2);
                // cek apakah sudah redirect ke pin/home
                const urlAfterNik=page.url();
                log(`URL setelah NIK: ${urlAfterNik}`);
                if(/invest\.ajaib\.co\.id\/(pin|home)/.test(urlAfterNik)){ verified=true; log('NIK OK langsung ke pin/home'); }
                else {
                  // mungkin masih butuh OTP email atau error
                  if(afterNik.includes('berhasil') || afterNik.includes('Berhasil')){ log('NIK berhasil - tunggu redirect...'); await sleep(3000); }
                }
              }
            }
          }
        }catch(e){ log('Coba Cara Lain/NIK gagal: '+e.message); }
        for(let i=0;i<36;i++){
          await sleep(5000);
          const url = page.url();
          if(/invest\.ajaib\.co\.id\/(pin|home)/.test(url)){ log(`Redirect setelah konfirmasi HP: ${url}`); verified=true; break; }
          const txt = await page.evaluate(()=>document.body.innerText.slice(0,400)).catch(()=>'');
          if(txt.includes('berhasil') || txt.includes('Berhasil') || txt.includes('Terverifikasi')){ log(`Status: ${txt.slice(0,200)}`); }
          log(`Poll konfirmasi HP ${i+1}/36 url=${url.slice(0,80)} txt=${txt.slice(0,80)}`);
          if(txt.includes('Coba Cara Lain') && i==3){
            log('Coba klik Coba Cara Lain untuk lihat opsi verifikasi lain...');
            try{
              await page.click('text=Coba Cara Lain', {timeout:3000});
              await sleep(3000);
              const afterCoba = await page.evaluate(()=>document.body.innerText.slice(0,600)).catch(()=>'');
              log(`Setelah Coba Cara Lain: ${afterCoba.slice(0,300)}`);
              const h2=await page.content(); require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-coba-cara-lain.html'), h2);
            }catch(e){ log('Coba Cara Lain click gagal: '+e.message); }
          }
        }
        if(!verified){
          const html=await page.content();
          require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-wait-email.html'), html);
          log('Belum redirect setelah 90s - user harus klik link di email lalu jalankan lagi auto-login');
          await browser.close(); process.exit(8);
        }
      } else {
        const body=await page.evaluate(()=>document.body.innerText.slice(0,600)).catch(()=>'');
        log(`Tidak redirect & bukan verifikasi: ${body.slice(0,200)}`);
        const html=await page.content();
        require('fs').writeFileSync(require('path').join(SESSION_DIR,'auto-login-fresh-noredirect.html'), html);
        await browser.close(); process.exit(5);
      }
    }
    let url=page.url(); log(`URL setelah login: ${url}`);
    if(url.includes('/pin')){
      if(!PIN){ log('Butuh PIN kosong'); await browser.close(); process.exit(6); }
      log('Isi PIN ...'); await sleep(2000);
      const cnt=await page.locator('input[maxlength="1"], input[inputmode="numeric"], input[type="password"], input[type="tel"]').count();
      log(`PIN inputs ${cnt}`);
      if(cnt>=6){
        const inputs=page.locator('input[maxlength="1"], input[inputmode="numeric"]');
        for(let i=0;i<6&&i<PIN.length;i++){ await inputs.nth(i).fill(PIN[i]); await sleep(120); }
      }else if(cnt>=1){
        await page.fill('input[type="password"], input[type="tel"]', PIN);
      }else{
        await page.keyboard.type(PIN,{delay:100});
      }
      await sleep(1000);
      try{ const b=page.locator('button:has-text("Konfirmasi"), button:has-text("Lanjut"), button[type="submit"]').first(); if(await b.count()>0){ await b.click(); log('Klik konfirmasi PIN'); } }catch(e){}
      await page.waitForURL('https://invest.ajaib.co.id/home',{timeout:30000});
      url=page.url(); log(`URL setelah PIN: ${url}`);
    }
    if(!url.includes('/home')){ log(`Gagal URL ${url}`); await browser.close(); process.exit(7); }
    log('Login BERHASIL fresh! Simpan session ...');
    await context.storageState({path: SESSION_FILE});
    log(`Session tersimpan ${SESSION_FILE} (${(fs.statSync(SESSION_FILE).size/1024).toFixed(1)} KB)`);
    await sleep(3000);
    try{
      // Ambil cash dulu di HOME (Buying Power hanya ada di home, tidak di tab Portofolio)
      await page.waitForTimeout(3000);
      let cashVal=0;
      try{
        cashVal = await page.evaluate(()=>{
          const txt=document.body.innerText.replace(/\xa0/g,' ');
          let m=txt.match(/Buying Power\s*Rp\s*([\d.,]+)/i) || txt.match(/Buying Power[^0-9]*Rp\s*([\d.,]+)/i);
          if(m) return parseFloat(m[1].replace(/\./g,'').replace(',','.'))||0;
          return 0;
        });
        if(cashVal>0) console.log(`[auto-login-fresh] Cash dari HOME: ${cashVal}`);
      }catch(e){}
      // baru buka tab Portofolio untuk holdings
      try{ const tab = page.locator("text=Portofolio").first(); if(await tab.count()>0){ await tab.click(); await page.waitForTimeout(4000); } }catch(e){}
      const portfolio=await page.evaluate((cashFromHome)=>{
        const data={cash: cashFromHome||0, stocks:[]};
        const txt=document.body.innerText.replace(/\xa0/g,' ');
        // cash sudah diambil dari HOME, di tab Portofolio Buying Power tidak ada - jangan timpa 0
        // Parse tabel Holdings: header "Saham Lot Harga Rata-rata Harga Saat Ini Diinvestasikan Total Return"
        const lines=txt.split('\n').map(s=>s.trim()).filter(Boolean);
        for(let i=0;i<lines.length;i++){
          if(/^[A-Z]{4}$/.test(lines[i])){
            // baris holdings sejati punya lot angka kecil (1-10) di baris berikutnya + Rp rata + Rp saat ini
            if(i+5 >= lines.length) continue;
            const lotStr = lines[i+1];
            const avgStr = lines[i+2];
            const curStr = lines[i+3];
            const invStr = lines[i+4];
            const totStr = lines[i+5];
            const lot = parseInt(lotStr.replace(/[^0-9]/g,''))||0;
            const avg = parseFloat(avgStr.replace(/Rp\s*/i,'').replace(/\./g,'').replace(',','.'))||0;
            const cur = parseFloat(curStr.replace(/Rp\s*/i,'').replace(/\./g,'').replace(',','.'))||0;
            const invested = parseFloat(invStr.replace(/Rp\s*/i,'').replace(/\./g,'').replace(',','.'))||0;
            const total = parseFloat(totStr.replace(/Rp\s*/i,'').replace(/\./g,'').replace(',','.'))||0;
            if(lot>0 && avg>0 && cur>0){
              data.stocks.push({code:lines[i], lots:lot, avg_price:avg, price:cur, invested, total});
            }
          }
        }
        return data;
      }, cashVal);
      // fallback kalau evaluate cash masih 0 tapi cashVal ada
      if(!portfolio.cash && cashVal) portfolio.cash=cashVal;
      if(!portfolio.cash){ try{ portfolio.cash=cashVal||0; }catch(e){} }
      portfolio.grandTotal = (portfolio.cash||0) + portfolio.stocks.reduce((s,x)=>s+(x.total||x.lots*100*x.price),0);
      portfolio.totalStockValue = portfolio.stocks.reduce((s,x)=>s+(x.total||0),0);
            fs.writeFileSync(PORTFOLIO_FILE, JSON.stringify(portfolio,null,2));
      log(`Portfolio fresh: cash=${portfolio.cash} stocks=${JSON.stringify(portfolio.stocks)} grandTotal=${portfolio.grandTotal}`);
    }catch(e){ log(`Scrape gagal: ${e.message}`); }
    await browser.close(); log('Selesai fresh.'); process.exit(0);
  }catch(e){
    log(`ERROR: ${e.message}`); try{ const h=await page.content(); fs.writeFileSync(path.join(SESSION_DIR,'auto-login-fresh-error.html'), h);}catch(_){}
    await browser.close(); process.exit(1);
  }
}
run();
