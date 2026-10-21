"""SMA crossover backtest on one EGX stock using the younit SDK.

Rules: long-only, one position, signals at the close, execution at the next
trading day's open, commission charged on every buy and sell. Any position
still open on the last bar is closed at the final close (commission applies),
and the buy-and-hold benchmark is treated the same way.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from younit import ChartPeriod, Client

TRADING_DAYS = 252
SPLIT_THRESHOLD = 0.25


def fetch_prices(symbol: str, date_from: str, date_to: str) -> pd.DataFrame:
    with Client() as client:
        candles = client.historical_prices(
            symbol,
            period=ChartPeriod.DAY,
            date_from=date_from,
            date_to=date_to,
        )
    rows = [
        {
            "date": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles
        if c.timestamp is not None
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        raise SystemExit(f"No data returned for {symbol}")
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_convert("Africa/Cairo").dt.tz_localize(None).dt.normalize()
    return df


def clean_prices(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report: dict = {"rows_raw": len(df)}
    df = df.sort_values("date")
    dup = int(df.duplicated("date").sum())
    df = df.drop_duplicates("date", keep="last")
    report["duplicate_dates_dropped"] = dup

    price_cols = ["open", "high", "low", "close"]
    bad = (df[price_cols] <= 0).any(axis=1) | df[price_cols].isna().any(axis=1)
    report["non_positive_rows_dropped"] = int(bad.sum())
    df = df[~bad].reset_index(drop=True)

    jumps = df["close"].pct_change()
    flagged = df.loc[jumps.abs() > SPLIT_THRESHOLD, ["date", "close"]].copy()
    flagged["move_pct"] = jumps[flagged.index] * 100
    report["flagged_moves"] = flagged
    report["rows_clean"] = len(df)
    return df.reset_index(drop=True), report


@dataclass
class Result:
    equity: pd.Series
    trades: pd.DataFrame
    commission: float
    buys: pd.DataFrame
    sells: pd.DataFrame


def simulate(df: pd.DataFrame, fast: int, slow: int, cash: float, comm: float) -> tuple[Result, Result, pd.DataFrame]:
    if fast >= slow:
        raise ValueError("fast SMA length must be smaller than slow SMA length")
    df = df.copy()
    df["sma_fast"] = df["close"].rolling(fast).mean()
    df["sma_slow"] = df["close"].rolling(slow).mean()

    above = (df["sma_fast"] > df["sma_slow"]).to_numpy()
    valid = (df["sma_fast"].notna() & df["sma_slow"].notna()).to_numpy()
    n = len(df)
    start = int(np.argmax(valid)) if valid.any() else n
    if start + 2 >= n:
        raise SystemExit("Not enough data for the requested SMA lengths")

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    # Strategy
    c = cash
    shares = 0
    entry_cost = 0.0
    entry_date = None
    entry_px = 0.0
    comm_paid = 0.0
    pending = None
    equity = np.full(n, np.nan)
    trades, buys, sells = [], [], []

    def do_sell(i: int, px: float) -> None:
        nonlocal c, shares, comm_paid
        proceeds = shares * px
        fee = proceeds * comm
        c += proceeds - fee
        comm_paid += fee
        trades.append(
            {
                "entry_date": entry_date,
                "exit_date": df["date"].iloc[i],
                "entry_px": entry_px,
                "exit_px": px,
                "shares": shares,
                "pnl": proceeds - fee - entry_cost,
            }
        )
        sells.append({"date": df["date"].iloc[i], "px": px})
        shares = 0

    for i in range(start, n):
        if pending is not None:
            if pending == "buy" and shares == 0:
                px = opens[i]
                qty = math.floor(c / (px * (1 + comm)))
                if qty > 0:
                    cost = qty * px
                    fee = cost * comm
                    c -= cost + fee
                    comm_paid += fee
                    shares = qty
                    entry_cost = cost + fee
                    entry_date = df["date"].iloc[i]
                    entry_px = px
                    buys.append({"date": entry_date, "px": px})
            elif pending == "sell" and shares > 0:
                do_sell(i, opens[i])
            pending = None

        if i == n - 1 and shares > 0:
            do_sell(i, closes[i])
        equity[i] = c + shares * closes[i]

        if i > start:
            cross_up = above[i] and not above[i - 1]
            cross_dn = (not above[i]) and above[i - 1]
            if cross_up:
                pending = "buy"
            elif cross_dn:
                pending = "sell"

    strat = Result(
        equity=pd.Series(equity[start:], index=df["date"].iloc[start:], name="Strategy"),
        trades=pd.DataFrame(trades),
        commission=comm_paid,
        buys=pd.DataFrame(buys),
        sells=pd.DataFrame(sells),
    )

    # Buy and hold: same start, buy at the first open after the first valid signal bar
    bh_px = opens[start + 1]
    qty = math.floor(cash / (bh_px * (1 + comm)))
    bh_buy_fee = qty * bh_px * comm
    bh_cash = cash - qty * bh_px - bh_buy_fee
    bh_eq = np.full(n, np.nan)
    bh_eq[start] = cash
    for i in range(start + 1, n):
        bh_eq[i] = bh_cash + qty * closes[i]
    bh_sell_fee = qty * closes[-1] * comm
    bh_eq[-1] -= bh_sell_fee
    bh_trades = pd.DataFrame(
        [
            {
                "entry_date": df["date"].iloc[start + 1],
                "exit_date": df["date"].iloc[-1],
                "entry_px": bh_px,
                "exit_px": closes[-1],
                "shares": qty,
                "pnl": bh_eq[-1] - cash,
            }
        ]
    )
    bh = Result(
        equity=pd.Series(bh_eq[start:], index=df["date"].iloc[start:], name="Buy & hold"),
        trades=bh_trades,
        commission=bh_buy_fee + bh_sell_fee,
        buys=pd.DataFrame(),
        sells=pd.DataFrame(),
    )
    return strat, bh, df


def metrics(res: Result, rf: float) -> dict:
    eq = res.equity
    rets = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan")
    vol = rets.std(ddof=1) * math.sqrt(TRADING_DAYS)
    dd = (eq / eq.cummax() - 1).min()
    rf_d = rf / TRADING_DAYS
    excess = rets - rf_d
    sharpe = excess.mean() / rets.std(ddof=1) * math.sqrt(TRADING_DAYS) if rets.std(ddof=1) > 0 else float("nan")
    downside = math.sqrt((np.minimum(excess, 0) ** 2).mean())
    sortino = excess.mean() / downside * math.sqrt(TRADING_DAYS) if downside > 0 else float("nan")
    t = res.trades
    win = float((t["pnl"] > 0).mean()) if len(t) else float("nan")
    return {
        "Total return": f"{total:.2%}",
        "CAGR": f"{cagr:.2%}",
        "Final equity (EGP)": f"{eq.iloc[-1]:,.2f}",
        "Trades (round trips)": str(len(t)),
        "Win rate": f"{win:.1%}" if len(t) else "n/a",
        "Total commission (EGP)": f"{res.commission:,.2f}",
        "Annualised volatility": f"{vol:.2%}",
        "Max drawdown": f"{dd:.2%}",
        "Sharpe": f"{sharpe:.2f}",
        "Sortino": f"{sortino:.2f}",
    }


def plot(df: pd.DataFrame, strat: Result, bh: Result, symbol: str, fast: int, slow: int, path: str) -> None:
    d = df[df["date"] >= strat.equity.index[0]]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    ax1.plot(d["date"], d["close"], color="black", lw=1, label="Close")
    ax1.plot(d["date"], d["sma_fast"].loc[d.index], color="tab:blue", lw=1, label=f"SMA {fast}")
    ax1.plot(d["date"], d["sma_slow"].loc[d.index], color="tab:orange", lw=1, label=f"SMA {slow}")
    if len(strat.buys):
        ax1.scatter(strat.buys["date"], strat.buys["px"], marker="^", color="green", s=70, zorder=5, label="Buy")
    if len(strat.sells):
        ax1.scatter(strat.sells["date"], strat.sells["px"], marker="v", color="red", s=70, zorder=5, label="Sell")
    ax1.set_title(f"{symbol} - SMA {fast}/{slow} crossover")
    ax1.set_ylabel("Price (EGP)")
    ax1.legend(loc="upper left")
    ax1.grid(alpha=0.3)

    ax2.plot(strat.equity.index, strat.equity, label="Strategy", color="tab:blue")
    ax2.plot(bh.equity.index, bh.equity, label="Buy & hold", color="tab:gray")
    ax2.set_ylabel("Equity (EGP)")
    ax2.legend(loc="upper left")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def table(rows: list[str], strat: dict, bh: dict) -> str:
    out = ["| Metric | Strategy | Buy & hold |", "|---|---|---|"]
    out += [f"| {r} | {strat[r]} | {bh[r]} |" for r in rows]
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default="COMI")
    p.add_argument("--fast", type=int, default=20)
    p.add_argument("--slow", type=int, default=50)
    p.add_argument("--rf", type=float, default=0.0, help="annual risk-free rate, e.g. 0.25")
    p.add_argument("--cash", type=float, default=100_000.0)
    p.add_argument("--commission", type=float, default=0.003)
    p.add_argument("--date-from", default="2010-01-01")
    p.add_argument("--date-to", default=str(date.today()))
    p.add_argument("--out", default="equity.png")
    args = p.parse_args()

    raw = fetch_prices(args.symbol, args.date_from, args.date_to)
    df, rep = clean_prices(raw)

    print(f"## Data quality: {args.symbol}")
    print(f"- Raw rows: {rep['rows_raw']}, clean rows: {rep['rows_clean']}")
    print(f"- Date range: {df['date'].iloc[0].date()} to {df['date'].iloc[-1].date()}")
    print(f"- Duplicate dates dropped: {rep['duplicate_dates_dropped']}")
    print(f"- Zero/non-positive/NaN price rows dropped: {rep['non_positive_rows_dropped']}")
    fl = rep["flagged_moves"]
    print(f"- Daily close moves beyond +/-{SPLIT_THRESHOLD:.0%}: {len(fl)}")
    for _, r in fl.iterrows():
        print(f"  - {r['date'].date()}: close {r['close']:.2f} ({r['move_pct']:+.1f}%)")
    weekdays = df["date"].dt.day_name().value_counts().to_dict()
    print(f"- Rows by weekday: {weekdays}")

    strat, bh, df = simulate(df, args.fast, args.slow, args.cash, args.commission)
    plot(df, strat, bh, args.symbol, args.fast, args.slow, args.out)

    ms, mb = metrics(strat, args.rf), metrics(bh, args.rf)
    print(f"\n## Backtest {args.symbol} SMA {args.fast}/{args.slow}, "
          f"{strat.equity.index[0].date()} to {strat.equity.index[-1].date()}, rf={args.rf:.2%}\n")
    print("### Profit\n")
    print(table(["Total return", "CAGR", "Final equity (EGP)", "Trades (round trips)", "Win rate",
                 "Total commission (EGP)"], ms, mb))
    print("\n### Risk\n")
    print(table(["Annualised volatility", "Max drawdown", "Sharpe", "Sortino"], ms, mb))
    print(f"\nChart saved to {args.out}")


if __name__ == "__main__":
    main()
