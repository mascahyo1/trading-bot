# Ajaib Trading Bot

Automated trading bot for Ajaib using Playwright.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Install Playwright browsers:
```bash
npx playwright install chromium
```

3. Login manually (saves session):
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
│   └── index.js     # Main bot (coming soon)
├── session/         # Saved login session (gitignored)
├── logs/            # Bot logs (gitignored)
├── .env             # Configuration (gitignored)
├── .env.example     # Config template
└── package.json
```

## Notes

- Session is saved after login, no need to login again
- Use `headless: false` for local debugging
- Use `headless: true` on VPS/server
