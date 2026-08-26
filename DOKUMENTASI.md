# Dokumentasi Lengkap Trading Bot

> Indodax (kripto) + Ajaib (saham) - teknikal + Telegram. Server smago (110.136.119.82) ~/trading-bot

## 1. Cara Kerja
Indodax bot 30m: scan 14 pair -> top 3 -> LLM paralel 3 -> buy/sell
Saham bot 30m: cek jam BEI 09:00-11:30/13:30-15:00 -> scrape Ajaib jika buka -> scan 20 saham -> Playwright

## 2. File Penting
- indodax/config.py : pair, timeframe 15m, risk 2%/1%, SL3% TP6% trailing5%, fee 0.3%+0.3%
- indodax/bot.py : scan_all_pairs (simpan ohlcv) -> analyze_with_llm paralel -> process_pair
- saham/config.py : 20 saham, fee Ajaib beli 0.1513% jual 0.2513% PMK131/2024, persistent profile
- saham/bot.py : market-closed skip scrape, cache TTL 1 jam, mode 100rb
- saham/ajaib_trader.py : Playwright persistent vs storage-state, _ensure_logged_in
- ajaib/src/login-via-tunnel.js : login headed via SOCKS 1080

## 3. Fee
Ajaib 0.1513/0.2513/0.4026% , Indodax 0.3+0.3=0.6% + PPh 0.21% . Semua PnL sudah net.

## 4. Operasional
systemctl status trading-indodax trading-saham
sudo systemctl restart trading-indodax
ssh -D 1080 -N smago + node src/login-via-tunnel.js untuk Ajaib

## 5. Fix 25 Agu
CPU 99% fix, double fetch reuse, LLM paralel, dust skip, fee akurat, RSI 50, persistent tunnel, log DEBUG
