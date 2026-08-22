#!/bin/bash
# Quick start script untuk VPS
# Jalankan: bash start.sh

cd "$(dirname "$0")"

# Check .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env not found!"
    echo "Run: cp .env.example .env && nano .env"
    exit 1
fi

# Activate venv if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

echo "Starting Trading Bot..."
echo "Press 'q' to stop"
echo ""

python3 bot.py
