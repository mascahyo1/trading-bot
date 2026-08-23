# Ajaib Trading Bot

Automated trading bot for Ajaib stock trading using Playwright.

## Setup

1. Install dependencies:
```bash
cd ajaib
npm install
```

2. Install Playwright browsers:
```bash
npx playwright install chromium
```

3. Login manually (saves session for VPS):
```bash
npm run login
```

4. Start bot:
```bash
npm start
```

## Folder Structure

```
ajaib/
├── src/
│   ├── login.js     # Manual login, saves session
│   └── index.js     # Main bot (load session, scrape, trade)
├── session/         # Saved login session (gitignored)
├── logs/            # Daily logs (gitignored)
├── .env             # Configuration (gitignored)
├── .env.example     # Config template
├── .gitignore
├── package.json
└── README.md
```

## Notes

- Session is saved after login, no need to login again
- Use `HEADLESS=false` for local debugging
- Use `HEADLESS=true` on VPS/server
- Session expires after some days, re-run `npm run login` when needed
