#!/bin/bash
# Deploy script untuk VPS Ubuntu/Debian
# Jalankan: bash deploy.sh

set -e

echo "=========================================="
echo "  AI Trading Bot - VPS Deployment"
echo "=========================================="

# Update system
echo "[1/6] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install dependencies
echo "[2/6] Installing Python and tools..."
sudo apt install -y python3 python3-pip python3-venv git screen

# Clone repo
echo "[3/6] Cloning repository..."
if [ -d "trading-bot" ]; then
    cd trading-bot
    git pull
else
    git clone https://github.com/mascahyo1/trading-bot.git
    cd trading-bot
fi

# Setup virtual environment
echo "[4/6] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Check .env
echo "[5/6] Checking configuration..."
if [ ! -f ".env" ]; then
    echo "WARNING: .env not found!"
    echo "Copy .env.example to .env and fill your API keys:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    read -p "Press Enter after you've configured .env..."
fi

# Setup systemd service for auto-start
echo "[6/6] Setting up systemd service..."
sudo tee /etc/systemd/system/trading-bot.service > /dev/null <<EOF
[Unit]
Description=AI Trading Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python bot.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
EOF

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
echo "  source venv/bin/activate"
echo "  python bot.py"
echo ""
echo "IP Address:"
curl -s ifconfig.me
echo ""
