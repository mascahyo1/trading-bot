# AI Trading Bot - Saham Indonesia

Automated trading bot untuk saham Indonesia yang menganalisis pasar setiap 5 menit dan mengeksekusi transaksi otomatis di Ajaib.

## Features

- **Auto Buy/Sell**: Eksekusi transaksi otomatis via Playwright di website Ajaib
- **Technical Analysis**: RSI, MACD, EMA, Bollinger Bands, ATR, Volume
- **Risk Management**: Stop-loss, take-profit, trailing stop, position sizing
- **Telegram Notifications**: Notifikasi trade, aset per saham, grand total
- **Multi-Stock**: Monitor 20 saham blue-chip Indonesia secara bersamaan
- **Portfolio Tracking**: Detail aset per saham + grand total

## Arsitektur

```
saham/
├── config.py           # Konfigurasi (saham, risk, API keys)
├── exchange.py         # yfinance wrapper (data harga saham .JK)
├── ajaib_trader.py     # Playwright automation (buy/sell di Ajaib)
├── analyzer.py         # Technical analysis (RSI, MACD, EMA, BB, ATR)
├── strategy.py         # Trading strategy + Risk management
├── notifier.py         # Logging ke file & console
├── telegram_notifier.py    # Telegram notifications
├── telegram_commands.py    # Telegram bot commands
├── portfolio.py        # Per-stock asset tracking + grand total
├── bot.py              # Main bot loop
├── requirements.txt
└── .env.example
```

## Cara Kerja

1. Setiap 5 menit, bot fetch data OHLCV dari yfinance untuk setiap saham
2. Analyzer hitung indikator teknikal (RSI, MACD, EMA, Bollinger, ATR, Volume)
3. Strategy evaluasi sinyal buy/sell berdasarkan confidence threshold
4. Risk manager cek position limits, stop-loss, take-profit
5. Order dieksekusi via Playwright di website Ajaib
6. Notifikasi dikirim ke Telegram

## Indikator yang Dipakai

| Indikator | Weight | Fungsi |
|-----------|--------|--------|
| RSI (14) | 20% | Overbought/Oversold |
| MACD | 20% | Trend momentum |
| EMA (9/21/50) | 20% | Trend direction |
| Bollinger Bands | 15% | Volatilitas |
| ATR (14) | 15% | Volatilitas |
| Volume | 10% | Konfirmasi sinyal |

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Pastikan sudah login Ajaib via Node.js:
```bash
cd ../ajaib
npm install
npm run login
```

3. Configure `.env` with Telegram credentials:
```
Telegram_Bot_Token=your_bot_token
Telegram_Chat_ID=your_chat_id
```

4. Run the bot:
```bash
python bot.py
```

## Telegram Commands

| Command | Fungsi |
|---------|--------|
| `/status-saham` | Status bot & portfolio |
| `/saham` | Portfolio dari Ajaib |
| `/asset-saham` | Aset per saham + grand total |
| `/trades-saham` | Riwayat transaksi |
| `/analytics-saham` | Win rate, PnL, R/R ratio |
| `/why-idle-saham` | Kenapa bot tidak trading |
| `/analyze-improvement-saham` | AI analysis & suggestions |
| `/fees-saham` | Transaction fees breakdown |
| `/stop-saham` | Stop bot (dengan konfirmasi) |
| `/start-saham` | Start bot (dengan konfirmasi) |
| `/help-saham` | List commands |

### Aliases (Shortcut)

| Alias | Command Asli |
|-------|-------------|
| `/status` | `/status-saham` |
| `/portfolio` | `/saham` |
| `/asset` / `/aset` | `/asset-saham` |
| `/trades` | `/trades-saham` |
| `/analytics` / `/stats` | `/analytics-saham` |
| `/why` / `/why-idle` | `/why-idle-saham` |
| `/improve` / `/improvement` | `/analyze-improvement-saham` |
| `/fees` / `/biaya` | `/fees-saham` |
| `/stop` | `/stop-saham` |
| `/start` | `/start-saham` |

## Biaya Transaksi (Otomatis Dihitung)

Bot ini **SUDAH** memperhitungkan biaya transaksi dalam setiap keputusan beli/jual:

| Biaya | Beli | Jual |
|-------|------|------|
| Broker Fee | 0.10% | 0.10% |
| Clearing Fee (KPEI) | 0.02% | 0.02% |
| BEI Fee | 0.02% | 0.02% |
| PPN (VAT) | - | 0.10% |
| PPh Final | - | 0.10% |
| **Total** | **0.14%** | **0.34%** |

**Round-trip cost (beli + jual): ~0.48%**
Artinya harga saham harus naik minimal **0.48%** agar impas (break-even).

Semua PnL yang ditampilkan adalah **NET** (sudah dipotong biaya).

## Risk Warning

**Trading saham memiliki risiko tinggi. Bot ini untuk tujuan edukasi. Jangan trade dengan uang yang tidak siap hilang. Selalu test dengan jumlah kecil terlebih dahulu.**

## Saham yang Dimonitor

Default: BBCA, BMRI, BBRI, TLKM, ASII, UNVR, INDF, KLBF, ICBP, ANTM, INCO, PGAS, PTBA, SMGR, ADHI, INTP, EXCL, ISAT, JSMR, CPIN

Edit `config.py` untuk mengubah daftar saham.
