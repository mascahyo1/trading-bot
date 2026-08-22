#!/bin/bash
# Deploy script untuk VPS Ubuntu/Debian
# Jalankan: bash deploy.sh

set -e

echo "=========================================="
echo "  AI Trading Bot - Indodax VPS Deployment"
echo "=========================================="

# Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing Python and tools..."
sudo apt install -y python3 python3-pip python3-venv git screen

# Clone repo
echo "[3/6] Cloning repository..."
if [ -d "trading" ]; then
    cd trading/indodax
    git pull
else
    git clone https://github.com/mascahyo1/trading.git
    cd trading/indodax
fi

# Setup virtual environment (shared venv in parent)
echo "[4/6] Setting up Python environment..."
if [ ! -d "../venv" ]; then
    python3 -m venv ../venv
fi
source ../venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Check .env
echo "[5/6] Checking configuration..."
if [ ! -f "../.env" ] && [ ! -f ".env" ]; then
    echo "WARNING: .env not found!"
    echo "Copy .env.example to .env and fill your API keys:"
    echo "  cp .env.example ../.env"
    echo "  nano ../.env"
    echo ""
    read -p "Press Enter after you've configured .env..."
fi

# Setup systemd service for auto-start
echo "[6/6] Setting up systemd service..."
sudo cp trading-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable trading-bot

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "Commands:"
echo "  Start:   sudo systemctl start trading-bot"
echo "  Stop:    sudo systemctl stop trading-bot"
echo "  Status:  sudo systemctl status trading-bot"
echo "  Logs:    journalctl -u trading-bot -f"
echo ""
echo "Or run manually:"
echo "  source ../venv/bin/activate"
echo "  python bot.py"
echo ""
