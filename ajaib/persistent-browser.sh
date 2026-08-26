#!/bin/bash
# Persistent Chromium dengan remote debugging port 9222
pkill -f 'remote-debugging-port=9222' 2>/dev/null
sleep 1
mkdir -p /home/cahyo/trading-bot/ajaib/persistent-profile
nohup /home/cahyo/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome \
  --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
  --user-agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36' \
  --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
  --user-data-dir=/home/cahyo/trading-bot/ajaib/persistent-profile \
  > /home/cahyo/trading-bot/ajaib/logs/persistent-browser.log 2>&1 &
echo $! > /home/cahyo/trading-bot/ajaib/persistent-browser.pid
sleep 4
curl -s http://127.0.0.1:9222/json/version | head -3
