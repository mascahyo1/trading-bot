# Dokumentasi Lengkap Trading Bot — Update 31 Agustus 2026 (Mode Aman)

> **Server smago** `100.136.119.175` (lama `110.136.119.82`) — `Tailscale smago 100.65.197.44` `~/trading-bot` (repo lokal `C:\laragon\www\trading`)
> **Status 31-08-2026 08:46 WIB**: Indodax `active` Balance `60.413 IDR` `HEARTBEAT` normal setelah fix IP whitelist. Saham `active` heartbeat `CYCLE #471` menunggu `09:00`.

---

## Daftar Isi
1. Ringkasan
2. Arsitektur & Cara Kerja
3. Konfigurasi (Indodax + Saham)
4. File Penting
5. Fee & Risk Management
6. Operasional (systemd, ssh, logs, watchdog, Telegram)
7. Perubahan 31 Agustus 2026 — Mode Aman
8. Troubleshooting
9. Roadmap

---

## 1. Ringkasan

Bot hybrid teknikal + AI LLM untuk **Indodax (kripto 24/7)** dan **Ajaib (saham BEI jam bursa)** dengan notifikasi Telegram unified (1 listener).

- **Indodax**: scan 14 pair → top 3 by confidence → LLM paralel 3 → eksekusi buy/sell via CCXT Trade API v2. Interval **1800s (30 menit)**. Position sizing **Mode Aman 15-20k/trade**.
- **Saham**: cek `is_market_open()` presisi `09:00-11:30` & `13:30-14:59` (Senin-Jumat) → scrape Ajaib via Playwright persistent profile → scan 20 saham yfinance → eksekusi via browser. Interval **300s (5 menit)** heartbeat, trading hanya saat bursa buka, cache TTL 1 jam, keep-alive jitter 3-4.5 jam.

---

## 2. Arsitektur & Cara Kerja

```
Telegram (1 listener telegram_handler.py:868)
  ├─ /status-indodax, /portfolio-indodax, /trades-indodax, /analytics-indodax, /why-idle-indodax
  └─ /status-saham, /saham, /asset-saham, /trades-saham, /analytics-saham, /why-saham, /fees-saham, /help

Indodax Bot (indodax/bot.py:599) — 30m cycle:
  1) check_ip_change() → log IP BERUBAH + Telegram jika IP VPS ganti (110.136.119.82 → 175)
  2) health_check() Balance IDR
  3) sync_positions_from_exchange() load 4 dust (ATOM/AVAX/BTC/LTC) dari saldo real
  4) scan_all_pairs() fetch_ohlcv 14 pair (limit 100, 15m) simpan ohlcv reuse → analyze_technical() → top 3 (>55%)
  5) analyze_with_llm() paralel ThreadPoolExecutor 3 (reuse ohlcv, skip LLM jika conf<0.6) → _combine_signals() 60% teknikal 40% LLM + boost 10% jika sepakat
  6) process_pair() per kandidat: evaluate() → BUY (amount via calculate_position_size Mode Aman) / partial_sell tp1 1% / close tp2 3.5% / trailing 1.5% / smart_sell hanya jika profit >0.5% / DCA -3%/-6% / SL -3% / TP 6% legacy
  7) rebalance jika balance <15k cari score sell
  8) notify_summary() + _send_indodax_no_buy_explanation() jika tidak beli + unrealized (net fee 0.3%)

Saham Bot (saham/bot.py:590):
  if not is_market_open() → keep-alive jitter 3-4.5h (GET /home, auto-login via node ajaib/src/auto-login.js DISPLAY=:99 jika expired, fallback cash dari portfolio.json)
  else → sync yfinance → scan_all_stocks() → top buy/sell → process_stock()

Ajaib Trader (saham/ajaib_trader.py:231):
  get_portfolio_async() launch_persistent_context (1366x768, proxy SOCKS 1080 jika ada) → _ensure_logged_in → goto /home → klik Portofolio → wait Buying Power → page.evaluate innerText → regex Buying Power Rp + 4 huruf kode saham + lot/avg/cur → fallback cash portfolio.json → retry 3x

Indodax Exchange (indodax/exchange.py:125): HMAC SHA256 Private API v2 `https://api.indodax.com`, X-APIKEY + Sign, recvWindow 5000, retry 3x exponential 2s/4s, CCXT untuk ohlcv/ticker public (200 OK), private 403 jika IP whitelist salah

