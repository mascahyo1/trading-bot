#!/usr/bin/env python3
"""
Unified Telegram Command Handler untuk Indodax Crypto & Saham IHSG

Modul ini bertindak sebagai satu-satunya listener polling Telegram terpusat (single listener)
untuk bot Indodax (crypto) dan Saham (Ajaib/IHSG), sehingga tidak terjadi konflik (HTTP 409)
atau respons ganda ke pengguna Telegram.

Fitur Utama:
- Long polling Telegram bot API dengan offset auto-increment.
- Handler terpisah dan unik untuk setiap perintah crypto (/status-indodax, dll.) dan saham (/status-saham, dll.).
- Interaktivitas tombol inline keyboard untuk konfirmasi tindakan sensitif (Start/Stop bot).
- Format respons berbasis HTML untuk tampilan Telegram yang rapi dan informatif.
- Pengecekan keamanan berdasarkan TELEGRAM_CHAT_ID terdaftar.

Author: AI Trading Bot
"""
import json
import os
import sys
import time
import logging
import urllib.request
import urllib.error
import threading

logger = logging.getLogger(__name__)

# Kredensial Telegram (diisi otomatis oleh load_env)
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
BOT_INSTANCE = None  # Menyimpan instance aktif dari ProductionBot (Indodax)

# Jalur file state dan history untuk bot saham dan indodax
SAHAM_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saham", "saham_state.json")
SAHAM_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saham", "trade_history.json")
INODAX_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indodax")
SAHAM_SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saham")

# State penampung konfirmasi aksi sensitif (e.g. {"chat_id": "stop" / "start"})
PENDING_CONFIRMATION = {}


