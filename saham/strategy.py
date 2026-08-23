"""
Trading Strategy & Risk Management untuk Saham Indonesia

Mengimplementasikan:
- Position tracking dengan stop-loss, take-profit, trailing stop
- Fee-aware pricing (entry price include buy fees, PnL net of sell fees)
- Dollar Cost Averaging (DCA) untuk averaging down
- Partial selling untuk profit taking bertahap
- Risk management dengan position sizing dan daily loss limit

Biaya Transaksi (Otomatis Dihitung):
- Buy: 0.14% (broker + clearing + BEI)
- Sell: 0.34% (broker + clearing + BEI + PPN + PPh)
- Round-trip: 0.48%

Fitur:
- Entry price sudah include buy fees (true cost basis)
- PnL dihitung net setelah sell fees
- Break-even price dihitung untuk mengetahui titik impas
- Stop-loss pada -3% dari cost basis
- Take-profit pada +8% dari cost basis
- Trailing stop 5% dari harga tertinggi

Author: AI Trading Bot
"""

import json
import os
import logging
from datetime import datetime
from config import (
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
    TRAILING_STOP_PCT,
    MAX_OPEN_POSITIONS,
    POSITION_SIZE_IDR,
    MIN_ORDER_IDR,
    LOT_SIZE,
    TRADE_HISTORY_FILE,
    MAX_DAILY_LOSS_PCT,
    BUY_TOTAL_FEE_PCT,
    SELL_TOTAL_FEE_PCT,
    ROUND_TRIP_FEE_PCT,
    now_jakarta,
    format_datetime,
)

logger = logging.getLogger(__name__)


