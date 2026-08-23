"""
Manajemen Portofolio & Valuasi Aset Kripto Indodax

Modul ini bertugas menghitung dan merekap seluruh saldo koin non-nol di akun pengguna,
mengonversi nilainya ke ekuivalen Rupiah (IDR) berdasarkan harga ticker real-time,
serta memformat laporan portofolio untuk Telegram dan CLI.

Author: AI Trading Bot
"""

import os
import sys
import time
import json
import urllib.request
from datetime import datetime
from exchange import IndodaxExchange

# Inisialisasi singleton instance IndodaxExchange
EXCHANGE = IndodaxExchange()


def get_all_balances():
    """
    Mengambil semua saldo aset koin dan fiat yang nilainya lebih dari nol (non-zero balances).
    
    Returns:
        list or None: Daftar dictionary saldo [{'asset': 'BTC', 'free': 0.01, 'locked': 0.0, 'total': 0.01}, ...],
                      atau None jika terjadi kesalahan koneksi/API.
    """
    result = EXCHANGE.get_balance()
    if result.get("error"):
        return None

    balances = []
    for b in result.get("balances", []):
        free = float(b.get("free", 0))
        locked = float(b.get("locked", 0))
        total = free + locked
        if total > 0:
            balances.append({
                "asset": b["asset"],
                "free": free,
                "locked": locked,
                "total": total,
            })
    return balances


def get_idr_value(asset, amount):
    """
    Mengonversi sejumlah unit aset koin menjadi estimasi nominal Rupiah (IDR) via harga pasar terkini.
    
    Args:
        asset (str): Simbol aset (misal 'IDR', 'BTC', 'ETH').
        amount (float): Kuantitas aset.
        
    Returns:
        float: Nilai ekuivalen dalam Rupiah (IDR).
    """
    if asset == "IDR":
        return amount
    if amount <= 0:
        return 0
    pair = f"{asset}/IDR"
    ticker = EXCHANGE.fetch_ticker(pair)
    if ticker and ticker.get("last"):
        return amount * ticker["last"]
    return 0


def get_total_portfolio_value():
    """
    Menghitung total kekayaan bersih portofolio akun Indodax (Grand Total IDR).
    
    Returns:
        dict or None: Dictionary berisi 'total_idr', 'details' (daftar baris ringkasan per koin > Rp 1.000),
                      dan 'balances', atau None jika gagal mengambil data.
    """
    balances = get_all_balances()
    if not balances:
        return None

    total_idr = 0
    details = []
    for b in balances:
        idr_val = get_idr_value(b["asset"], b["total"])
        total_idr += idr_val
        # Hanya tampilkan aset yang bernilai signifikan (> Rp 1.000) untuk kerapian laporan
        if idr_val > 1000:
            details.append(f"  {b['asset']}: {b['total']:.6f} ≈ {idr_val:,.0f} IDR")

    return {"total_idr": total_idr, "details": details, "balances": balances}


def format_portfolio_report():
    """
    Membuat laporan ringkasan portofolio terformat HTML siap kirim ke Telegram atau print CLI.
    
    Returns:
        str: String teks HTML laporan portofolio.
    """
    portfolio = get_total_portfolio_value()
    if not portfolio:
        return "Error fetching portfolio"

    lines = ["📊 <b>PORTFOLIO REPORT</b>"]
    lines.extend(portfolio["details"])
    lines.append(f"\n💰 <b>Total: {portfolio['total_idr']:,.0f} IDR</b>")
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_portfolio_report())

