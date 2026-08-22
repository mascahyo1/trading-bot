# AI Trading Bot - Indodax

Automated trading bot that analyzes the market every 5 minutes and executes trades based on AI-powered technical analysis.

## Features

- **Automated Analysis**: Runs every 5 minutes (configurable)
- **Multi-Indicator AI**: Combines RSI, MACD, EMA, Bollinger Bands, ATR, and Volume analysis
- **Risk Management**: Stop-loss, take-profit, position sizing, max open positions
- **Multi-Pair**: Trades BTC/IDR, ETH/IDR, SOL/IDR simultaneously
- **Trade History**: Logs all trades with PnL tracking
- **Win Rate Tracking**: Monitors performance over time

## Architecture

```
├── config.py        # Configuration (API keys, pairs, risk params)
├── exchange.py      # Indodax API wrapper (via CCXT)
├── llm_client.py    # LLM client (LongCat-2.0, OpenAI-compatible)
├── analyzer.py      # AI Market Analysis (technical + LLM hybrid)
├── strategy.py      # Trading strategy + Risk management
├── notifier.py      # Logging and trade notifications
├── bot.py           # Main bot loop (5-min interval)
├── dry_run.py       # Simulation mode (no real trades)
├── .env             # API credentials
└── requirements.txt
```

## How It Works

1. Every 5 minutes, the bot fetches OHLCV data for each trading pair
2. The AI analyzer computes multiple technical indicators (RSI, MACD, EMA, Bollinger, ATR, Volume)
3. The LLM (LongCat-2.0) receives the indicators and provides a second opinion
4. A hybrid scoring system combines technical (60%) + LLM (40%) signals
5. Risk manager checks position limits, stop-loss, and take-profit
6. Orders are executed on Indodax if confidence threshold is met

## Hybrid AI Signal

The bot uses a dual-analysis approach:

| Source | Weight | Method |
|--------|--------|--------|
| Technical Analysis | 60% | RSI + MACD + EMA + Bollinger + ATV + Volume |
| LLM Analysis | 40% | LongCat-2.0 reasoning on market conditions |

**Signal combination rules:**
- Both agree → boosted confidence (+10%)
- Disagree with technical dominant → keep technical signal, reduced confidence
- Disagree with LLM dominant → switch signal if combined confidence > 50%
- Both uncertain → HOLD

## Indicators Used

| Indicator | Weight | Purpose |
|-----------|--------|---------|
| RSI (14) | 20% | Overbought/Oversold detection |
| MACD | 20% | Trend momentum |
| EMA (9/21/50) | 20% | Trend direction |
| Bollinger Bands | 15% | Volatility & price extremes |
| ATR (14) | 15% | Volatility measurement |
| Volume | 10% | Signal confirmation |

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure `.env` with your Indodax API credentials:
```
INDODAX_API_KEY=your_api_key
INDODAX_API_SECRET=your_api_secret
```

3. Run the bot:
```bash
python bot.py
```

## Configuration

Edit `config.py` to customize:

- `TRADING_PAIRS` - Trading pairs to monitor
- `INTERVAL_SECONDS` - Analysis interval (default: 300s = 5min)
- `RISK_PER_TRADE` - Risk per trade as fraction of balance (default: 2%)
- `STOP_LOSS_PCT` - Stop loss percentage (default: 3%)
- `TAKE_PROFIT_PCT` - Take profit percentage (default: 6%)
- `MAX_OPEN_POSITIONS` - Maximum concurrent positions (default: 3)
- `POSITION_SIZE_USDT` - Position size in IDR (default: 500,000)

## Risk Warning

**Trading cryptocurrency involves significant risk. This bot is for educational purposes. Never trade with money you cannot afford to lose. Always test with small amounts first.**

## LLM Configuration

The bot uses LongCat-2.0 by default (OpenAI-compatible API). To use a different LLM:

1. Update `.env`:
```
llm_base_url=https://your-llm-api.com/v1
llm_api_key=your_api_key
llm_model=your-model-name
```

2. Adjust weights in `config.py`:
- `LLM_WEIGHT = 0.40` — how much the LLM opinion matters
- `TECHNICAL_WEIGHT = 0.60` — how much technical analysis matters

3. To disable LLM and use technical-only: change `use_llm=False` in `bot.py`