class Position:
    """
    Merepresentasikan posisi saham yang terbuka.
    
    Attributes:
        symbol (str): Kode saham (mis. "BBCA.JK")
        code (str): Kode singkat (mis. "BBCA")
        entry_price_market (float): Harga beli di pasar
        entry_price (float): Cost basis (include buy fees)
        lots (int): Jumlah lot (1 lot = 100 lembar)
        shares (int): Jumlah lembar (lots * 100)
        stop_loss (float): Harga stop loss
        take_profit (float): Harga take profit
        break_even_price (float): Harga impas (include sell fees)
        status (str): "open" atau "closed"
    """

    def __init__(self, symbol, entry_price, lots, code=None):
        """
        Inisialisasi posisi saham baru.
        
        Args:
            symbol (str): Kode saham (mis. "BBCA.JK")
            entry_price (float): Harga beli di pasar
            lots (int): Jumlah lot
            code (str): Kode singkat saham
        """
        self.symbol = symbol
        self.code = code or symbol.replace(".JK", "")
        self.entry_price_market = entry_price
        self.entry_price = entry_price * (1 + BUY_TOTAL_FEE_PCT)
        self.initial_lots = lots
        self.lots = lots
        self.shares = lots * LOT_SIZE
        self.stop_loss = self.entry_price * (1 - STOP_LOSS_PCT)
        self.take_profit = self.entry_price * (1 + TAKE_PROFIT_PCT)
        self.break_even_price = self.entry_price * (1 + SELL_TOTAL_FEE_PCT)
        self.highest_price = entry_price
        self.trailing_stop_pct = TRAILING_STOP_PCT
        self.entry_time = now_jakarta().isoformat()
        self.status = "open"
        self.partial_sell_count = 0
        self.dca_count = 0
        self.tp1_pct = 0.04
        self.tp2_pct = 0.08
        self.dca1_pct = 0.03
        self.dca2_pct = 0.06
        self.total_buy_fees = 0
        self.total_sell_fees = 0
        self.total_buy_cost = 0
        self.total_sell_proceeds = 0

    def get_dca1_price(self):
        """
        Menghitung harga pemicu DCA level 1 (-3% dari harga entry cost basis).
        
        Returns:
            float: Harga pemicu DCA 1.
        """
        return self.entry_price * (1 - self.dca1_pct)

    def get_dca2_price(self):
        """
        Menghitung harga pemicu DCA level 2 (-6% dari harga entry cost basis).
        
        Returns:
            float: Harga pemicu DCA 2.
        """
        return self.entry_price * (1 - self.dca2_pct)

    def should_dca(self, current_price):
        """
        Mengevaluasi apakah harga saat ini telah menyentuh batas averaging down (DCA).
        
        Args:
            current_price (float): Harga saham di pasar saat ini.
            
        Returns:
            bool: True jika memenuhi syarat DCA, False jika tidak.
        """
        if self.dca_count >= 2:
            return False
        if self.dca_count == 0 and current_price <= self.get_dca1_price():
            return True
        if self.dca_count == 1 and current_price <= self.get_dca2_price():
            return True
        return False

    def dca_lots(self):
        """
        Menghitung alokasi jumlah lot untuk averaging down.
        
        Returns:
            int: Jumlah lot DCA (50% dari lot awal pada DCA 1, 25% pada DCA 2).
        """
        if self.dca_count == 0:
            return max(1, self.initial_lots // 2)
        return max(1, self.initial_lots // 4)

    def update_trailing_stop(self, current_price):
        """
        Memperbarui harga trailing stop jika harga pasar menembus rekor tertinggi baru (highest price).
        
        Args:
            current_price (float): Harga saham saat ini.
            
        Returns:
            bool: True jika stop loss berhasil dinaikkan, False jika tidak ada perubahan.
        """
        if current_price > self.highest_price:
            self.highest_price = current_price
            new_stop = current_price * (1 - self.trailing_stop_pct)
            if new_stop > self.stop_loss:
                self.stop_loss = new_stop
                return True
        return False

    def check_trailing_stop(self, current_price):
        """
        Mengecek apakah harga saat ini telah menembus ke bawah batas trailing stop.
        
        Args:
            current_price (float): Harga saham saat ini.
            
        Returns:
            bool: True jika trailing stop tertembus, False jika masih aman.
        """
        return current_price <= self.stop_loss

    def get_tp1_price(self):
        """
        Menghitung harga target Take Profit tier 1 (+4% dari cost basis).
        
        Returns:
            float: Harga target TP1.
        """
        return self.entry_price * (1 + self.tp1_pct)

    def get_tp2_price(self):
        """
        Menghitung harga target Take Profit tier 2 (+8% dari cost basis).
        
        Returns:
            float: Harga target TP2.
        """
        return self.entry_price * (1 + self.tp2_pct)

    def should_partial_sell(self, current_price):
        """
        Mengecek apakah posisi memenuhi kriteria penjualan parsial pada TP1 (+4%).
        
        Args:
            current_price (float): Harga pasar saat ini.
            
        Returns:
            bool: True jika belum pernah partial sell dan harga >= TP1.
        """
        if self.partial_sell_count == 0 and current_price >= self.get_tp1_price():
            return True
        return False

    def should_full_sell(self, current_price):
        """
        Mengecek apakah sisa posisi harus ditutup penuh pada TP2 (+8%).
        
        Args:
            current_price (float): Harga pasar saat ini.
            
        Returns:
            bool: True jika sudah pernah partial sell dan harga >= TP2.
        """
        if self.partial_sell_count >= 1 and current_price >= self.get_tp2_price():
            return True
        return False

    def partial_sell_lots(self):
        """
        Menghitung jumlah lot yang dilepas saat partial sell (50% dari initial lots).
        
        Returns:
            int: Jumlah lot yang dijual.
        """
        return max(1, self.initial_lots // 2)

    def current_value(self, current_price):
        """
        Menghitung nilai pasar bruto posisi saham saat ini (Lots * 100 * Harga).
        
        Args:
            current_price (float): Harga saham saat ini.
            
        Returns:
            float: Nominal nilai pasar bruto.
        """
        return self.lots * LOT_SIZE * current_price

    def unrealized_pnl(self, current_price):
        """
        Menghitung floating Profit/Loss bersih setelah dikurangi estimasi fee transaksi jual (0.34%).
        
        Args:
            current_price (float): Harga pasar saat ini.
            
        Returns:
            float: Nominal floating PnL bersih (Net IDR).
        """
        gross_pnl = (current_price - self.entry_price) * self.lots * LOT_SIZE
        estimated_sell_fees = current_price * self.lots * LOT_SIZE * SELL_TOTAL_FEE_PCT
        return gross_pnl - estimated_sell_fees

    def unrealized_pnl_pct(self, current_price):
        """
        Menghitung persentase floating Profit/Loss bersih terhadap total modal yang diinvestasikan.
        
        Args:
            current_price (float): Harga pasar saat ini.
            
        Returns:
            float: Persentase floating return bersih (%).
        """
        if self.entry_price == 0:
            return 0
        net_pnl = self.unrealized_pnl(current_price)
        total_cost = self.entry_price * self.lots * LOT_SIZE
        return (net_pnl / total_cost) * 100

    def to_dict(self):
        """
        Mengonversi objek Position menjadi dictionary serializable JSON.
        
        Returns:
            dict: Representasi dictionary posisi saham.
        """
        return {
            "symbol": self.symbol,
            "code": self.code,
            "entry_price": self.entry_price,
            "entry_price_market": self.entry_price_market,
            "lots": self.lots,
            "initial_lots": self.initial_lots,
            "shares": self.shares,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "break_even_price": self.break_even_price,
            "highest_price": self.highest_price,
            "entry_time": self.entry_time,
            "status": self.status,
            "partial_sell_count": self.partial_sell_count,
            "total_buy_fees": self.total_buy_fees,
            "total_sell_fees": self.total_sell_fees,
        }


class RiskManager:
    """
    Manajer Risiko Portofolio Saham Indonesia.
    
    Attributes:
        positions (dict): Map dari symbol -> objek Position aktif.
        trade_history (list): Riwayat seluruh transaksi jual yang telah selesai.
        daily_loss_limit_pct (float): Batas toleransi kerugian harian (default 5%).
        last_check_date (str): Tanggal pengecekan harian terakhir.
    """

    def __init__(self):
        """Inisialisasi RiskManager dan memuat riwayat transaksi dari file JSON."""
        self.positions = {}
        self.trade_history = self._load_history()
        self.daily_loss_limit_pct = MAX_DAILY_LOSS_PCT
        self.last_check_date = datetime.now().strftime("%Y-%m-%d")

    def _load_history(self):
        """Memuat riwayat transaksi dari file JSON lokal."""
        if os.path.exists(TRADE_HISTORY_FILE):
            try:
                with open(TRADE_HISTORY_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_history(self):
        """Menyimpan riwayat transaksi ke file JSON lokal."""
        try:
            with open(TRADE_HISTORY_FILE, "w") as f:
                json.dump(self.trade_history, f, indent=2)
        except IOError as e:
            logger.error(f"Error saving trade history: {e}")

    def sync_positions_from_exchange(self, exchange, trader):
        """
        Melakukan sinkronisasi posisi kepemilikan saham riil dari browser automation Ajaib.
        
        Args:
            exchange (StockExchange): Instance data pasar Yahoo Finance.
            trader (AjaibTrader): Instance automasi browser Ajaib.
        """
        portfolio = trader.get_portfolio()
        if not portfolio:
            return

        cash = portfolio.get("cash", 0)
        stocks = portfolio.get("stocks", [])

        for stock_text in stocks:
            try:
                lines = stock_text.strip().split("\n")
                if len(lines) >= 2:
                    code = lines[0].strip()
                    symbol = f"{code}.JK"
                    for line in lines:
                        if "lot" in line.lower():
                            lots = int("".join(filter(str.isdigit, line)))
                            if symbol not in self.positions or self.positions[symbol].status != "open":
                                ticker = exchange.fetch_ticker(symbol)
                                if ticker and ticker.get("last"):
                                    entry_price = ticker["last"]
                                    self.positions[symbol] = Position(symbol, entry_price, lots, code)
                                    logger.info(f"Loaded position: {symbol} lots={lots} entry={entry_price:,.0f}")
            except Exception as e:
                logger.warning(f"Error parsing stock: {e}")

    def get_daily_pnl(self):
        """
        Menghitung total profit/loss terealisasi hari ini (WIB).
        
        Returns:
            float: Akumulasi PnL hari ini dalam IDR.
        """
        today = now_jakarta().strftime("%Y-%m-%d")
        pnl = 0
        for t in self.trade_history:
            exit_time = t.get("exit_time", "")
            if exit_time.startswith(today):
                pnl += t.get("pnl_amount", 0)
        return pnl

    def is_daily_loss_limit_reached(self, balance):
        """
        Memeriksa apakah kerugian hari ini telah menyentuh batas maksimal (5%).
        
        Args:
            balance (float): Total modal/saldo kas.
            
        Returns:
            bool: True jika batas kerugian tercapai, False jika masih aman.
        """
        daily_pnl = self.get_daily_pnl()
        if daily_pnl >= 0:
            return False
        loss_pct = abs(daily_pnl) / balance if balance > 0 else 0
        return loss_pct >= self.daily_loss_limit_pct

    def get_open_positions_count(self):
        """
        Menghitung jumlah posisi saham yang sedang aktif terbuka.
        
        Returns:
            int: Jumlah open positions.
        """
        return sum(1 for p in self.positions.values() if p.status == "open")

    def can_open_position(self):
        """
        Mengecek apakah kuota posisi terbuka masih tersedia (< MAX_OPEN_POSITIONS).
        
        Returns:
            bool: True jika masih boleh buka posisi baru.
        """
        return self.get_open_positions_count() < MAX_OPEN_POSITIONS

    def calculate_lots(self, balance, current_price, is_primary=True):
        """
        Menghitung ukuran order dalam satuan Lot berdasarkan modal, harga, dan manajemen risiko.
        
        Formula:
        - Primary stock: 2% risk allocation
        - Secondary stock: 1% risk allocation
        - Dikonversi ke lot bulat (1 lot = 100 lembar) dengan memperhitungkan biaya beli 0.14%.
        
        Args:
            balance (float): Saldo kas IDR.
            current_price (float): Harga per lembar saham.
            is_primary (bool, optional): Apakah saham prioritas utama.
            
        Returns:
            int: Jumlah lot yang disarankan.
        """
        if is_primary:
            risk_amount = balance * RISK_PER_TRADE
        else:
            risk_amount = balance * (RISK_PER_TRADE * 0.5)

        position_value = min(POSITION_SIZE_IDR, risk_amount)
        min_value = MIN_ORDER_IDR * 1.5

        if position_value < min_value:
            if balance >= MIN_ORDER_IDR:
                position_value = balance * 0.95
            else:
                return 0

        cost_per_lot = LOT_SIZE * current_price * (1 + BUY_TOTAL_FEE_PCT)
        lots = int(position_value // cost_per_lot)
        return max(1, lots)

    def add_position(self, symbol, entry_price, lots, code=None):
        """
        Mencatat posisi saham baru ke dalam portofolio aktif.
        
        Args:
            symbol (str): Simbol saham Yahoo Finance.
            entry_price (float): Harga beli per lembar.
            lots (int): Jumlah lot.
            code (str, optional): Kode singkat saham.
            
        Returns:
            Position: Objek posisi yang baru dibuat.
        """
        position = Position(symbol, entry_price, lots, code)
        self.positions[symbol] = position
        logger.info(
            f"Position opened: {symbol} entry={entry_price:,.0f} lots={lots} "
            f"SL={position.stop_loss:,.0f} TP={position.take_profit:,.0f}"
        )
        return position

    def close_position(self, symbol, exit_price):
        """
        Menutup posisi saham, menghitung biaya fee beli & jual aktual, dan mencatat rekam jejak trade ke history.
        
        Args:
            symbol (str): Simbol saham.
            exit_price (float): Harga jual per lembar.
            
        Returns:
            dict or None: Record data trade lengkap yang mencakup Gross PnL, Fees, dan Net PnL.
        """
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos.status = "closed"

            buy_value = pos.entry_price_market * pos.initial_lots * LOT_SIZE
            buy_fees = buy_value * BUY_TOTAL_FEE_PCT
            pos.total_buy_fees = buy_fees
            pos.total_buy_cost = buy_value + buy_fees

            sell_value = exit_price * pos.lots * LOT_SIZE
            sell_fees = sell_value * SELL_TOTAL_FEE_PCT
            pos.total_sell_fees = sell_fees
            pos.total_sell_proceeds = sell_value - sell_fees

            gross_pnl = (exit_price - pos.entry_price_market) * pos.lots * LOT_SIZE
            net_pnl = pos.total_sell_proceeds - (pos.entry_price * pos.lots * LOT_SIZE)
            total_fees = (buy_fees * pos.lots / pos.initial_lots) + sell_fees

            pnl_pct = (net_pnl / (pos.entry_price * pos.lots * LOT_SIZE)) * 100

            trade_record = {
                "symbol": symbol,
                "code": pos.code,
                "entry_price": pos.entry_price,
                "entry_price_market": pos.entry_price_market,
                "exit_price": exit_price,
                "lots": pos.lots,
                "shares": pos.lots * LOT_SIZE,
                "buy_fees": round(buy_fees * pos.lots / pos.initial_lots, 2),
                "sell_fees": round(sell_fees, 2),
                "total_fees": round(total_fees, 2),
                "gross_pnl": round(gross_pnl, 2),
                "pnl_amount": round(net_pnl, 2),
                "pnl_pct": round(pnl_pct, 4),
                "entry_time": pos.entry_time,
                "exit_time": now_jakarta().isoformat(),
            }

            self.trade_history.append(trade_record)
            self._save_history()

            logger.info(
                f"Position closed: {symbol} exit={exit_price:,.0f} | "
                f"Gross PnL={gross_pnl:+,.0f} | Fees={total_fees:,.0f} | "
                f"Net PnL={net_pnl:+,.0f} ({pnl_pct:+.2f}%)"
            )
            return trade_record
        return None

    def check_stop_loss_take_profit(self, symbol, current_price):
        """
        Mengecek apakah harga terkini melanggar Stop Loss atau mencapai Take Profit.
        
        Args:
            symbol (str): Simbol saham.
            current_price (float): Harga terkini di pasar.
            
        Returns:
            str or None: 'stop_loss', 'take_profit', atau None.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        if pos.status != "open":
            return None

        if current_price <= pos.stop_loss:
            return "stop_loss"
        elif current_price >= pos.take_profit:
            return "take_profit"

        return None

    def get_total_pnl(self):
        """
        Menghitung total profit/loss bersih kumulatif dari seluruh riwayat trading.
        
        Returns:
            float: Grand total Net PnL dalam IDR.
        """
        return sum(t.get("pnl_amount", 0) for t in self.trade_history)

    def get_win_rate(self):
        """
        Menghitung rasio kemenangan (Win Rate persentase) dari riwayat transaksi yang ditutup.
        
        Returns:
            float: Win rate dalam persen (0 - 100%).
        """
        if not self.trade_history:
            return 0
        wins = sum(1 for t in self.trade_history if t.get("pnl_amount", 0) > 0)
        return round(wins / len(self.trade_history) * 100, 2)

    def get_unrealized_pnl(self, exchange):
        """
        Menghitung total floating Profit/Loss bersih untuk seluruh posisi saham yang sedang dibuka.
        
        Args:
            exchange (StockExchange): Instance data exchange.
            
        Returns:
            float: Total floating PnL bersih dalam IDR.
        """
        total_unrealized = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    current_price = ticker["last"]
                    unrealized = pos.unrealized_pnl(current_price)
                    total_unrealized += unrealized
        return round(total_unrealized, 2)

    def get_total_stock_value(self, exchange):
        """
        Menghitung total nilai pasar aset saham yang sedang dipegang saat ini.
        
        Args:
            exchange (StockExchange): Instance data exchange.
            
        Returns:
            float: Nilai pasar bruto saham.
        """
        total = 0
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    total += ticker["last"] * pos.lots * LOT_SIZE
        return total

    def get_position_details(self, exchange):
        """
        Menghasilkan dictionary rincian mendalam setiap posisi aktif untuk laporan Telegram & bot dashboard.
        
        Args:
            exchange (StockExchange): Instance data exchange.
            
        Returns:
            dict: Map dari symbol -> detail posisi (harga beli, harga saat ini, PnL bersih, estimasi fee jual, break-even).
        """
        details = {}
        for symbol, pos in self.positions.items():
            if pos.status == "open":
                ticker = exchange.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    current_price = ticker["last"]
                    net_pnl = pos.unrealized_pnl(current_price)
                    pnl_pct = pos.unrealized_pnl_pct(current_price)
                    est_sell_fees = current_price * pos.lots * LOT_SIZE * SELL_TOTAL_FEE_PCT
                    details[symbol] = {
                        "code": pos.code,
                        "lots": pos.lots,
                        "shares": pos.lots * LOT_SIZE,
                        "entry_price": pos.entry_price,
                        "entry_price_market": pos.entry_price_market,
                        "current_price": current_price,
                        "value": current_price * pos.lots * LOT_SIZE,
                        "net_pnl": net_pnl,
                        "pnl": net_pnl,
                        "pnl_pct": pnl_pct,
                        "est_sell_fees": est_sell_fees,
                        "break_even": pos.break_even_price,
                    }
        return details


class TradingStrategy:
    """
    Evaluator Strategi Trading Saham Indonesia (IDX Engine).
    
    Menentukan keputusan eksekusi order (BUY, DCA, PARTIAL SELL, CLOSE, HOLD)
    berdasarkan sinyal teknikal, filter RSI, risk-to-reward ratio, dan batas risiko.
    
    Attributes:
        analyzer (MarketAnalyzer): Engine analisis teknikal.
        risk_manager (RiskManager): Pengelola risiko dan portofolio.
        min_confidence (float): Ambang batas minimum keyakinan sinyal (default 0.70).
        rsi_overbought (float): Batas overbought (default 70).
        rsi_entry_max (float): Batas maksimal RSI untuk entry buy (default 40).
        min_risk_reward (float): Rasio minimal reward vs risk (default 2.0).
        min_win_rate (float): Batas minimum win rate historis (default 40%).
    """

    def __init__(self, analyzer, risk_manager):
        """
        Inisialisasi TradingStrategy.
        
        Args:
            analyzer (MarketAnalyzer): Engine analisis teknikal.
            risk_manager (RiskManager): Pengelola risiko.
        """
        self.analyzer = analyzer
        self.risk_manager = risk_manager
        self.min_confidence = 0.70
        self.rsi_overbought = 70
        self.rsi_entry_max = 40
        self.min_risk_reward = 2.0
        self.min_win_rate = 40.0

    def evaluate(self, symbol, ohlcv, balance, current_price, is_primary=True):
        """
        Mengevaluasi kondisi pasar dan portofolio untuk menghasilkan instruksi trading yang tepat.
        
        Logika Evaluasi:
        1. Jika saham sudah dipegang:
           - Update trailing stop (+5% dari puncak tertinggi).
           - Cek apakah trailing stop tertembus -> action 'close'.
           - Cek Take Profit 1 (+4%) -> action 'partial_sell' (50% lot).
           - Cek Take Profit 2 (+8%) -> action 'close'.
           - Cek DCA (-3% atau -6%) -> action 'buy' (averaging down).
           - Smart exit: RSI > 70 atau RSI > 65 dengan MACD bearish -> action 'close'.
        2. Jika sinyal BUY baru terdeteksi:
           - Validasi RSI <= 40 (tidak membeli di pucuk).
           - Validasi Win Rate >= 40% (setelah minimal 5 trade).
           - Validasi Risk/Reward >= 2.0.
           - Validasi ketersediaan saldo dan kuota posisi terbuka.
           - Hitung lot order -> action 'buy'.
        
        Args:
            symbol (str): Simbol saham (misal 'BBCA.JK').
            ohlcv (list): Data candlestick saham.
            balance (float): Saldo kas IDR tersedia.
            current_price (float): Harga saham saat ini.
            is_primary (bool, optional): Apakah saham termasuk koin/saham prioritas utama.
            
        Returns:
            dict: Keputusan aksi trading {'action': 'buy'/'partial_sell'/'close'/'hold', 'lots': int, ...}.
        """
        analysis = self.analyzer.analyze(ohlcv, symbol=symbol)
        signal = analysis["signal"]
        confidence = analysis["confidence"]
        indicators = analysis.get("indicators", {})
        rsi = indicators.get("rsi", 50)
        atr = indicators.get("atr", 0)

        logger.info(
            f"[{symbol}] Signal: {signal.upper()} | Confidence: {confidence:.1%} | "
            f"RSI: {rsi} | Price: {current_price:,.0f}"
        )

        # 1. Pengecekan posisi yang sudah berjalan (Open Position Management)
        if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
            pos = self.risk_manager.positions[symbol]

            # Trailing stop update
            if pos.update_trailing_stop(current_price):
                logger.info(
                    f"[{symbol}] Trailing stop updated: {pos.stop_loss:,.0f} "
                    f"(highest: {pos.highest_price:,.0f})"
                )

            # Eksekusi trailing stop
            if pos.check_trailing_stop(current_price):
                return {
                    "action": "close",
                    "reason": f"trailing_stop (peak: {pos.highest_price:,.0f})",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            # Eksekusi Partial Take Profit 1 (+4%)
            if pos.should_partial_sell(current_price):
                partial_lots = pos.partial_sell_lots()
                pos.partial_sell_count += 1
                pos.lots -= partial_lots
                return {
                    "action": "partial_sell",
                    "reason": f"tp1_hit (+4% @ {pos.get_tp1_price():,.0f})",
                    "analysis": analysis,
                    "lots": partial_lots,
                }

            # Eksekusi Full Take Profit 2 (+8%)
            if pos.should_full_sell(current_price):
                return {
                    "action": "close",
                    "reason": f"tp2_hit (+8% @ {pos.get_tp2_price():,.0f})",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            # Eksekusi Dollar Cost Averaging (DCA)
            if pos.should_dca(current_price):
                dca_lots = pos.dca_lots()
                dca_cost = dca_lots * LOT_SIZE * current_price
                dca_fees = dca_cost * BUY_TOTAL_FEE_PCT
                total_dca_cost = dca_cost + dca_fees
                if balance >= total_dca_cost:
                    pos.dca_count += 1
                    pos.lots += dca_lots
                    pos.shares = pos.lots * LOT_SIZE
                    total_cost_with_fees = pos.entry_price * (pos.lots - dca_lots) * LOT_SIZE + current_price * (1 + BUY_TOTAL_FEE_PCT) * dca_lots * LOT_SIZE
                    pos.entry_price = total_cost_with_fees / (pos.lots * LOT_SIZE)
                    pos.break_even_price = pos.entry_price * (1 + SELL_TOTAL_FEE_PCT)
                    return {
                        "action": "buy",
                        "lots": dca_lots,
                        "reason": f"dca_{pos.dca_count} (price dropped {pos.dca_count * 3}%)",
                        "analysis": analysis,
                        "is_dca": True,
                    }
                else:
                    logger.info(f"[{symbol}] DCA skipped: insufficient balance")

            # Eksekusi Take Profit standar
            if current_price >= pos.take_profit:
                return {
                    "action": "close",
                    "reason": "take_profit",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            # Smart exit jika RSI jenuh beli
            if rsi >= self.rsi_overbought and confidence > 0.5:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f} overbought)",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

            # Smart exit jika momentum MACD berbalik bearish
            macd_hist = indicators.get("macd_histogram", 0)
            if rsi > 65 and macd_hist < 0:
                return {
                    "action": "close",
                    "reason": f"smart_sell (RSI: {rsi:.1f}, MACD bearish)",
                    "analysis": analysis,
                    "lots": pos.lots,
                }

        # 2. Pengecekan sinyal baru untuk Entry Beli
        if signal == "hold" or confidence < self.min_confidence:
            return {"action": "hold", "analysis": analysis}

        if signal == "buy":
            if rsi > self.rsi_entry_max:
                logger.info(f"[{symbol}] Skip buy: RSI {rsi} > {self.rsi_entry_max}")
                return {"action": "hold", "reason": "rsi_too_high", "analysis": analysis}

            win_rate = self.risk_manager.get_win_rate()
            if len(self.risk_manager.trade_history) >= 5 and win_rate < self.min_win_rate:
                logger.info(f"[{symbol}] Skip buy: win rate {win_rate}% < {self.min_win_rate}%")
                return {"action": "hold", "reason": "low_win_rate", "analysis": analysis}

            risk = current_price * STOP_LOSS_PCT
            reward = current_price * TAKE_PROFIT_PCT
            rr_ratio = reward / risk if risk > 0 else 0
            if rr_ratio < self.min_risk_reward:
                logger.info(f"[{symbol}] Skip buy: R/R {rr_ratio:.1f} < {self.min_risk_reward}")
                return {"action": "hold", "reason": "poor_risk_reward", "analysis": analysis}

            min_order = MIN_ORDER_IDR * 1.5
            can_afford = balance >= min_order

            if not can_afford:
                logger.info(f"[{symbol}] Cannot afford, balance {balance:,.0f} < {min_order:,.0f}")
                return {"action": "hold", "reason": "insufficient_balance", "analysis": analysis}

            if symbol in self.risk_manager.positions and self.risk_manager.positions[symbol].status == "open":
                return {"action": "hold", "analysis": analysis}

            if not self.risk_manager.can_open_position():
                logger.info(f"Max positions reached ({MAX_OPEN_POSITIONS})")
                return {"action": "hold", "analysis": analysis}

            if self.risk_manager.is_daily_loss_limit_reached(balance):
                logger.info("Daily loss limit reached")
                return {"action": "hold", "reason": "daily_loss_limit", "analysis": analysis}

            lots = self.risk_manager.calculate_lots(balance, current_price, is_primary=is_primary)
            return {
                "action": "buy",
                "lots": lots,
                "analysis": analysis,
            }

        return {"action": "hold", "analysis": analysis}

