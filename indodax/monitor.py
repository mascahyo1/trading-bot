#!/usr/bin/env python3
"""
Indodax Bot Monitor - Analyze performance every 2 hours
Runs via cron: 0 */2 * * * /home/cahyo/trading/venv/bin/python3 /home/cahyo/trading/indodax/monitor.py
"""
import os
import sys
import json
import time
import glob
import logging
import urllib.request
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)

from config import now_jakarta, format_datetime, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""

def load_env():
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    env_path = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == "Telegram_Bot_Token":
                        TELEGRAM_TOKEN = v.strip()
                    elif k.strip() == "Telegram_Chat_ID":
                        TELEGRAM_CHAT_ID = v.strip()

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def parse_logs(hours=2):
    """Parse bot logs from last N hours"""
    cutoff = now_jakarta() - timedelta(hours=hours)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:")
    
    trades = []
    errors = []
    total_cycles = 0
    
    today = now_jakarta().strftime("%Y-%m-%d")
    yesterday = (now_jakarta() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    log_files = []
    for date_str in [yesterday, today]:
        log_file = os.path.join(LOG_DIR, f"{date_str}.log")
        if os.path.exists(log_file):
            log_files.append(log_file)
    
    for log_file in log_files:
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if "CYCLE #" in line:
                        total_cycles += 1
                    if "TRADE:" in line:
                        trades.append(line.strip())
                    if "ERROR" in line or "Traceback" in line:
                        errors.append(line.strip())
        except Exception:
            pass
    
    return {
        "trades": trades[-20:],
        "errors": errors[-10:],
        "total_cycles": total_cycles,
    }

def parse_trade_history():
    """Parse trade history JSON"""
    history_file = os.path.join(SCRIPT_DIR, "trade_history.json")
    if not os.path.exists(history_file):
        return []
    try:
        with open(history_file) as f:
            return json.load(f)
    except Exception:
        return []

def calculate_metrics(trades_history):
    """Calculate performance metrics"""
    if not trades_history:
        return {}
    
    total = len(trades_history)
    wins = [t for t in trades_history if t.get("pnl_amount", 0) > 0]
    losses = [t for t in trades_history if t.get("pnl_amount", 0) <= 0]
    
    total_pnl = sum(t.get("pnl_amount", 0) for t in trades_history)
    win_rate = len(wins) / total * 100 if total > 0 else 0
    
    avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0
    
    today = now_jakarta().strftime("%Y-%m-%d")
    today_trades = [t for t in trades_history if t.get("exit_time", "").startswith(today)]
    today_pnl = sum(t.get("pnl_amount", 0) for t in today_trades)
    
    return {
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "today_trades": len(today_trades),
        "today_pnl": round(today_pnl, 2),
    }

def analyze_with_llm(metrics, logs_summary):
    """Send analysis to LongCat API and get improvement suggestions"""
    if not LLM_API_KEY or not LLM_BASE_URL:
        return "LLM not configured for analysis"
    
    prompt = f"""You are an expert trading bot analyst. Analyze this Indodax crypto bot performance and suggest improvements.

## Performance Metrics (Last 24h)
- Total Trades: {metrics.get('total_trades', 0)}
- Win Rate: {metrics.get('win_rate', 0)}%
- Total PnL: {metrics.get('total_pnl', 0):+,.0f} IDR
- Today Trades: {metrics.get('today_trades', 0)}
- Today PnL: {metrics.get('today_pnl', 0):+,.0f} IDR
- Avg Win: {metrics.get('avg_win', 0):+,.0f} IDR
- Avg Loss: {metrics.get('avg_loss', 0):+,.0f} IDR

## Bot Activity (Last 2h)
- Total Cycles: {logs_summary['total_cycles']}
- Errors: {len(logs_summary['errors'])}

## Recent Errors
{chr(10).join(logs_summary['errors'][:5]) if logs_summary['errors'] else 'None'}

Provide:
1. Performance assessment (good/bad/neutral)
2. Top 2-3 specific improvements for the strategy
3. Any concerns or risks

Keep response concise (max 500 words). Use Indonesian language."""

    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert crypto trading bot analyst."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 800,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}",
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Analysis failed: {str(e)[:100]}"

def run_analysis():
    """Run full analysis and send report"""
    load_env()
    
    print(f"[{format_datetime()}] Starting analysis...")
    
    logs_summary = parse_logs(hours=2)
    trades_history = parse_trade_history()
    metrics = calculate_metrics(trades_history)
    
    llm_analysis = analyze_with_llm(metrics, logs_summary)
    
    msg = (
        f"<b>INDODAX BOT ANALYSIS</b>\n"
        f"{format_datetime()}\n"
        f"\n"
        f"<b>PERFORMANCE</b>\n"
        f"Win Rate: {metrics.get('win_rate', 0)}%\n"
        f"Total PnL: {metrics.get('total_pnl', 0):+,.0f} IDR\n"
        f"Today: {metrics.get('today_trades', 0)} trades, {metrics.get('today_pnl', 0):+,.0f} IDR\n"
        f"\n"
        f"<b>ANALYSIS</b>\n"
        f"{llm_analysis.replace('<', '&lt;').replace('>', '&gt;')}\n"
        f"\n"
        f"<b>ERRORS (24h):</b> {len(logs_summary['errors'])}"
    )
    
    if len(msg) > 4000:
        msg = msg[:4000] + "\n\n...(truncated)"
    
    send_telegram(msg)
    print(f"[{format_datetime()}] Analysis sent!")

if __name__ == "__main__":
    run_analysis()
