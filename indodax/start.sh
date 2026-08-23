#!/bin/bash
# ==============================================================================
# Script Quick Start Bot Indodax untuk VPS / Linux
# ==============================================================================
# Menjalankan bot secara interaktif di terminal dengan virtualenv aktif.
#
# Penggunaan:
#   bash start.sh
# ==============================================================================

cd "$(dirname "$0")"

# 1. Pengecekan ketersediaan file .env
if [ ! -f ".env" ] && [ ! -f "../.env" ]; then
    echo "ERROR: .env not found!"
    echo "Run: cp .env.example ../.env && nano ../.env"
    exit 1
fi

# 2. Aktivasi virtual environment jika tersedia
if [ -d "../venv" ]; then
    source ../venv/bin/activate
fi

echo "Starting Trading Bot..."
echo "Press 'q' to stop"
echo ""

# 3. Jalankan bot utama
python3 bot.py

