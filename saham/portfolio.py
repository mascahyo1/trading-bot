import os
import sys
import logging
import re
from config import now_jakarta, format_datetime, LOT_SIZE, SELL_TOTAL_FEE_PCT

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_portfolio_from_ajaib(trader):
    """Get portfolio data from Ajaib via Playwright"""
    try:
        portfolio = trader.get_portfolio()
        if not portfolio:
            return None
        return portfolio
    except Exception as e:
        logger.error(f"Error fetching Ajaib portfolio: {e}")
        return None


def format_portfolio_report():
    """Format portfolio report from Ajaib"""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from ajaib_trader import AjaibTrader
        trader = AjaibTrader()
        portfolio = get_portfolio_from_ajaib(trader)

        if not portfolio:
            return "Error: Could not fetch portfolio from Ajaib"

        lines = [
            f"<b>📊 PORTFOLIO REPORT</b>",
            f"⏰ {format_datetime()}",
            f"",
        ]

        cash = portfolio.get("cash", 0)
        lines.append(f"<b>💰 Cash: {cash:,.0f} IDR</b>")

        stocks = portfolio.get("stocks", [])
        if stocks:
            lines.append(f"\n<b>📈 STOCKS:</b>")
            for stock_text in stocks:
                lines.append(f"  {stock_text}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_asset_breakdown():
    """Get per-stock asset breakdown with grand total - sends via Telegram"""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        from exchange import StockExchange
        from ajaib_trader import AjaibTrader

        exchange = StockExchange()
        trader = AjaibTrader()

        portfolio = get_portfolio_from_ajaib(trader)
        if not portfolio:
            return "Error: Could not fetch portfolio from Ajaib"

        cash = portfolio.get("cash", 0)
        stocks_raw = portfolio.get("stocks", [])

        lines = [
            f"<b>📊 ASET PER SAHAM</b>",
            f"⏰ {format_datetime()}",
            f"",
            f"<b>💰 CASH: {cash:,.0f} IDR</b>",
            f"",
        ]

        stock_assets = []
        total_stock_value = 0

        for stock_data in stocks_raw:
            try:
                if isinstance(stock_data, str):
                    text_lines = stock_data.strip().split("\n")
                    if len(text_lines) < 2:
                        continue
                    code = text_lines[0].strip()
                    symbol = f"{code}.JK"
                    lots = 0
                    for line in text_lines:
                        if "lot" in line.lower():
                            match = re.search(r'(\d+)\s*lot', line, re.IGNORECASE)
                            if match:
                                lots = int(match.group(1))
                elif isinstance(stock_data, dict):
                    code = stock_data.get("code", "")
                    symbol = f"{code}.JK"
                    lots = stock_data.get("lots", 0)
                else:
                    continue

                if lots == 0:
                    continue

                ticker = exchange.fetch_ticker(symbol)
                if not ticker or not ticker.get("last"):
                    continue

                current_price = ticker["last"]
                shares = lots * LOT_SIZE
                value = shares * current_price
                total_stock_value += value

                stock_assets.append({
                    "code": code,
                    "lots": lots,
                    "shares": shares,
                    "price": current_price,
                    "value": value,
                })
            except Exception as e:
                logger.warning(f"Error parsing stock: {e}")

        if stock_assets:
            stock_assets.sort(key=lambda x: x["value"], reverse=True)

            lines.append("<b>📈 DETAIL PER SAHAM:</b>")
            lines.append("")

            for asset in stock_assets:
                lines.append(f"<b>{asset['code']}</b>")
                lines.append(f"   Lot: {asset['lots']} ({asset['shares']} lembar)")
                lines.append(f"   Harga: {asset['price']:,.0f} IDR")
                lines.append(f"   <b>Total: {asset['value']:,.0f} IDR</b>")
                lines.append("")

        grand_total = cash + total_stock_value
        lines.append(f"{'─' * 25}")
        lines.append(f"<b>💵 Total Saham: {total_stock_value:,.0f} IDR</b>")
        lines.append(f"<b>💰 Total Cash: {cash:,.0f} IDR</b>")
        lines.append(f"")
        lines.append(f"<b>🏦 GRAND TOTAL: {grand_total:,.0f} IDR</b>")
        lines.append(f"")
        lines.append(f"<i>Catatan: Belum dipotong biaya jual (~{SELL_TOTAL_FEE_PCT*100:.2f}%)</i>")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def get_portfolio_summary(risk_manager, exchange, cash_balance):
    """Get portfolio summary from internal tracking + live prices"""
    try:
        position_details = risk_manager.get_position_details(exchange)
        total_stock_value = sum(d["value"] for d in position_details.values())
        grand_total = cash_balance + total_stock_value
        total_est_sell_fees = sum(d.get("est_sell_fees", 0) for d in position_details.values())

        lines = [
            f"<b>📊 PORTFOLIO SUMMARY</b>",
            f"⏰ {format_datetime()}",
            f"",
        ]

        if position_details:
            sorted_positions = sorted(
                position_details.items(),
                key=lambda x: x[1]["value"],
                reverse=True
            )

            for symbol, detail in sorted_positions:
                pnl_sign = "+" if detail["pnl"] >= 0 else ""
                pnl_emoji = "🟢" if detail["pnl"] >= 0 else "🔴"
                est_sell_fees = detail.get("est_sell_fees", 0)
                lines.append(f"{pnl_emoji} <b>{detail['code']}</b>")
                lines.append(f"   Lot: {detail['lots']} ({detail['shares']} lembar)")
                lines.append(f"   Value: {detail['value']:,.0f} IDR")
                lines.append(f"   PnL (net): {pnl_sign}{detail['pnl']:,.0f} ({pnl_sign}{detail['pnl_pct']:.2f}%)")
                lines.append(f"   Est. Biaya Jual: {est_sell_fees:,.0f} IDR")
                lines.append("")

        lines.append(f"<b>💵 Total Saham (gross): {total_stock_value:,.0f} IDR</b>")
        lines.append(f"   Est. Biaya Jual: {total_est_sell_fees:,.0f} IDR")
        lines.append(f"<b>💰 Cash: {cash_balance:,.0f} IDR</b>")
        lines.append(f"<b>🏦 GRAND TOTAL (net): {grand_total - total_est_sell_fees:,.0f} IDR</b>")

        return "\n".join(lines), grand_total, position_details
    except Exception as e:
        logger.error(f"Portfolio summary error: {e}")
        return f"Error: {e}", 0, {}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(get_asset_breakdown())