Watchdog (indodax/watchdog.py:160): cron */5 → check_bot_health() pgrep + mtime bot.log >2400s (40m = 30m+buffer) → get_portfolio() → BOT DOWN / BOT ALIVE. Jika portfolio None → pesan baru 31-08: timestamp + IP + err 403 + solusi whitelist (fix notif 08:20)
```

---

## 3. Konfigurasi

### Indodax `indodax/config.py`
| Parameter | Nilai | Keterangan |
|-----------|-------|------------|
| `TRADING_PAIRS` | BTC/IDR, ETH/IDR, SOL/IDR | Pair utama prioritas |
| `ALL_PAIRS` | 14 pair (BTC ETH SOL DOGE XRP ADA AVAX DOT LINK LTC BCH UNI ATOM FIL) | Universe scan |
| `INTERVAL_SECONDS` | `1800` **= 30 menit** (bukan 5 menit) | Fix 31-08 comment sebelumnya salah `5 menit` |
| `CANDLESTICK_TIMEFRAME` | `15m` limit 100 | |
| `LLM_TOP_PAIRS` | 3 | |
| `RISK_PRIMARY_PCT` 0.02 / `SECONDARY` 0.01 / `RISK_PER_TRADE` 0.02 | Legacy, real sizing Mode Aman 15-20k |
| `STOP_LOSS_PCT` 0.03 | SL -3% dari harga market (fix dari fee) |
| `TAKE_PROFIT_PCT` 0.06 | Legacy 6%, real `tp1 1% tp2 3.5%` di `strategy.py:95-96` |
| `TRAILING_STOP_PCT` 0.05 | Legacy 5%, real `1.5%` di `strategy.py:90` |
| `MAX_DAILY_LOSS_PCT` 0.05 | Circuit -5% |
| `MAX_OPEN_POSITIONS` 3 | |
| `POSITION_SIZE_USDT` 500000 | Legacy cap, real Mode Aman `15-20k` di `strategy.py:384` |
| `MIN_ORDER_IDR` 10000 | |
| `LLM_WEIGHT` 0.40 `TECHNICAL_WEIGHT` 0.60 | |
| `TRADE_HISTORY_FILE` | `trade_history.json` (18 trades, win 16.67%, PnL -834) |

### Saham `saham/config.py`
| Parameter | Nilai |
|-----------|-------|
| `ALL_STOCKS` | 20 saham (BBCA BMRI BBRI TLKM ASII GOTO BUMI BRMS dll) |
| `INTERVAL_SECONDS` | `300` = 5 menit heartbeat, trading hanya saat `is_market_open()` |
| `is_market_open()` | `09:00-11:30` & `13:30-14:59` presisi menit `m=hour*60+minute` (fix 31-08: sebelumnya `hour==11` masih True 11:31-11:59, `hour==13` 13:00-13:29 salah True) weekday 0-4 |
| `POSITION_SIZE_IDR` | 1.000.000 (tapi risk 2% + fallback 95% — perlu sync, lihat Error E07) |
| `MAX_OPEN_POSITIONS` | 5 |
| `STOP_LOSS` 3% `TAKE_PROFIT` 8% `TRAILING` 5% | |
| Fee | `PMK131/2024`: beli `0.1513%` (broker 0.10 + clearing 0.02 + BEI 0.02 + levy 0.0113) jual `0.2513%` total `0.4026%` round-trip |

### .env (tidak di-commit)
```
indodax_api_key, indodax_api_secret
llm_base_url=https://api.longcat.ai/openai/v1  llm_api_key  llm_model=LongCat-2.0
Telegram_Bot_Token  Telegram_Chat_ID
Ajaib email/pass/PIN/NIK (untuk auto-login)
```

---

## 4. File Penting

- `indodax/config.py:183` interval, risk, IP check; `strategy.py:54` Position, `260` RiskManager, `631` TradingStrategy; `bot.py:599` ProductionBot, `400` health_check, `560` _keyboard_listener fix 100% CPU; `exchange.py:125` _v2_request HMAC; `analyzer.py:324` hybrid 60/40, ATR filter 0.4%; `watchdog.py:92` get_portfolio fix 31-08 + `160` check_bot_health; `telegram_handler.py:492` get_saham_portfolio fix `_fb_stocks` 31-08; `notifier.py` DailyFileHandler WIB
- `saham/config.py:95` fee; `bot.py:102` is_market_open, `590` run_cycle keep-alive, `95` cache TTL; `ajaib_trader.py:231` get_portfolio_async regex Buying Power; `exchange.py` yfinance
- `ajaib/src/auto-login.js` `login-via-tunnel.js` SOCKS 1080 `Xvfb :99`
- Service `indodax/trading-indodax.service:9` `WorkingDirectory ~/trading-bot/indodax` `ExecStart venv/bin/python bot.py` `StandardOutput append logs/bot.log`; `saham/trading-saham.service` + `cron */5 watchdog.py >> logs/watchdog.log`

---

## 5. Fee & Risk Management

**Indodax**: `0.3% buy + 0.3% sell = 0.6%` net (sudah dipotong di `strategy.py:83` `entry*1.003` dan `450` `sell*0.997`). PnL -834 sudah net. **Ajaib**: `0.1513% beli + 0.2513% jual = 0.4026%` (README lama 0.14/0.34 salah). **Mode Aman 31-08**: `calculate_position_size()` 60k→20k, 45k→15k, 30k→10k, <10k skip (bisa 3 posisi). `tp1 1%` (net 0.4% setelah fee) jual 50%, `tp2 3.5%` jual habis, `trailing 1.5%` dari puncak (dulu 5% terlalu lebar), `smart_sell` hanya jika profit >0.5% (fix jual rugi kecil -0.2% terus), `SL -3%` tetap, `DCA -3%/-6%` 50%/25%, `daily loss -5%`, `win rate gate 25% if n<20 else 40%` (n=18 win 16.67% → block buy).

**Fix finansial 31-08**: `get_unrealized_pnl()` sekarang `current*0.997-entry` (dulu tanpa fee over-estimate 0.3%); `get_total_portfolio_value()` `balance + open_value` (dulu double-count `balance+unreal+open_value`).

---

## 6. Operasional

```bash
# SSH
ssh smago                    # Tailscale 100.65.197.44, fallback smago-cf cloudflared
ssh smago "curl -s https://ifconfig.me"  # IP sekarang 110.136.119.175
cat ~/trading-bot/indodax/known_ip.txt ~/trading-bot/indodax/ip_changes.json

