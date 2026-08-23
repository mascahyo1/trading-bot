"""
Script Pengujian Pembacaan dan Parsing File Lingkungan (.env)

Memeriksa keberadaan file .env serta mencetak semua key dan panjang value yang terdeteksi.

Author: AI Trading Bot
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

env_path = os.path.join(SCRIPT_DIR, ".env")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")

print(f"Env path: {env_path}")
print(f"Exists: {os.path.exists(env_path)}")

with open(env_path) as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            print(f"Key: [{k.strip()}] Value: [{v.strip()}] Len: {len(v.strip())}")

