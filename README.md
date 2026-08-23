# AI Trading Bot - Indodax & Saham Indonesia

Sistem trading otomatis untuk pasar kripto (Indodax) dan saham Indonesia (Ajaib) dengan analisis teknikal AI, risk management, dan notifikasi Telegram.

## Daftar Isi

- [Arsitektur](#arsitektur)
- [Fitur Utama](#fitur-utama)
- [Persiapan](#persiapan)
- [Instalasi](#instalasi)
- [Konfigurasi](#konfigurasi)
- [Menjalankan Bot](#menjalankan-bot)
- [Telegram Commands](#telegram-commands)
- [Biaya Transaksi](#biaya-transaksi)
- [Risk Management](#risk-management)
- [Troubleshooting](#troubleshooting)

---

## Arsitektur

```
trading/
├── indodax/              # Bot kripto (Python)
│   ├── bot.py            # Main loop - analisis & eksekusi tiap 5 menit
│   ├── exchange.py       # Wrapper API Indodax (CCXT)
│   ├── analyzer.py       # Analisis teknikal (RSI, MACD, EMA, Bollinger, ATR, Volume)
│   ├── strategy.py       # Trading strategy + Risk management
│   ├── notifier.py       # Logging ke file & console
│   ├── portfolio.py      # Tracking aset & nilai portfolio
│   ├── watchdog.py       # Monitoring health tiap 5 menit
│   └── monitor.py        # AI analysis & suggestions
│
├── saham/                # Bot saham Indonesia (Python)
│   ├── bot.py            # Main loop - analisis tiap 5 menit
│   ├── exchange.py       # Wrapper yfinance (data harga saham .JK)
│   ├── ajaib_trader.py   # Playwright automation (buy/sell di Ajaib)
│   ├── analyzer.py       # Analisis teknikal
│   ├── strategy.py       # Trading strategy + Risk management
│   └── portfolio.py      # Tracking aset per saham + grand total
│
├── ajaib/                # Browser automation (Node.js)
│   ├── src/
│   │   ├── keep-alive.js # Check session + kirim portfolio tiap 3 menit
│   │   ├── login.js      # Login Ajaib via Playwright
│   │   └── explore.js    # Eksplorasi fitur Ajaib
│   └── session/          # Browser session storage
│
├── telegram_handler.py   # Unified Telegram command handler (1 listener untuk semua bot)
├── .env                  # API keys & credentials
└── venv/                 # Python virtual environment
```

### Cara Kerja

```
┌─────────────────────────────────────────────────────────────────┐
│                     TELEGRAM BOT (1 Listener)                    │
│                         telegram_handler.py                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   /status-indodax  ──► get_indodax_status()                      │
│   /portfolio-indodax ──► get_indodax_portfolio()                 │
│   /analytics-indodax ──► get_indodax_analytics()                 │
│   /status-saham    ──► get_saham_state() ──► saham_state.json    │
│   /asset-saham     ──► get_saham_portfolio() ──► saham_state.json│
│   /trades-saham    ──► saham/trade_history.json                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│     INDOODAX BOT        │     │       SAHAM BOT         │
│     (Crypto)            │     │   (Stocks .JK)          │
├─────────────────────────┤     ├─────────────────────────┤
│ • Scan 14 pairs          │     │ • Scan 20 saham         │
│ • Analisis teknikal      │     │ • Analisis teknikal     │
│ • LLM analysis (AI)      │     │ • yfinance untuk harga  │
│ • Auto buy/sell          │     │ • Ajaib web untuk       │
│ • CCXT API               │     │   eksekusi transaksi    │
│ • Interval: 5 menit      │     │ • Interval: 5 menit     │
└─────────────────────────┘     └─────────────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│     INDOODAX API        │     |     AJAIB (Browser)      │
│     (CCXT)              │     │     Playwright           │
└─────────────────────────┘     └─────────────────────────┘
```

---

## Fitur Utama

### Indodax (Crypto)
- **Multi-Pair**: Monitor 14 pair kripto (BTC, ETH, SOL, DOGE, XRP, ADA, AVAX, DOT, LINK, LTC, BCH, UNI, ATOM, FIL)
- **Technical Analysis**: RSI, MACD, EMA (9/21/50), Bollinger Bands, ATR, Volume
- **AI Analysis**: LLM (LongCat-2.0) untuk second opinion
- **Hybrid Scoring**: Technical (60%) + LLM (40%)
- **Auto Buy/Sell**: Eksekusi otomatis via API Indodax
- **Risk Management**: Stop-loss, take-profit, trailing stop, position sizing

### Saham (Stocks)
- **Multi-Stock**: Monitor 20 saham blue-chip (BBCA, BMRI, BBRI, TLKM, ASII, dll)
- **Sumber Data**: yfinance untuk harga real-time
- **Eksekusi**: Playwright automation untuk buy/sell di Ajaib
- **Technical Analysis**: RSI, MACD, EMA, Bollinger Bands, ATR, Volume
- **Auto Buy/Sell**: Via browser automation di website Ajaib
- **Portfolio Tracking**: Detail per saham + grand total

### Telegram Notifikasi
- **Unified Listener**: 1 listener untuk semua bot (tidak ada response dobel)
- **Real-time Alerts**: Notifikasi tiap ada sinyal/trade
- **Portfolio Report**: Detail aset per saham + grand total
- **Watchdog**: Monitoring bot health tiap 5 menit

---

## Persiapan

### Sistem Requirements
- Python 3.10+
- Node.js 18+
- Playwright Chromium
- Akun Indodax dengan API key
- Akun Ajaib (sekuritas online)
- Telegram Bot Token

### Buat Telegram Bot
1. Buka [@BotFather](https://t.me/BotFather) di Telegram
2. Ketik `/newbot` dan ikuti instruksi
3. Simpan **Bot Token**
4. Dapatkan **Chat ID** dengan mengirim message ke bot, lalu:
   ```
   curl https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

---

## Instalasi

### 1. Clone Repository
```bash
git clone https://github.com/mascahyo1/trading.git
cd trading
```

### 2. Setup Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# atau
venv\Scripts\activate     # Windows
```

### 3. Install Python Dependencies
```bash
pip install -r indodax/requirements.txt
pip install -r saham/requirements.txt
```

### 4. Install Node.js Dependencies (Ajaib)
```bash
cd ajaib
npm install
cd ..
```

### 5. Install Playwright Browser
```bash
playwright install chromium
```

### 6. Login Ajaib (First Time)
```bash
cd ajaib
npm run login
# Ikuti prompt untuk login ke akun Ajaib
cd ..
```

---

## Konfigurasi

### File `.env`
```env
# Indodax API Credentials
# Dapatkan di: https://indodax.com/trade_api
indodax_api_key=YOUR_API_KEY_HERE
indodax_api_secret=YOUR_API_SECRET_HERE

# LLM Configuration (LongCat-2.0)
llm_base_url=https://api.longcat.ai/openai/v1
llm_api_key=YOUR_LLM_API_KEY_HERE
llm_model=LongCat-2.0

# Telegram Notifications
Telegram_Bot_Token=YOUR_TELEGRAM_BOT_TOKEN_HERE
Telegram_Chat_ID=YOUR_TELEGRAM_CHAT_ID_HERE
```

### Konfigurasi Indodax (`indodax/config.py`)
| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `TRADING_PAIRS` | BTC/IDR, ETH/IDR, SOL/IDR | Pair utama yang ditrade |
| `ALL_PAIRS` | 14 pairs | Semua pair yang dimonitor |
| `INTERVAL_SECONDS` | 300 | Interval analisis (5 menit) |
| `RISK_PER_TRADE` | 0.02 | Risk per trade (2%) |
| `STOP_LOSS_PCT` | 0.03 | Stop loss (3%) |
| `TAKE_PROFIT_PCT` | 0.06 | Take profit (6%) |
| `MAX_OPEN_POSITIONS` | 3 | Maks posisi terbuka |
| `POSITION_SIZE_USDT` | 500000 | Ukuran posisi (IDR) |

### Konfigurasi Saham (`saham/config.py`)
| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `TRADING_STOCKS` | 10 saham | Saham utama yang ditrade |
| `ALL_STOCKS` | 20 saham | Semua saham yang dimonitor |
| `INTERVAL_SECONDS` | 300 | Interval analisis (5 menit) |
| `RISK_PER_TRADE` | 0.02 | Risk per trade (2%) |
| `STOP_LOSS_PCT` | 0.03 | Stop loss (3%) |
| `TAKE_PROFIT_PCT` | 0.08 | Take profit (8%) |
| `MAX_OPEN_POSITIONS` | 5 | Maks posisi terbuka |
| `POSITION_SIZE_IDR` | 1000000 | Ukuran posisi (IDR) |

### Biaya Transaksi Saham
| Komponen | Beli | Jual |
|----------|------|------|
| Broker Fee | 0.10% | 0.10% |
| Clearing (KPEI) | 0.02% | 0.02% |
| BEI Fee | 0.02% | 0.02% |
| PPN | - | 0.10% |
| PPh Final | - | 0.10% |
| **Total** | **0.14%** | **0.34%** |

**Round-trip cost: ~0.48%** (harga harus naik 0.48% untuk impas)

---

## Menjalankan Bot

### Indodax Bot
```bash
cd indodax
python bot.py
```

### Saham Bot
```bash
cd saham
python bot.py
```

### Ajaib Keep-Alive (via Crontab)
```bash
# Edit crontab
crontab -e

# Tambahkan untuk keep-alive tiap 3 menit
*/3 * * * * cd /path/to/trading/ajaib && \
  TELEGRAM_Bot_Token=TOKEN TELEGRAM_CHAT_ID=ID \
  /usr/bin/node src/keep-alive.js >> logs/keep-alive.log 2>&1

# Watchdog tiap 5 menit
*/5 * * * * /path/to/trading/venv/bin/python3 \
  /path/to/trading/indodax/watchdog.py >> \
  /path/to/trading/indodax/logs/watchdog.log 2>&1
```

### Stop Bot
- Tekan `q` + Enter di terminal
- Atau `Ctrl+C`

---

## Telegram Commands

### Indodax (Crypto)
| Command | Deskripsi |
|---------|-----------|
| `/status-indodax` | Status bot & balance |
| `/portfolio-indodax` | Semua aset & total value |
| `/trades-indodax` | Riwayat transaksi |
| `/analytics-indodax` | Win rate, PnL, R/R ratio |
| `/why-idle-indodax` | Kenapa bot tidak trading |
| `/analyze-improvement-indodax` | AI analysis & suggestions |
| `/stop-indodax` | Stop bot (konfirmasi) |
| `/start-indodax` | Start bot (konfirmasi) |

### Saham (Stocks)
| Command | Deskripsi |
|---------|-----------|
| `/status-saham` | Status bot & portfolio |
| `/saham` | Portfolio dari Ajaib |
| `/asset-saham` | Aset per saham + grand total |
| `/trades-saham` | Riwayat transaksi |
| `/analytics-saham` | Win rate, PnL, R/R ratio |
| `/why-idle-saham` | Kenapa bot tidak trading |
| `/fees-saham` | Breakdown biaya transaksi |

### Lainnya
| Command | Deskripsi |
|---------|-----------|
| `/help` | Tampilkan semua command |

---

## Risk Management

### Position Sizing
- **Indodax**: Maks 2% dari balance per trade, posisi max 500.000 IDR
- **Saham**: Maks 2% dari balance per trade, posisi max 1.000.000 IDR

### Stop Loss & Take Profit
- **Stop Loss**: 3% dari harga entry
- **Take Profit**: 6% (Indodax) / 8% (Saham)
- **Trailing Stop**: 5% dari harga tertinggi

### Daily Loss Limit
- Bot berhenti trading jika daily loss >= 5% dari balance

### Max Open Positions
- **Indodax**: Max 3 posisi bersamaan
- **Saham**: Max 5 posisi bersamaan

### Entry Filters
- RSI harus < 40 (oversold) untuk buy
- Win rate harus >= 40% (setelah 5+ trades)
- Risk/Reward ratio harus >= 2.0
- Daily loss limit harus belum tercapai

---

## Troubleshooting

### Bot Tidak Response di Telegram
1. Cek apakah bot jalan: `ps aux | grep bot.py`
2. Cek log: `tail -f indodax/logs/bot.log`
3. Cek Telegram token di `.env`
4. Pastikan hanya 1 proses yang polling (tidak ada duplikat)

### Error 409 Conflict
Penyebab: Dua proses polling token Telegram bersamaan.
Solusi:
```bash
# Kill semua proses bot
pkill -f 'bot.py'
# Restart hanya 1
cd indodax && python bot.py
```

### Session Ajaib Expired
```bash
cd ajaib
npm run login
```

### Bot Tidak Trading
Cek dengan command `/why-idle-indodax` atau `/why-idle-saham`.
Penyebab umum:
- Win rate < 40%
- Sudah max positions
- Balance terlalu kecil
- Daily loss limit tercapai

---

## Disclaimer

**Trading memiliki risiko tinggi. Bot ini untuk tujuan edukasi. Jangan trade dengan uang yang tidak siap hilang. Selalu test dengan jumlah kecil terlebih dahulu.**

---

## Lisensi

MIT License