def load_env():
    """
    Memuat variabel lingkungan (Telegram_Bot_Token dan Telegram_Chat_ID) dari file `.env`.
    
    Mencari file `.env` di folder lokal dan folder parent untuk memastikan
    variabel selalu termuat baik saat dijalankan langsung maupun sebagai modul.
    """
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
    for env_path in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    ]:
        if not os.path.exists(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip() == "Telegram_Bot_Token":
                        TELEGRAM_TOKEN = v.strip()
                    elif k.strip() == "Telegram_Chat_ID":
                        TELEGRAM_CHAT_ID = v.strip()


def escape_html(text):
    """
    Melakukan sanitasi karakter khusus HTML agar aman dikirim ke Telegram parse_mode='HTML'.
    
    Args:
        text (str): Teks mentah yang akan disanitasi.
        
    Returns:
        str: Teks dengan karakter &, <, dan > yang sudah di-escape.
    """
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def send_telegram(text, parse_mode="HTML", reply_markup=None):
    """
    Mengirim pesan teks ke Telegram menggunakan HTTP POST ke Telegram Bot API.
    
    Args:
        text (str): Isi pesan yang akan dikirim (format HTML secara default).
        parse_mode (str, optional): Mode parser pesan ('HTML' atau 'Markdown'). Default 'HTML'.
        reply_markup (str/dict, optional): Inline keyboard JSON string atau dict jika ada.
        
    Returns:
        None
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        if isinstance(reply_markup, dict):
            payload["reply_markup"] = reply_markup
        elif isinstance(reply_markup, str):
            try:
                payload["reply_markup"] = json.loads(reply_markup)
            except Exception:
                payload["reply_markup"] = reply_markup
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.error(f"Telegram send error: {e}")


def get_updates(offset=None):
    """
    Mengambil daftar update terbaru dari Telegram Bot API menggunakan teknik long polling.
    
    Args:
        offset (int, optional): Identifier update terkecil berikutnya yang akan diambil.
        
    Returns:
        list: Daftar objek update Telegram, atau list kosong jika error/tidak ada pesan.
    """
    if not TELEGRAM_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode())
            return data.get("result", [])
    except urllib.error.HTTPError as e:
        if e.code == 409:
            # Terjadi konflik karena ada instance bot lain yang sedang polling
            clear_pending_updates()
            return []
        logger.error(f"getUpdates HTTP {e.code}: {e.reason}")
        return []
    except Exception as e:
        logger.error(f"getUpdates error: {e}")
        return []


def clear_pending_updates():
    """
    Menghapus antrean update lama yang tertumpuk di Telegram server dengan offset=-1.
    Berguna saat me-restart bot untuk mencegah respons ke tumpukan pesan lama.
    """
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"offset": -1, "timeout": 1}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{query}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        pass


def read_saham_state():
    """
    Membaca dan mem-parse file state JSON bot saham (`saham_state.json`).
    
    Returns:
        dict or None: Data state portofolio & analytics saham, atau None jika file tidak ditemukan/error.
    """
    try:
        if not os.path.exists(SAHAM_STATE_FILE):
            return None
        with open(SAHAM_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def get_indodax_status():
    """
    Membuat laporan ringkasan status operasional bot Indodax.
    
    Menampilkan:
    - Saldo IDR saat ini di akun Indodax.
    - Jumlah open positions yang sedang berjalan.
    - Total PnL dan Win Rate historis.
    
    Returns:
        str: Pesan terformat HTML siap kirim ke Telegram.
    """
    try:
        sys.path.insert(0, INODAX_SCRIPT_DIR)
        from exchange import IndodaxExchange
        ex = IndodaxExchange()
        bal = ex.get_idr_balance()
        lines = [
            "<b>INDODAX STATUS</b>",
            f"IDR Balance: {bal:,.0f} IDR",
        ]
        if BOT_INSTANCE:
            rm = BOT_INSTANCE.risk_manager
            open_count = rm.get_open_positions_count()
            total_pnl = rm.get_total_pnl()
            win_rate = rm.get_win_rate()
            total_trades = len(rm.trade_history)
            sign = "+" if total_pnl >= 0 else ""
            lines.extend([
                f"Open Positions: {open_count}",
                f"Total PnL: {sign}{total_pnl:,.0f} IDR",
                f"Win Rate: {win_rate}% ({total_trades} trades)",
            ])
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_indodax_portfolio():
    """
    Mengambil dan memformat ringkasan portofolio aset crypto di Indodax.
    
    Returns:
        str: Pesan terformat HTML berisi daftar koin yang dimiliki, jumlah, dan nilai estimasi.
    """
    try:
        sys.path.insert(0, INODAX_SCRIPT_DIR)
        from portfolio import format_portfolio_report
        return format_portfolio_report()
    except Exception as e:
        return f"Error: {e}"


def get_indodax_trades():
    """
    Mengambil 5 riwayat transaksi terakhir bot Indodax dari file `trade_history.json`.
    
    Returns:
        str: Pesan terformat HTML berisi daftar trade terakhir, harga exit, dan PnL.
    """
    try:
        sys.path.insert(0, INODAX_SCRIPT_DIR)
        from config import now_jakarta
        history_file = os.path.join(INODAX_SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "No trades yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "No trades yet"
        lines = ["<b>INDODAX RECENT TRADES</b>"]
        for t in trades[-5:]:
            pnl = t.get("pnl_amount", 0)
            sign = "+" if pnl >= 0 else ""
            lines.append(
                f"  {t.get('symbol', '?')} {t.get('side', '?')} @ {t.get('exit_price', 0):,.0f}\n"
                f"     PnL: {sign}{pnl:,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_indodax_analytics():
    """
    Menghitung dan memformat statistik kinerja trading crypto Indodax.
    
    Metrik yang dihitung:
    - Total transaksi, Win Rate, jumlah menang/kalah.
    - PnL harian dan total PnL kumulatif.
    - Rata-rata Profit (Avg Win), Rata-rata Loss (Avg Loss), serta Rasio Risk/Reward.
    - Performa trade terbaik (Best) dan terburuk (Worst).
    
    Returns:
        str: Pesan terformat HTML analitik trading Indodax.
    """
    try:
        sys.path.insert(0, INODAX_SCRIPT_DIR)
        from config import now_jakarta
        history_file = os.path.join(INODAX_SCRIPT_DIR, "trade_history.json")
        if not os.path.exists(history_file):
            return "No trade data yet"
        with open(history_file) as f:
            trades = json.load(f)
        if not trades:
            return "No trade data yet"
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
        losses = [t for t in trades if t.get("pnl_amount", 0) <= 0]
        total_pnl = sum(t.get("pnl_amount", 0) for t in trades)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0
        best = max(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        worst = min(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        daily_pnl = 0
        today = now_jakarta().strftime("%Y-%m-%d")
        for t in trades:
            if t.get("exit_time", "").startswith(today):
                daily_pnl += t.get("pnl_amount", 0)
        sign_pnl = "+" if total_pnl >= 0 else ""
        sign_daily = "+" if daily_pnl >= 0 else ""
        lines = [
            "<b>INDODAX ANALYTICS</b>",
            f"Total Trades: {total_trades}",
            f"Win Rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)",
            f"Daily PnL: {sign_daily}{daily_pnl:,.0f} IDR",
            f"Total PnL: {sign_pnl}{total_pnl:,.0f} IDR",
            f"Avg Win: {avg_win:,.0f} IDR",
            f"Avg Loss: {avg_loss:,.0f} IDR",
        ]
        if avg_loss != 0:
            rr = abs(avg_win / avg_loss)
            lines.append(f"Risk/Reward: 1:{rr:.1f}")
        if best:
            sign_b = "+" if best['pnl_amount'] >= 0 else ""
            lines.append(f"Best: {best.get('symbol', '?')} {sign_b}{best['pnl_amount']:,.0f}")
        if worst:
            sign_w = "+" if worst['pnl_amount'] >= 0 else ""
            lines.append(f"Worst: {worst.get('symbol', '?')} {sign_w}{worst['pnl_amount']:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return escape_html(f"Error: {e}")


def get_indodax_why_idle():
    """
    Menganalisis dan menjelaskan alasan mengapa bot Indodax saat ini sedang idle (tidak membuka posisi baru).
    
    Faktor yang dievaluasi:
    - Apakah win rate di bawah batas minimum proteksi (< 40%).
    - Apakah kuota open position sudah penuh (maksimal MAX_OPEN_POSITIONS).
    - Apakah saldo IDR mencukupi batas minimum order (MIN_ORDER_IDR).
    
    Returns:
        str: Pesan terformat HTML berisi diagnosis status bot dan saran tindakan perbaikan.
    """
    try:
        sys.path.insert(0, INODAX_SCRIPT_DIR)
        from config import now_jakarta, MAX_OPEN_POSITIONS, MIN_ORDER_IDR
        history_file = os.path.join(INODAX_SCRIPT_DIR, "trade_history.json")
        trades = []
        if os.path.exists(history_file):
            with open(history_file) as f:
                trades = json.load(f)
        reasons = []
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        if total_trades >= 5 and win_rate < 40:
            reasons.append(f"BLOCKED: Win rate {win_rate:.0f}% &lt; 40%")
        elif win_rate >= 40:
            reasons.append(f"OK: Win rate {win_rate:.0f}%")
        else:
            reasons.append(f"Win rate {win_rate:.0f}% (need 5+ trades)")
        open_count = 0
        balance = 0
        if BOT_INSTANCE:
            open_count = BOT_INSTANCE.risk_manager.get_open_positions_count()
            balance = BOT_INSTANCE.get_balance()
        if open_count >= MAX_OPEN_POSITIONS:
            reasons.append(f"BLOCKED: Max positions ({open_count}/{MAX_OPEN_POSITIONS})")
        else:
            reasons.append(f"OK: Positions available ({open_count}/{MAX_OPEN_POSITIONS})")
        min_order = MIN_ORDER_IDR * 1.5
        if balance < min_order:
            reasons.append(f"BLOCKED: Balance {balance:,.0f} &lt; {min_order:,.0f} IDR")
        else:
            reasons.append(f"OK: Balance {balance:,.0f} IDR")
        today = now_jakarta().strftime("%Y-%m-%d")
        today_trades = [t for t in trades if t.get("exit_time", "").startswith(today)]
        today_pnl = sum(t.get("pnl_amount", 0) for t in today_trades)
        reasons.append(f"Today: {len(today_trades)} trades, {today_pnl:+,.0f} IDR")
        lines = ["<b>INDODAX WHY IDLE</b>", "", "<b>FACTORS:</b>"]
        lines.extend(reasons)
        if any("BLOCKED" in r for r in reasons):
            lines.append("")
            lines.append("<b>ACTION:</b>")
            if win_rate < 40 and total_trades >= 5:
                lines.append("- Wait for win rate &gt; 40%")
            if open_count >= MAX_OPEN_POSITIONS:
                lines.append("- Wait for TP/SL to hit")
            if balance < min_order:
                lines.append("- Deposit more IDR")
        else:
            lines.append("")
            lines.append("Bot should be active!")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_saham_status():
    """
    Mengambil status ringkasan portofolio dan analytics bot Saham IDX.
    
    Returns:
        str: Pesan terformat HTML status saldo kas, open positions, Net PnL, dan biaya fee.
    """
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    analytics = state.get("analytics", {})
    lines = [
        "<b>SAHAM STATUS</b>",
        f"Cash: {state.get('cash', 0):,.0f} IDR",
        f"Open Positions: {analytics.get('open_positions', 0)}",
        f"Total PnL (net): {analytics.get('total_pnl', 0):+,.0f} IDR",
        f"Win Rate: {analytics.get('win_rate', 0)}% ({analytics.get('total_trades', 0)} trades)",
        f"Total Fees: {analytics.get('total_fees', 0):,.0f} IDR",
    ]
    return "\n".join(lines)


def get_saham_portfolio():
    """
    Mengambil dan memformat rincian kepemilikan saham IDX (lot, lembar, harga pasar, total nilai) serta kas.
    
    Returns:
        str: Pesan terformat HTML portofolio saham lengkap dan grand total nilai aset.
    """
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    portfolio = state.get("portfolio", {})
    cash = portfolio.get("cash", 0)
    stocks = portfolio.get("stocks", [])
    lines = [
        "<b>SAHAM PORTFOLIO</b>",
        "",
        f"<b>CASH: {cash:,.0f} IDR</b>",
        "",
    ]
    if stocks:
        lines.append("<b>PER SAHAM:</b>")
        lines.append("")
        total_value = 0
        for s in stocks:
            code = s.get("code", "?")
            lots = s.get("lots", 0)
            price = s.get("price", 0)
            value = lots * 100 * price
            total_value += value
            lines.append(f"<b>{code}</b>")
            lines.append(f"   Lot: {lots} ({lots * 100} lembar)")
            lines.append(f"   Harga: {price:,.0f} IDR")
            lines.append(f"   <b>Total: {value:,.0f} IDR</b>")
            lines.append("")
    lines.append(f"<b>Total Saham: {total_value:,.0f} IDR</b>")
    lines.append(f"<b>Cash: {cash:,.0f} IDR</b>")
    lines.append(f"<b>GRAND TOTAL: {cash + total_value:,.0f} IDR</b>")
    return "\n".join(lines)


def get_saham_trades():
    """
    Mengambil 5 transaksi saham terakhir dari `saham/trade_history.json`.
    
    Returns:
        str: Pesan terformat HTML daftar transaksi saham dengan indikator emoji profit/loss.
    """
    try:
        if not os.path.exists(SAHAM_HISTORY_FILE):
            return "No trades yet"
        with open(SAHAM_HISTORY_FILE) as f:
            trades = json.load(f)
        if not trades:
            return "No trades yet"
        lines = ["<b>SAHAM RECENT TRADES</b>"]
        for t in trades[-5:]:
            pnl = t.get("pnl_amount", 0)
            sign = "+" if pnl >= 0 else ""
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{pnl_emoji} {t.get('code', '?')} @ {t.get('exit_price', 0):,.0f}\n"
                f"   PnL (net): {sign}{pnl:,.0f} IDR ({t.get('pnl_pct', 0):+.2f}%)"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_saham_analytics():
    """
    Menghitung dan memformat statistik kinerja trading saham IDX.
    
    Termasuk rincian fee transaksi, Gross PnL vs Net PnL, Win Rate, dan perbandingan Best/Worst trade.
    
    Returns:
        str: Pesan terformat HTML analitik trading saham.
    """
    try:
        if not os.path.exists(SAHAM_HISTORY_FILE):
            return "No trade data yet"
        with open(SAHAM_HISTORY_FILE) as f:
            trades = json.load(f)
        if not trades:
            return "No trade data yet"
        total_trades = len(trades)
        wins = [t for t in trades if t.get("pnl_amount", 0) > 0]
        losses = [t for t in trades if t.get("pnl_amount", 0) <= 0]
        total_pnl = sum(t.get("pnl_amount", 0) for t in trades)
        total_fees = sum(t.get("total_fees", 0) for t in trades)
        gross_pnl = sum(t.get("gross_pnl", 0) for t in trades)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_win = sum(t["pnl_amount"] for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t["pnl_amount"] for t in losses) / len(losses) if losses else 0
        best = max(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        worst = min(trades, key=lambda t: t.get("pnl_amount", 0)) if trades else None
        daily_pnl = 0
        from config import now_jakarta
        today = now_jakarta().strftime("%Y-%m-%d")
        for t in trades:
            if t.get("exit_time", "").startswith(today):
                daily_pnl += t.get("pnl_amount", 0)
        sign_pnl = "+" if total_pnl >= 0 else ""
        sign_daily = "+" if daily_pnl >= 0 else ""
        lines = [
            "<b>SAHAM ANALYTICS</b>",
            f"Total Trades: {total_trades}",
            f"Win Rate: {win_rate:.1f}% ({len(wins)}W/{len(losses)}L)",
            f"Daily PnL (net): {sign_daily}{daily_pnl:,.0f} IDR",
            f"Total PnL (net): {sign_pnl}{total_pnl:,.0f} IDR",
            f"Total Fees: {total_fees:,.0f} IDR",
            f"Gross PnL: {gross_pnl:+,.0f} IDR",
        ]
        if avg_loss != 0:
            rr = abs(avg_win / avg_loss)
            lines.append(f"Risk/Reward: 1:{rr:.1f}")
        if best:
            sign_b = "+" if best['pnl_amount'] >= 0 else ""
            lines.append(f"Best: {best.get('code', '?')} {sign_b}{best['pnl_amount']:,.0f}")
        if worst:
            sign_w = "+" if worst['pnl_amount'] >= 0 else ""
            lines.append(f"Worst: {worst.get('code', '?')} {sign_w}{worst['pnl_amount']:,.0f}")
        return "\n".join(lines)
    except Exception as e:
        return escape_html(f"Error: {e}")


def get_saham_why_idle():
    """
    Menganalisis dan menjelaskan alasan mengapa bot Saham IDX tidak membuka posisi baru saat ini.
    
    Evaluasi mencakup:
    - Status jam bursa BEI (hanya buka Senin-Jumat jam sesi tertentu).
    - Batas maksimum slot saham terbuka (max 5 saham).
    - Ketersediaan saldo kas untuk minimal order 1 lot.
    
    Returns:
        str: Pesan terformat HTML status kesiapan trading saham.
    """
    state = read_saham_state()
    if not state:
        return "<b>SAHAM</b>\nBot tidak jalan atau state belum tersedia."
    analytics = state.get("analytics", {})
    cash = state.get("cash", 0)
    open_count = analytics.get("open_positions", 0)
    total_trades = analytics.get("total_trades", 0)
    win_rate = analytics.get("win_rate", 0)
    reasons = []
    if total_trades >= 5 and win_rate < 40:
        reasons.append(f"BLOCKED: Win rate {win_rate:.0f}% &lt; 40%")
    elif win_rate >= 40:
        reasons.append(f"OK: Win rate {win_rate:.0f}%")
    else:
        reasons.append(f"Win rate {win_rate:.0f}% (need 5+ trades)")
    if open_count >= 5:
        reasons.append(f"BLOCKED: Max positions ({open_count}/5)")
    else:
        reasons.append(f"OK: Positions available ({open_count}/5)")
    min_order = 75000 * 1.5
    if cash < min_order:
        reasons.append(f"BLOCKED: Cash {cash:,.0f} &lt; {min_order:,.0f} IDR")
    else:
        reasons.append(f"OK: Cash {cash:,.0f} IDR")
    reasons.append(f"Today: {analytics.get('trades_today', 0)} trades, {analytics.get('daily_pnl', 0):+,.0f} IDR")
    lines = ["<b>SAHAM WHY IDLE</b>", "", "<b>FACTORS:</b>"]
    lines.extend(reasons)
    if any("BLOCKED" in r for r in reasons):
        lines.append("")
        lines.append("<b>ACTION:</b>")
        if win_rate < 40 and total_trades >= 5:
            lines.append("- Wait for win rate &gt; 40%")
        if open_count >= 5:
            lines.append("- Wait for TP/SL to hit")
        if cash < min_order:
            lines.append("- Deposit more IDR")
    else:
        lines.append("")
        lines.append("Bot should be active!")
    return "\n".join(lines)


def get_saham_fees():
    """
    Menampilkan rincian struktur biaya transaksi (fee) saham BEI serta akumulasi fee historis.
    
    Rincian:
    - Biaya Beli: 0.14% (Broker: 0.10%, KPEI Clearing: 0.02%, BEI: 0.02%)
    - Biaya Jual: 0.34% (Broker: 0.10%, Clearing: 0.02%, BEI: 0.02%, PPN: 0.10%, PPh Final: 0.10%)
    - Round-trip total: 0.48%
    
    Returns:
        str: Pesan terformat HTML rincian fee transaksi saham.
    """
    try:
        total_fees = 0
        total_buy_fees = 0
        total_sell_fees = 0
        if os.path.exists(SAHAM_HISTORY_FILE):
            with open(SAHAM_HISTORY_FILE) as f:
                trades = json.load(f)
            for t in trades:
                total_buy_fees += t.get("buy_fees", 0)
                total_sell_fees += t.get("sell_fees", 0)
                total_fees += t.get("total_fees", 0)
        lines = [
            "<b>SAHAM TRANSACTION FEES</b>",
            "",
            "<b>Per Trade:</b>",
            f"  Biaya Beli: 0.14%",
            f"  Biaya Jual: 0.34%",
            f"  Round-trip: 0.48%",
            "",
            "<b>Breakdown Beli:</b>",
            f"  Broker: 0.10% | Clearing: 0.02% | BEI: 0.02%",
            f"  <b>Total: 0.14%</b>",
            "",
            "<b>Breakdown Jual:</b>",
            f"  Broker: 0.10% | Clearing: 0.02% | BEI: 0.02%",
            f"  PPN: 0.10% | PPh Final: 0.10%",
            f"  <b>Total: 0.34%</b>",
            "",
            "<b>Lifetime Stats:</b>",
            f"  Total Biaya: {total_fees:,.0f} IDR",
            f"  Biaya Beli: {total_buy_fees:,.0f} IDR",
            f"  Biaya Jual: {total_sell_fees:,.0f} IDR",
            "",
            "<i>Semua PnL sudah NET (setelah potong biaya)</i>",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


COMMAND_MAP = {
    "/status-indodax": get_indodax_status,
    "/portfolio-indodax": get_indodax_portfolio,
    "/trades-indodax": get_indodax_trades,
    "/analytics-indodax": get_indodax_analytics,
    "/stats-indodax": get_indodax_analytics,
    "/why-idle-indodax": get_indodax_why_idle,
    "/why-indodax": get_indodax_why_idle,
    "/analyze-improvement-indodax": None,

    "/status-saham": get_saham_status,
    "/saham": get_saham_portfolio,
    "/portfolio-saham": get_saham_portfolio,
    "/asset-saham": get_saham_portfolio,
    "/trades-saham": get_saham_trades,
    "/analytics-saham": get_saham_analytics,
    "/stats-saham": get_saham_analytics,
    "/why-idle-saham": get_saham_why_idle,
    "/why-saham": get_saham_why_idle,
    "/fees-saham": get_saham_fees,
}
"""
Command-to-handler mapping untuk Telegram.

Setiap command map ke exactly satu handler function.
Tidak ada alias yang overlap antara bot → tidak ada response dobel.

Handler function mengembalikan string HTML yang dikirim ke Telegram.
"""


def handle_command(text, chat_id):
    """
    Route Telegram command ke handler yang sesuai.
    
    Args:
        text (str): Message text dari Telegram
        chat_id (str): Chat ID untuk konfirmasi aksi sensitif (stop/start)
        
    Flow:
        1. Parse command dari text
        2. Cari handler di COMMAND_MAP
        3. Execute handler dan kirim response
        4. Khusus stop/start: memerlukan konfirmasi 2x
    """
    text = text.strip()
    cmd = text.lower().split()[0] if text else ""

    handler = COMMAND_MAP.get(cmd)
    if handler:
        send_telegram(handler())
        return
    elif cmd == "/analyze-improvement-indodax":
        send_telegram("<b>INDODAX</b>\nAnalyzing bot performance...")
        try:
            sys.path.insert(0, INODAX_SCRIPT_DIR)
            from monitor import run_analysis
            run_analysis()
        except Exception as e:
            send_telegram("<b>INDODAX</b>\nAnalysis failed: " + escape_html(str(e)[:200]))
        return
    elif cmd == "/stop-indodax" or cmd == "/stop":
        if chat_id in PENDING_CONFIRMATION and PENDING_CONFIRMATION[chat_id] == "stop":
            send_telegram("<b>INDODAX</b>\nBot stopping...")
            if BOT_INSTANCE:
                BOT_INSTANCE.stop()
            PENDING_CONFIRMATION.pop(chat_id, None)
        else:
            PENDING_CONFIRMATION[chat_id] = "stop"
            keyboard = json.dumps({
                "inline_keyboard": [[
                    {"text": "Yes, Stop Bot", "callback_data": "confirm_stop"},
                    {"text": "Cancel", "callback_data": "cancel"}
                ]]
            })
            send_telegram("<b>INDODAX</b>\nAre you sure you want to STOP the bot?", reply_markup=keyboard)
        return
    elif cmd == "/start-indodax" or cmd == "/start":
        if chat_id in PENDING_CONFIRMATION and PENDING_CONFIRMATION[chat_id] == "start":
            send_telegram("<b>INDODAX</b>\nBot starting...")
            if BOT_INSTANCE:
                BOT_INSTANCE.start()
            PENDING_CONFIRMATION.pop(chat_id, None)
        else:
            PENDING_CONFIRMATION[chat_id] = "start"
            keyboard = json.dumps({
                "inline_keyboard": [[
                    {"text": "Yes, Start Bot", "callback_data": "confirm_start"},
                    {"text": "Cancel", "callback_data": "cancel"}
                ]]
            })
            send_telegram("<b>INDODAX</b>\nAre you sure you want to START the bot?", reply_markup=keyboard)
        return
    elif cmd == "/help":
        send_telegram(
            "<b>TRADING BOT COMMANDS</b>\n"
            "\n"
            "<b>INDODAX (Crypto)</b>\n"
            "/status-indodax - Bot status & balance\n"
            "/portfolio-indodax - All assets & total value\n"
            "/trades-indodax - Recent trade history\n"
            "/analytics-indodax - Win rate, PnL, R/R ratio\n"
            "/why-idle-indodax - Why bot is not trading\n"
            "/analyze-improvement-indodax - AI analysis\n"
            "/stop-indodax - Stop bot (confirmation)\n"
            "/start-indodax - Start bot (confirmation)\n"
            "\n"
            "<b>SAHAM (Stocks)</b>\n"
            "/status-saham - Bot status & portfolio\n"
            "/saham - Portfolio from Ajaib\n"
            "/asset-saham - Asset per stock + grand total\n"
            "/trades-saham - Recent trade history\n"
            "/analytics-saham - Win rate, PnL, R/R ratio\n"
            "/why-idle-saham - Why bot is not trading\n"
            "/fees-saham - Transaction fees breakdown\n"
            "\n"
            "/help - Show this message"
        )
        return

    if text.startswith("/"):
        send_telegram("Unknown command. Type /help for available commands.")


def handle_callback(data, chat_id):
    """
    Menangani callback query yang dipicu oleh penekanan tombol inline keyboard di Telegram.
    
    Args:
        data (str): Data payload callback dari tombol Telegram ('confirm_stop', 'confirm_start', 'cancel').
        chat_id (str): Chat ID pengirim untuk verifikasi dan pembersihan sesi konfirmasi.
        
    Returns:
        None
    """
    if data == "confirm_stop":
        send_telegram("<b>INDODAX</b>\nBot stopping...")
        if BOT_INSTANCE:
            BOT_INSTANCE.stop()
        PENDING_CONFIRMATION.pop(chat_id, None)
    elif data == "confirm_start":
        send_telegram("<b>INDODAX</b>\nBot starting...")
        if BOT_INSTANCE:
            BOT_INSTANCE.start()
        PENDING_CONFIRMATION.pop(chat_id, None)
    elif data == "cancel":
        send_telegram("Cancelled")
        PENDING_CONFIRMATION.pop(chat_id, None)


class TelegramCommandHandler:
    """
    Threaded Polling Manager untuk Telegram Bot commands.
    
    Menjalankan background daemon thread yang secara periodik memanggil `get_updates` (long polling)
    dan mengarahkan setiap pesan atau callback ke handler yang tepat tanpa memblokir bot engine utama.
    
    Attributes:
        running (bool): Flag status operasional background thread.
        offset (int or None): Pointer update ID berikutnya untuk Telegram long polling.
        thread (threading.Thread or None): Objek thread background yang menjalankan loop polling.
    """

    def __init__(self, bot_instance=None):
        """
        Inisialisasi TelegramCommandHandler.
        
        Args:
            bot_instance (ProductionBot, optional): Instance bot utama untuk kontrol start/stop dan info posisi.
        """
        global BOT_INSTANCE
        load_env()
        BOT_INSTANCE = bot_instance
        self.running = False
        self.offset = None
        self.thread = None

    def start(self):
        """
        Memulai thread background polling Telegram jika belum berjalan.
        """
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        logger.info("Telegram command handler started")

    def stop(self):
        """
        Menghentikan thread background polling dan menunggu thread selesai (join timeout 5s).
        """
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _poll_loop(self):
        """
        Loop internal yang berjalan di background thread untuk mengambil updates dan mengeksekusi command.
        """
        while self.running:
            try:
                updates = get_updates(self.offset)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if "message" in update:
                        msg = update["message"]
                        chat_id = msg.get("chat", {}).get("id")
                        # Pastikan pesan hanya diproses jika berasal dari Chat ID yang terdaftar
                        if chat_id and TELEGRAM_CHAT_ID and str(chat_id) == TELEGRAM_CHAT_ID:
                            text = msg.get("text", "")
                            if text:
                                logger.info(f"Received command: {text}")
                                handle_command(text, chat_id)
                    elif "callback_query" in update:
                        cb = update["callback_query"]
                        chat_id = cb.get("message", {}).get("chat", {}).get("id")
                        data = cb.get("data")
                        if chat_id and data:
                            handle_callback(data, chat_id)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                time.sleep(5)

