"""Example 06 — Account info, portfolio summary, positions, buying power.

This example demonstrates:
- Fetching client account information
- Portfolio summary (cash, stocks, P&L)
- Open stock positions
- Open fund positions
- Buying power for a specific stock

Prerequisites:
- Set EFG_PARTNER_ID, EFG_PARTNER_SECRET, EFG_TRADING_UUID in your environment
"""

from younit import Client

with Client() as client:
    # Account information
    info = client.account_info()
    print("=== Account Info ===")
    print(f"Account Code:  {info.account_code}")
    print(f"Name:          {info.client_name}")
    print(f"Email:         {info.email}")
    print(f"Mobile:        {info.mobile}")
    print(f"Investor Code: {info.investor_code}")
    print(f"Live Datafeed: {info.is_live_datafeed}")
    print(f"Global Market: {info.is_global_market_allowed}")
    print()

    # Portfolio summary
    summary = client.portfolio()
    print("=== Portfolio Summary ===")
    print(f"  Client ID:          {summary.client_id}")
    print(f"  Market ID:          {summary.market_id}")
    print(f"  Currency:           {summary.currency}")
    print(f"  Total Cash:         {summary.total_cash:.2f}")
    print(f"  Total Stocks:       {summary.total_stocks:.2f}")
    print(f"  Total Balance:      {summary.total_balance:.2f}")
    print(f"  Realized P&L:       {summary.realized_profit:+.2f}")
    print(f"  Unrealized P&L:     {summary.unrealized_profit:+.2f}  ({summary.unrealized_profit_pct:+.2f}%)")
    print(f"  Profit/Loss:        {summary.profit_or_loss:+.2f}")
    print()

    # Open positions, reliably split into stocks vs. funds (GetStocksPortfolio
    # mixes both together as of 2026-09-09, with is_fund/symbol unreliable on
    # fund rows — see Client.positions_split()'s docstring)
    stock_positions, fund_positions = client.positions_split()
    print(f"=== Open Stock Positions ({len(stock_positions)}) ===")
    if not stock_positions:
        print("  No open positions.")
    else:
        for pos in stock_positions:
            print(
                f"  [{pos.stock_id}] {pos.symbol or pos.name:<8}"
                f"  name={pos.name}"
                f"  qty={pos.quantity:,}"
                f"  avail_sell={pos.qty_valid_for_sale:,}"
                f"  avg={pos.average_price:.4f}"
                f"  mkt={pos.market_price:.4f}"
                f"  value={pos.market_value:.2f}"
                f"  total={pos.total_value:.2f}"
                f"  pnl={pos.unrealized_pnl:+.2f} ({pos.unrealized_pnl_pct:+.2f}%)"
                f"  realized={pos.realized_pnl:+.2f}"
                f"  ccy={pos.currency}"
                f"  fund={pos.is_fund}"
                f"  suspended={pos.is_suspended}"
            )
    print()

    # symbol is confirmed garbled ("'") for fund rows — use name instead
    print(f"=== Open Fund Positions ({len(fund_positions)}) ===")
    if not fund_positions:
        print("  No open fund positions.")
    else:
        for pos in fund_positions:
            print(
                f"  [{pos.stock_id}] {pos.name:<8}"
                f"  qty={pos.quantity:,}"
                f"  avail_sell={pos.qty_valid_for_sale:,}"
                f"  avg={pos.average_price:.4f}"
                f"  mkt={pos.market_price:.4f}"
                f"  value={pos.market_value:.2f}"
                f"  total={pos.total_value:.2f}"
                f"  pnl={pos.unrealized_pnl:+.2f} ({pos.unrealized_pnl_pct:+.2f}%)"
                f"  realized={pos.realized_pnl:+.2f}"
                f"  ccy={pos.currency}"
            )
    print()