# Systemd
systemctl status trading-indodax trading-saham
sudo systemctl restart trading-indodax   # setelah update IP whitelist indodax.com/trade_api atau deploy
journalctl -u trading-indodax -n 50 --no-pager  # journal kosong karena log ke file
tail -n 100 ~/trading-bot/indodax/logs/2026-08-31.log   # real log harian WIB
tail -n 100 ~/trading-bot/indodax/logs/bot.log          # stdout service
tail -n 50 ~/trading-bot/indodax/logs/watchdog.log
tail -n 50 ~/trading-bot/saham/logs/2026-08-31.log
tail -n 50 ~/trading-bot/saham/logs/bot.log
ps aux | grep bot.py
free -h; uptime

# Ajaib manual
ssh -D 1080 -N smago &
PROXY_SERVER=socks5://127.0.0.1:1080 node ajaib/src/login-via-tunnel.js  # headed
# atau di VPS: DISPLAY=:99 node ajaib/src/auto-login.js (Xvfb :99)

# Telegram
# 1 listener telegram_handler.py:868 (polling 30s, anti 409). Commands: /status-indodax, /portfolio-indodax, /trades-indodax, /analytics-indodax, /why-idle-indodax, /status-saham, /saham, /asset-saham, /trades-saham, /analytics-saham, /why-saham, /fees-saham, /help
# Watchdog cron: */5 * * * * venv/bin/python ~/trading-bot/indodax/watchdog.py >> logs/watchdog.log
```

**IP whitelist Indodax**: jika `IP BERUBAH Old 110.136.119.82 New 110.136.119.175` → update di `indodax.com/trade_api` → `curl ifconfig.me` cek → `get_balance()` harus `canTrade True` bukan `403 Forbidden`. Bot interval 30m jadi next cycle 30m setelah update baru sukses (atau restart).

---

## 7. Perubahan 31 Agustus 2026 — Mode Aman

**Masalah 2 minggu**: 18 trades win 3 loss 15 win 16.67% PnL -834 (avg win +980 avg loss -252, expectancy -47/trade). SOL 0/5 -807 DOGE 0/3 -501, hold 1.6h, loss hold 1.7h. Penyebab: position sizing `balance*0.95 = 57k` all-in habis, TP 3%/6% kejauhan + smart_sell jual rugi -0.2% terus (RSI>70), LLM `6640 hold 33 buy` tidak membantu, ATR sideways, fee 0.6%.

**Fix**:

- `indodax/watchdog.py:92-205` notif `Gagal cek portfolio08:20` → pesan baru timestamp + IP + err 403 + solusi whitelist (deploy 08:25, test HEARTBEAT 08:30:07 OK)
- `indodax/strategy.py:384` Mode Aman sizing 15-20k (60k→20k, 45k→15k, 30k→10k) bisa 3 posisi, tidak all-in
- `strategy.py:90` trailing 5%→1.5%, `95-96` tp1 3%→1% (net 0.4% setelah fee) tp2 6%→3.5% (lebih capai), `794-809` smart_sell hanya jika profit >0.5% (jaga tidak jual rugi kecil)
- `indodax/config.py:183` comment 5m→30m, `204` legacy TP/Trailing docs
- `indodax/strategy.py:611` unreal net `*0.997`, `621` portfolio `balance+open_value` (dulu double)
- `saham/bot.py:102` is_market_open presisi menit `9*60<=m<=11*60+30` etc.
- `telegram_handler.py:507` fix `for s in stocks` → `_fb_stocks` + indent else
- `indodax/bot.py:617` log Position Size → `Mode Aman 15-20k`

**Verif 08:46**: `Balance 60.413` `Scanning 14 Found 2 buy 3 sell` `Position sizing Mode Aman: 60.413 -> 20.000` (next buy akan 20k). Open 4 dust menunggu TP1 1% / SL 3%.

---

## 8. Troubleshooting

- **403 Forbidden + Balance 0**: IP whitelist belum update → `ssh smago "venv/bin/python /tmp/bal_test2.py"` cek `canTrade` → update indodax API → `sudo systemctl restart trading-indodax`
- **Notif 08:20 Gagal cek portfolio**: watchdog 5m fetch private API gagal → sekarang sudah jelas (IP + err + solusi), cek `tail logs/2026-08-31.log`
- **Saham not trading**: `is_market_open()` false di luar 09:00-11:30/13:30-14:59 atau weekend → `tail saham/logs/2026-08-31.log` `Next cycle 300s` + `Keep-alive jitter 3-4.5h` + `auto-login` jika `Session expired`
- **Telegram 409**: 2 listener → `pkill -f bot.py` restart 1, `clear_pending_updates()` auto
- **Playwright Cloudflare**: `Cloudflare challenge detected` → jangan save storage-state, tunggu retry, `proxy SOCKS 1080` via smago
- **Dust <10k skip**: posisi kecil tidak dijual (hindari 400) → rebalance akan cari kandidat score tinggi
- **Win rate <25% block buy**: `Skip buy: win rate 16.67% < 25% (n=18)` → tunggu win naik atau reset `trade_history.json`

---

## 9. Roadmap
- Sinkronkan `saham/strategy.py` fallback `balance*0.95` (E07) dan persist `Position.to_dict()` lengkap
- Watchdog `BOT_LOG` dual path (daily vs bot.log) + `flock` Telegram
- Fee table README → `0.1513/0.2513`
- Hapus `os.chdir` di `config.py:15`, pakai `EnvironmentFile` di service
- Backtest 3 hari Mode Aman, evaluasi LLM prompt (kurangi konservatif)

> Disclaimer: Trading berisiko. Bot edukasi, jangan pakai uang tidak siap hilang.
