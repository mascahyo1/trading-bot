#!/bin/bash
# ==============================================================================
# Script Otomatis Deployment VPS Ubuntu / Debian untuk Bot Crypto Indodax
# ==============================================================================
# Menyiapkan lingkungan runtime Python 3, virtualenv, dependensi pip,
# validasi konfigurasi .env, dan registrasi systemd service auto-start.
#
# Penggunaan:
#   bash deploy.sh
# ==============================================================================

set -e

echo "=========================================="
echo "  AI Trading Bot - Indodax VPS Deployment"
echo "=========================================="

# 1. Update paket sistem operasi
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# 2. Instalasi runtime Python, pip, virtualenv, git, screen
echo "[2/6] Installing Python and tools..."
sudo apt install -y python3 python3-pip python3-venv git screen

# 3. Clone atau pull repository terbaru dari GitHub
echo "[3/6] Cloning repository..."
if [ -d "trading" ]; then
    cd trading/indodax
    git pull
else
    git clone https://github.com/mascahyo1/trading.git
    cd trading/indodax
fi

# 4. Inisialisasi Python Virtual Environment (venv bersama) dan install requirements
echo "[4/6] Setting up Python environment..."
if [ ! -d "../venv" ]; then
    python3 -m venv ../venv
fi
source ../venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Pengecekan file konfigurasi lingkungan (.env)
echo "[5/6] Checking configuration..."
if [ ! -f "../.env" ] && [ ! -f ".env" ]; then
    echo "WARNING: .env not found!"
    echo "Copy .env.example to .env and fill your API keys:"
    echo "  cp .env.example ../.env"
    echo "  nano ../.env"
    echo ""
    read -p "Press Enter after you've configured .env..."
fi

# 6. Registrasi dan aktifkan service systemd untuk background daemon auto-restart
echo "[6/6] Setting up systemd service..."
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "Perintah Manajemen Service:"
echo "  Start:   sudo systemctl start trading-bot"
echo "  Stop:    sudo systemctl stop trading-bot"
echo "  Status:  sudo systemctl status trading-bot"
echo "  Logs:    journalctl -u trading-bot -f"
echo ""
echo "Atau jalankan secara manual:"
echo "  source ../venv/bin/activate"
echo "  python bot.py"
echo ""

