import os
import sys
import time
import json
import urllib.request
from datetime import datetime
from exchange import IndodaxExchange

EXCHANGE = IndodaxExchange()

def get_all_balances():
    """Get all non-zero balances with their IDR value"""
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
    """Convert any asset amount to IDR value"""
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
    """Get total portfolio value in IDR"""
    balances = get_all_balances()
    if not balances:
        return None

    total_idr = 0
    details = []
    for b in balances:
        idr_val = get_idr_value(b["asset"], b["total"])
        total_idr += idr_val
        if idr_val > 1000:
            details.append(f"  {b['asset']}: {b['total']:.6f} ≈ {idr_val:,.0f} IDR")

    return {"total_idr": total_idr, "details": details, "balances": balances}

def format_portfolio_report():
    """Format a portfolio report"""
    portfolio = get_total_portfolio_value()
    if not portfolio:
        return "Error fetching portfolio"

    lines = ["📊 <b>PORTFOLIO REPORT</b>"]
    lines.extend(portfolio["details"])
    lines.append(f"\n💰 <b>Total: {portfolio['total_idr']:,.0f} IDR</b>")
    return "\n".join(lines)

if __name__ == "__main__":
    print(format_portfolio_report())
