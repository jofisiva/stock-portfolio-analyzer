"""Stock Portfolio Analyzer: load a holdings CSV, validate it, and analyze the snapshot."""

import csv
import hashlib
import html
import io
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from theme import (ACCENT, DONUT_SHADES, FLAT, GAIN, GAIN_TEXT, LOSS, LOSS_TEXT, PAPER,
                   SECTOR_BAR, apply_theme)

HERE = Path(__file__).parent
SAMPLE_PATH = HERE / "sample_portfolio.csv"
# Market picks the currency used for display and which fictional sample loads.
# A portfolio must be in one currency: values are summed with no FX conversion.
MARKETS = {
    "India (₹ INR)": {"currency": "INR", "sample": SAMPLE_PATH},
    "USA ($ USD)": {"currency": "USD", "sample": HERE / "sample_portfolio_us.csv"},
}
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$"}
REQUIRED_COLUMNS = [
    "ticker", "company_name", "sector", "quantity",
    "buy_price", "buy_date", "current_price",
]
NUMERIC_COLUMNS = ["quantity", "buy_price", "current_price"]


def parse_csv(data):
    """Parse CSV bytes into an all-string DataFrame. Returns (df, errors).

    The index holds each record's line number in the file (header is line 1),
    so errors point at the right line even when blank lines are skipped.
    """
    try:
        text = data.decode("utf-8-sig")  # -sig strips the BOM Excel adds
    except UnicodeDecodeError:
        return None, ["The file is not UTF-8 text. Save it as 'CSV UTF-8' and upload again."]
    reader = csv.reader(io.StringIO(text, newline=""))
    records = []
    try:
        for fields in reader:
            if any(f.strip() for f in fields):  # blank lines hold no data; skip them
                records.append((reader.line_num, fields))
    except csv.Error as exc:
        return None, [f"Could not parse the file as CSV (line {reader.line_num}): {exc}"]
    if not records:
        return None, ["The file is empty."]

    header = [h.strip().lower() for h in records[0][1]]
    body = records[1:]
    errors = [f"Row {line}: expected {len(header)} values but found {len(fields)}."
              for line, fields in body if len(fields) != len(header)]
    if errors:
        return None, errors
    df = pd.DataFrame([fields for _, fields in body], columns=header, dtype=str,
                      index=[line for line, _ in body])
    return df, []


def validate_portfolio(raw):
    """Validate and type a string DataFrame indexed by CSV row number.

    Returns (clean_df, errors). Every problem is reported with its CSV row
    number; no rows are dropped.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        return None, [f"Missing required column(s): {', '.join(missing)}. "
                      f"Expected: {', '.join(REQUIRED_COLUMNS)}."]
    if raw.columns.duplicated().any():
        dupes = sorted(set(raw.columns[raw.columns.duplicated()]))
        return None, [f"Duplicate column name(s): {', '.join(dupes)}."]

    df = raw[REQUIRED_COLUMNS].apply(lambda col: col.str.strip())
    if df.empty:
        return None, ["The file has a header but no holdings rows."]

    df["ticker"] = df["ticker"].str.upper()
    errors = []

    for line, row in df.iterrows():
        empty = [c for c in REQUIRED_COLUMNS if row[c] == ""]
        if empty:
            errors.append(f"Row {line}: missing value(s) in {', '.join(empty)}.")

    for col in NUMERIC_COLUMNS:
        nums = pd.to_numeric(df[col], errors="coerce")
        for line, text, value in zip(df.index, df[col], nums):
            if text == "":
                continue  # already reported as missing
            if pd.isna(value) or not math.isfinite(value):
                errors.append(f"Row {line}: {col} '{text}' is not a valid finite number.")
            elif col == "quantity" and value <= 0:
                errors.append(f"Row {line}: quantity must be greater than 0 (got {text}).")
            elif col != "quantity" and value < 0:
                errors.append(f"Row {line}: {col} must be 0 or more (got {text}).")
        df[col] = nums

    # Each number can be finite while quantity x price overflows (e.g. 1e308 x 1e308).
    for price in ("buy_price", "current_price"):
        overflow = np.isinf(df["quantity"] * df[price])
        for line in df.index[overflow]:
            errors.append(f"Row {line}: quantity x {price} is too large to calculate.")

    # strptime alone accepts 2024-1-5, so also require the exact YYYY-MM-DD shape.
    shaped = df["buy_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    dates = pd.to_datetime(df["buy_date"].where(shaped), format="%Y-%m-%d", errors="coerce")
    for line, text, value in zip(df.index, df["buy_date"], dates):
        if text != "" and pd.isna(value):
            errors.append(f"Row {line}: buy_date '{text}' is not a valid YYYY-MM-DD date.")
    df["buy_date"] = dates

    tickers = df["ticker"]
    for ticker in sorted(set(tickers[tickers.duplicated(keep=False) & (tickers != "")])):
        rows = [str(line) for line in tickers.index[tickers == ticker]]
        errors.append(f"Duplicate ticker {ticker} in rows {', '.join(rows)}. "
                      "Use one row per ticker.")

    if errors:
        return None, errors
    return df.reset_index(drop=True), []


def add_metrics(df):
    """Add invested/current value, unrealized P&L and return % (NaN when invested is 0)."""
    out = df.copy()
    out["invested_value"] = out["quantity"] * out["buy_price"]
    out["current_value"] = out["quantity"] * out["current_price"]
    out["unrealized_pnl"] = out["current_value"] - out["invested_value"]
    invested = out["invested_value"].where(out["invested_value"] != 0)
    out["unrealized_return_pct"] = out["unrealized_pnl"] / invested * 100
    out["status"] = np.select([out["unrealized_pnl"] > 0, out["unrealized_pnl"] < 0],
                              ["Gain", "Loss"], "Unchanged")
    return out


def rank_extremes(df):
    """Best and worst holdings by unrealized return %, skipping N/A returns.

    Returns (best, worst) as lists of {ticker, return_pct, pnl} dicts; a list has
    several entries on a tie, and both are empty when no return is defined.
    """
    defined = df.dropna(subset=["unrealized_return_pct"])
    if defined.empty:
        return [], []
    pct = defined["unrealized_return_pct"]

    def pick(target):
        rows = defined[np.isclose(pct, target, rtol=0, atol=1e-9)]
        return [{"ticker": r.ticker, "return_pct": r.unrealized_return_pct,
                 "pnl": r.unrealized_pnl} for r in rows.itertuples()]

    return pick(pct.max()), pick(pct.min())


def portfolio_summary(df):
    """Portfolio totals. Return % is total P&L / total invested, not an average."""
    invested = df["invested_value"].sum()
    current = df["current_value"].sum()
    pnl = current - invested
    best, worst = rank_extremes(df)
    return {
        "invested": invested,
        "current": current,
        "pnl": pnl,
        "return_pct": pnl / invested * 100 if invested != 0 else float("nan"),
        "best": best,
        "worst": worst,
    }


def allocation(df, by, cur="INR"):
    """Current value and portfolio weight % grouped by `by`, largest first.

    Returns None when total current value is 0 (weights are undefined).
    """
    total = df["current_value"].sum()
    if total == 0:
        return None
    out = df.groupby(by, as_index=False)["current_value"].sum()
    out["weight_pct"] = out["current_value"] / total * 100
    out["value_label"] = out["current_value"].map(lambda v: format_money(v, cur))
    # Stable sort keeps groupby's alphabetical order for equal values (deterministic ties).
    return out.sort_values("current_value", ascending=False, kind="stable", ignore_index=True)


def largest(alloc, by):
    """Names tied for the largest weight in an allocation table, and that weight."""
    top = alloc["weight_pct"].iloc[0]
    names = alloc.loc[np.isclose(alloc["weight_pct"], top, rtol=0, atol=1e-9), by]
    return list(names), top


def portfolio_health(df):
    """Concentration facts for the selected holdings (not a risk score).

    Weight fields are None when total current value is 0.
    """
    counts = df["status"].value_counts()
    health = {
        "count": len(df),
        "total": df["current_value"].sum(),
        "gains": int(counts.get("Gain", 0)),
        "losses": int(counts.get("Loss", 0)),
        "unchanged": int(counts.get("Unchanged", 0)),
        "largest": None, "top": None, "sector": None,
    }
    by_stock = allocation(df, "ticker")
    if by_stock is None:
        return health
    top = by_stock.head(3)
    health["largest"] = largest(by_stock, "ticker")
    health["top"] = (list(top["ticker"]), top["weight_pct"].sum())
    health["sector"] = largest(allocation(df, "sector"), "sector")
    return health


def join_names(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def plural(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def health_summary(h, cur="INR"):
    """Plain-English description built only from portfolio_health() facts."""
    n = h["count"]
    parts = [f"This selection has {plural(n, 'holding')} with a current value of "
             f"{format_money(h['total'], cur)} at the CSV prices."]
    if h["largest"] is None:
        parts.append(f"Total current value is {format_money(0, cur)}, so holding and "
                     "sector weights cannot be calculated.")
    else:
        names, weight = h["largest"]
        if n == 1:
            parts.append(f"{names[0]} is the only holding, so it is 100.00% of current value.")
        elif len(names) > 1:
            parts.append(f"The largest holdings are {join_names(names)}, "
                         f"each at {weight:.2f}% of current value.")
        else:
            parts.append(f"The largest holding is {names[0]} at {weight:.2f}% of current value.")
        tickers, top_weight = h["top"]
        if 1 < n <= 3:
            parts.append(f"All {n} holdings together make up {top_weight:.2f}%.")
        elif n > 3:
            parts.append(f"The top three ({join_names(tickers)}) make up {top_weight:.2f}%.")
        sectors, sector_weight = h["sector"]
        if len(sectors) > 1:
            parts.append(f"The largest sectors are {join_names(sectors)}, "
                         f"each at {sector_weight:.2f}%.")
        else:
            parts.append(f"The largest sector is {sectors[0]} at {sector_weight:.2f}%.")
    parts.append(f"{plural(h['gains'], 'holding')} {'shows' if h['gains'] == 1 else 'show'} "
                 f"an unrealized gain, {h['losses']} a loss, and {h['unchanged']} "
                 "no change.")
    return " ".join(parts)


def show_health(holdings, cur):
    h = portfolio_health(holdings)
    st.subheader("Portfolio health")
    st.caption("How concentrated the selected holdings are by current value. It is not a "
               "risk score and does not measure volatility or drawdown, which need "
               "historical prices. Not investment advice.")
    cols = st.columns(4, gap="large")
    if h["largest"] is None:
        st.warning(f"Total current value is {format_money(0, cur)}, so weights are undefined.")
    else:
        names, weight = h["largest"]
        cols[0].metric("Largest holding", ", ".join(names), f"{weight:.2f}% of value",
                       delta_color="off")
        tickers, top_weight = h["top"]
        label = "Top 3 holdings" if len(tickers) == 3 else "All holdings"
        cols[1].metric(label, f"{top_weight:.2f}%", ", ".join(tickers), delta_color="off")
        sectors, sector_weight = h["sector"]
        cols[2].metric("Largest sector", ", ".join(sectors), f"{sector_weight:.2f}% of value",
                       delta_color="off")
    cols[3].metric("Gain · Loss · Unchanged",
                   f"{h['gains']} · {h['losses']} · {h['unchanged']}")
    # The marker turns the next info box into the italic pull quote (see theme.py).
    st.markdown('<span class="bs-quote-next"></span>', unsafe_allow_html=True)
    st.info(health_summary(h, cur))
    st.markdown('<span class="bs-small">Written automatically from the figures above by '
                'fixed rules.</span>', unsafe_allow_html=True)


def stock_allocation_chart(alloc, cur="INR", count=None):
    colors = [DONUT_SHADES[i % len(DONUT_SHADES)] for i in range(len(alloc))]
    fig = go.Figure(go.Pie(
        labels=alloc["ticker"], values=alloc["current_value"], hole=0.62,
        sort=False, direction="clockwise", textinfo="none",
        marker=dict(colors=colors, line=dict(color=PAPER, width=2)),
        customdata=alloc[["value_label", "weight_pct"]],
        hovertemplate="<b>%{label}</b><br>Current value: %{customdata[0]}"
                      "<br>Weight: %{customdata[1]:.2f}%<extra></extra>",
    ))
    n = count if count is not None else len(alloc)
    fig.update_layout(
        title="Allocation by stock (% of current value)", height=340,
        legend=dict(title_text="", orientation="v", x=1.02, y=0.5, yanchor="middle"),
        annotations=[dict(text=f"<span style='font-size:11px'>{n} HOLDING{'' if n == 1 else 'S'}</span><br>"
                               f"<b>{format_money(alloc['current_value'].sum(), cur)}</b>",
                          x=0.5, y=0.5, showarrow=False, font=dict(size=16))],
    )
    return fig


def sector_allocation_chart(alloc, selected=()):
    alloc = alloc.iloc[::-1]  # largest at the top of a horizontal bar chart
    colors = [ACCENT if s in selected else SECTOR_BAR for s in alloc["sector"]]
    fig = go.Figure(go.Bar(
        x=alloc["weight_pct"], y=alloc["sector"], orientation="h",
        marker_color=colors, width=0.5,
        text=alloc["weight_pct"].map("{:.1f}%".format), textposition="outside",
        cliponaxis=False,
        customdata=alloc[["value_label"]],
        hovertemplate="<b>%{y}</b><br>Current value: %{customdata[0]}"
                      "<br>Weight: %{x:.2f}%<br><i>Click to filter</i><extra></extra>",
    ))
    fig.update_layout(title="Allocation by sector (% of current value)", height=340,
                      xaxis=dict(visible=False), yaxis_title=None,
                      margin=dict(r=48), clickmode="event+select")
    return fig


def pnl_chart(df, cur="INR"):
    data = df.sort_values("unrealized_pnl", ascending=False)
    pnl = data["unrealized_pnl"]
    symbol = CURRENCY_SYMBOLS[cur]
    signed = pnl.map(lambda v: format_signed_money(v, cur))
    colors = [GAIN if v > 0 else LOSS if v < 0 else FLAT for v in pnl]
    fig = go.Figure(go.Bar(
        x=data["ticker"], y=pnl, marker_color=colors,
        text=signed, textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=[GAIN_TEXT if v > 0 else LOSS_TEXT if v < 0 else "#201e1d"
                                      for v in pnl]),
        customdata=list(zip(signed,
                            data["unrealized_return_pct"].map(format_pct),
                            data["current_value"].map(lambda v: format_money(v, cur)))),
        hovertemplate="<b>%{x}</b><br>Unrealized P&L: %{customdata[0]}"
                      "<br>Return: %{customdata[1]}"
                      "<br>Current value: %{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(
        title=f"Unrealized P&L by stock ({symbol}, high to low · cyan gain, magenta loss)",
        xaxis_title=None, yaxis_title=f"Unrealized P&L ({symbol})",
        yaxis_tickprefix=symbol, yaxis_zeroline=True, height=380, bargap=0.45)
    return fig


def on_sector_click():
    """Clicking a sector bar toggles that sector in the sidebar's Sector filter."""
    event = st.session_state.get("sector_chart")
    points = (event or {}).get("selection", {}).get("points", [])
    if not points:
        return
    sector = points[0].get("y")
    chosen = list(st.session_state.get("f_sectors", []))
    chosen.remove(sector) if sector in chosen else chosen.append(sector)
    st.session_state["f_sectors"] = chosen


def show_charts(holdings, cur):
    st.subheader("Dashboard")
    st.caption("A snapshot of the CSV prices only. No historical performance, volatility, "
               "drawdown, or benchmark comparison is shown; those need historical "
               "price and transaction data. Click a sector bar to filter by it.")
    by_stock = allocation(holdings, "ticker", cur)
    by_sector = allocation(holdings, "sector", cur)
    if by_stock is None:
        st.warning(f"Total current value is {format_money(0, cur)}, so allocation weights "
                   "are undefined. Allocation charts are hidden.")
    else:
        left, right = st.columns(2, gap="large")
        left.plotly_chart(stock_allocation_chart(by_stock, cur), use_container_width=True)
        right.plotly_chart(sector_allocation_chart(by_sector, st.session_state.get("f_sectors", [])),
                           use_container_width=True, key="sector_chart",
                           on_select=on_sector_click, selection_mode="points")
    st.plotly_chart(pnl_chart(holdings, cur), use_container_width=True)


def format_money(value, cur="INR"):
    """INR uses Indian grouping (-₹1,23,456.78); USD uses thousands (-$123,456.78)."""
    if pd.isna(value):
        return "N/A"
    sign = "-" if value < 0 else ""
    symbol = CURRENCY_SYMBOLS[cur]
    if cur != "INR":
        return f"{sign}{symbol}{abs(value):,.2f}"
    whole, frac = f"{abs(value):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}{symbol}{','.join(groups + [tail])}.{frac}"


def format_pct(value):
    return "N/A" if pd.isna(value) else f"{value:+.2f}%"


def format_signed_money(value, cur="INR"):
    """Like format_money but with an explicit + for gains."""
    return ("+" if not pd.isna(value) and value > 0 else "") + format_money(value, cur)


def colored(text, value):
    """HTML span in the gain/loss text colour (cyan / magenta); plain otherwise."""
    if pd.isna(value) or value == 0:
        return text
    return f'<span class="{"bs-gain" if value > 0 else "bs-loss"}">{text}</span>'


def delta_color(value):
    return "off" if pd.isna(value) or value == 0 else "normal"


def performer_card(label, entries, holding_count, cur):
    """Metric card for best/worst performer, handling ties, one holding, and no data."""
    if not entries:
        st.metric(label, "N/A", help="No holding has a defined return (invested value is 0).")
        return
    pct = entries[0]["return_pct"]
    tickers = ", ".join(e["ticker"] for e in entries)
    st.metric(label, tickers, delta=f"{format_pct(pct)} return", delta_color=delta_color(pct))
    pnl = " · ".join(f"{e['ticker']}: {colored(format_signed_money(e['pnl'], cur), e['pnl'])}"
                     for e in entries)
    st.caption(f"P&L {pnl}", unsafe_allow_html=True)
    if holding_count == 1:
        st.caption("Only one holding, so it is both best and worst.")
    elif len(entries) > 1:
        st.caption(f"Tie: {len(entries)} holdings share this return.")


def show_summary(holdings, cur):
    s = portfolio_summary(holdings)
    cols = st.columns(5, gap="large")
    cols[0].metric("Total invested", format_money(s["invested"], cur))
    cols[1].metric("Current value", format_money(s["current"], cur))
    with cols[2]:
        st.metric("Unrealized P&L", format_signed_money(s["pnl"], cur),
                  delta=f"{format_pct(s['return_pct'])} portfolio return",
                  delta_color=delta_color(s["pnl"]))
        st.caption("Total P&L ÷ total invested, not an average of holdings.")
    with cols[3]:
        performer_card("Best performer", s["best"], len(holdings), cur)
    with cols[4]:
        performer_card("Worst performer", s["worst"], len(holdings), cur)


def load_portfolio(data):
    """CSV bytes -> (holdings with metrics, errors)."""
    raw, errors = parse_csv(data)
    if errors:
        return None, errors
    clean, errors = validate_portfolio(raw)
    if errors:
        return None, errors
    return add_metrics(clean), []


def xirr(flows):
    """Annual rate r (as %) where sum(amount / (1+r)^(days/365)) = 0.

    Expects money paid in (negative) before one final payout (positive), which
    makes the sum strictly decreasing in r, so bisection finds the single root.
    Returns NaN when there is no such pattern.
    """
    start = min(d for d, _ in flows)
    t = [((d - start).days / 365, a) for d, a in flows]
    if not any(a < 0 for _, a in t) or max(y for y, _ in t) == 0:
        return float("nan")
    if not any(a > 0 for _, a in t):
        return -100.0  # everything paid in is now worth 0

    def npv(r):
        try:
            return sum(a / (1 + r) ** y for y, a in t)
        except OverflowError:  # r near -100% over many years: final payout dominates
            return math.inf

    low, high = -0.9999, 1.0
    while npv(high) > 0:
        high *= 2
        if high > 1e6:
            return float("nan")
    for _ in range(200):
        mid = (low + high) / 2
        low, high = (mid, high) if npv(mid) > 0 else (low, mid)
    return (low + high) / 2 * 100


def portfolio_xirr(df, as_of):
    """XIRR treating each holding as bought on buy_date and valued on `as_of`.

    NaN when any holding is bought after `as_of` or nothing was invested.
    """
    if (df["buy_date"].dt.date > as_of).any() or df["invested_value"].sum() == 0:
        return float("nan")
    flows = [(d.date(), -v) for d, v in zip(df["buy_date"], df["invested_value"]) if v > 0]
    flows.append((as_of, df["current_value"].sum()))
    return xirr(flows)


def show_annualized(selected, as_of):
    rate = portfolio_xirr(selected, as_of)
    bought = selected["buy_date"].dt.date
    left, right = st.columns([1, 2], gap="large")
    left.metric("Annualized return (XIRR)", format_pct(rate), delta_color="off",
                help="Annual rate that makes the money invested on each buy date "
                     "grow to today's total value.")
    with right:
        st.markdown(
            f'<p class="bs-note" style="padding-top:6px">Prices treated as of '
            f'<b>{as_of:%Y-%m-%d}</b>. Each row is one purchase on its buy date (one row per '
            'ticker), so extra buys, partial sales and dividends are not included. These are '
            'two-point returns (buy and current price), not a price history.</p>',
            unsafe_allow_html=True)
        note = None
        if (bought > as_of).any():
            note = ("Some buy dates are after the as-of date, so XIRR is N/A. "
                    "Change <b>Prices as of</b> in the sidebar.")
        elif (as_of - bought.min()).days < 365:
            note = ("Every selected holding was bought less than a year ago, so the XIRR "
                    "annualizes a short period and can look extreme.")
        if note:
            st.markdown(f'<p class="bs-warn">⚠ {note}</p>', unsafe_allow_html=True)


STATUSES = ["All", "Gain", "Loss", "Unchanged"]
FILTER_KEYS = ["f_search", "f_sectors", "f_tickers", "f_dates", "f_status"]


def apply_filters(df, search="", sectors=(), tickers=(), date_from=None, date_to=None,
                  status="All"):
    """Return holdings matching every active filter. Empty/None means 'no filter'.

    Dates are inclusive on both ends. Search matches ticker or company name,
    case-insensitive, as plain text.
    """
    mask = pd.Series(True, index=df.index)
    term = search.strip().lower()
    if term:
        mask &= (df["ticker"].str.lower().str.contains(term, regex=False)
                 | df["company_name"].str.lower().str.contains(term, regex=False))
    if sectors:
        mask &= df["sector"].isin(sectors)
    if tickers:
        mask &= df["ticker"].isin(tickers)
    bought = df["buy_date"].dt.date
    if date_from is not None:
        mask &= bought >= date_from
    if date_to is not None:
        mask &= bought <= date_to
    if status != "All":
        mask &= df["status"] == status
    return df[mask].reset_index(drop=True)


def export_csv(df, cur="INR"):
    """Filtered holdings with calculated columns as CSV bytes (N/A return -> blank)."""
    out = df.copy()
    out["buy_date"] = out["buy_date"].dt.strftime("%Y-%m-%d")
    out["currency"] = cur
    return out.round(4).to_csv(index=False).encode()


def reset_filters():
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def clear_filter(key):
    st.session_state.pop(key, None)


def sidebar_filters(holdings):
    """Render filter widgets and return apply_filters kwargs plus whether any is active."""
    first, last = holdings["buy_date"].min().date(), holdings["buy_date"].max().date()
    st.header("Filters")
    st.caption("Filters combine (a holding must match all of them). "
               "Leave a list empty to include everything.")
    search = st.text_input("Search company or ticker", key="f_search",
                           placeholder="Part of a name or ticker")
    sectors = st.multiselect("Sector", sorted(holdings["sector"].unique()), key="f_sectors",
                             placeholder="Every sector")
    tickers = st.multiselect("Ticker", sorted(holdings["ticker"]), key="f_tickers",
                             placeholder="Every ticker")
    dates = st.date_input("Bought between (inclusive)", value=(first, last), min_value=first,
                          max_value=last, key="f_dates", format="YYYY-MM-DD")
    st.caption("Selects holdings by their purchase date. "
               "It does not show historical portfolio performance.")
    status = st.radio("Status", STATUSES, horizontal=True, key="f_status")
    st.button("↺  Reset filters", on_click=reset_filters, use_container_width=True)

    date_from = dates[0] if len(dates) > 0 else None
    date_to = dates[1] if len(dates) > 1 else None  # one date picked: open-ended until the second
    active = bool(search.strip() or sectors or tickers or status != "All"
                  or (date_from, date_to) != (first, last))
    return dict(search=search, sectors=sectors, tickers=tickers, date_from=date_from,
                date_to=date_to, status=status), active, (first, last)


def error_locations(errors):
    """(lines, columns) each error points at, read back from its message."""
    locs = []
    for e in errors:
        dup = re.match(r"Duplicate ticker \S+ in rows ([\d, ]+)\.", e)
        row = re.match(r"Row (\d+): (.*)", e)
        if dup:
            locs.append(([int(x) for x in dup.group(1).split(",")], ["ticker"]))
        elif row:
            rest = row.group(2)
            missing = re.match(r"missing value\(s\) in (.+)\.$", rest)
            if missing:
                cols = [c.strip() for c in missing.group(1).split(",")]
            else:
                word = rest.split(" ")[0]
                cols = [word] if word in REQUIRED_COLUMNS else []
            locs.append(([int(row.group(1))], cols))
        else:
            locs.append(([], []))
    return locs


def show_load_error(source, data, errors):
    """Rejected upload: every problem by row, beside the file as read with bad cells marked."""
    locs = error_locations(errors)
    items, rules = [], []
    for i, (e, (lines, _)) in enumerate(zip(errors, locs)):
        where = f"Rows {', '.join(map(str, lines))}" if len(lines) > 1 else (
            f"Row {lines[0]}" if lines else "File")
        msg = e.split(": ", 1)[1] if e.startswith("Row ") else e
        items.append(f'<div class="bs-err-item e{i}"><span class="bs-err-where">{where}</span>'
                     f'<span class="bs-err-msg">{html.escape(msg)}</span></div>')
        rules += [f".bs-err:has(.e{i}:hover) tr.l{n} td {{ background: #fff1f4; }}" for n in lines]

    bad = {(n, c) for lines, cols in locs for n in lines for c in cols}
    table = ""
    records = []
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""))
        for fields in reader:
            if any(x.strip() for x in fields):
                records.append((reader.line_num, fields))
    except (UnicodeDecodeError, csv.Error):
        records = []
    if records:
        header = [h.strip().lower() for h in records[0][1]]
        head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
        body = ""
        for line, fields in records[1:51]:
            cells = "".join(
                f'<td class="{"bad" if (line, header[j] if j < len(header) else "") in bad else ""}">'
                f"{html.escape(v)}</td>" for j, v in enumerate(fields))
            body += f'<tr class="l{line}"><td class="line">{line}</td>{cells}</tr>'
        table = (f'<div class="bs-raw"><div class="bs-kicker" style="margin-bottom:10px">'
                 f'The file as read · problem cells marked</div><table><thead><tr><th>Line</th>'
                 f'{head}</tr></thead><tbody>{body}</tbody></table></div>')

    count = plural(len(errors), "problem")
    st.markdown(
        f"<style>{' '.join(rules)}</style>"
        f'<div class="bs-err-kicker">⚠ Upload rejected</div>'
        f'<div class="bs-err-title">{html.escape(source)} could not be loaded.</div>'
        f'<p class="bs-err-lede">Nothing was loaded and nothing was dropped. Fix the {count} '
        'below and upload again — each row number is the line in your file, counting the '
        'header as line 1.</p>'
        f'<div class="bs-err"><div>{"".join(items)}</div>{table}</div>',
        unsafe_allow_html=True)
    st.write("")
    st.button("Use sample data instead", type="primary", on_click=clear_upload,
              key="error_use_sample")


def clear_upload():
    """Remove the uploaded file by remounting the uploader under a new key."""
    st.session_state["upload_n"] = st.session_state.get("upload_n", 0) + 1


def show_empty(holdings, filters, bounds):
    """No matches: say which single filter to loosen, with how many holdings come back."""
    st.markdown('<span class="bs-empty-next"></span>', unsafe_allow_html=True)
    st.warning("No holdings match the current filters.")
    st.markdown('<p style="font-size:17px;margin:0 0 12px">Loosen one of them — each line '
                'shows how many holdings would come back.</p>', unsafe_allow_html=True)
    first, last = bounds
    options = []
    if filters["search"].strip():
        options.append(("f_search", f"search “{filters['search'].strip()}”", dict(search="")))
    if filters["sectors"]:
        options.append(("f_sectors", "sector: " + ", ".join(filters["sectors"]), dict(sectors=())))
    if filters["tickers"]:
        options.append(("f_tickers", "ticker: " + ", ".join(filters["tickers"]), dict(tickers=())))
    if filters["status"] != "All":
        options.append(("f_status", f"status: {filters['status']}", dict(status="All")))
    if (filters["date_from"], filters["date_to"]) != (first, last):
        options.append(("f_dates", f"bought {filters['date_from']} – {filters['date_to'] or '…'}",
                        dict(date_from=None, date_to=None)))
    counted = [(key, label, len(apply_filters(holdings, **{**filters, **patch})))
               for key, label, patch in options]
    for key, label, n in sorted(counted, key=lambda x: -x[2]):
        st.button(f"Remove {label}  ·  {plural(n, 'holding')} back", key=f"relax_{key}",
                  on_click=clear_filter, args=(key,))
    st.button("↺  Reset all filters", on_click=reset_filters, key="reset_empty", type="primary")


def main():
    st.set_page_config(page_title="Stock Portfolio Analyzer", layout="wide")
    apply_theme()
    st.title("Stock Portfolio Analyzer")

    with st.sidebar:
        st.header("Data")
        market = st.radio("Market", list(MARKETS), horizontal=True, key="market",
                          help="Sets the currency for every value and which sample loads. "
                               "Your CSV's prices must all be in this currency; "
                               "nothing is converted.")
        cur = MARKETS[market]["currency"]
        sample_path = MARKETS[market]["sample"]
        sample_bytes = sample_path.read_bytes()
        uploaded = st.file_uploader("Portfolio CSV", type="csv",
                                    key=f"upload_{st.session_state.get('upload_n', 0)}",
                                    help="Remove the uploaded file to return to sample data.")
        st.download_button(f"↓  Download {cur} sample CSV", sample_bytes,
                           file_name=sample_path.name, mime="text/csv")
        st.caption("Required columns: " + ", ".join(REQUIRED_COLUMNS))
        as_of = st.date_input("Prices as of", value=date.today(), key="as_of",
                              format="YYYY-MM-DD",
                              help="The date your current_price values are from. "
                                   "Used for the portfolio XIRR.")

    if uploaded is None:
        data, source = sample_bytes, sample_path.name
        label = f"**Sample data, {market}** — all holdings and prices are fictional"
    else:
        data, source = uploaded.getvalue(), uploaded.name
        label = f"**Uploaded data**: {uploaded.name}, shown as {market}"

    # Filter values from a previous file may not exist in this one: start fresh.
    data_id = hashlib.sha256(data).hexdigest()
    if st.session_state.get("data_id") != data_id:
        reset_filters()
        st.session_state["data_id"] = data_id

    holdings, errors = load_portfolio(data)
    if errors:
        show_load_error(source, data, errors)
        st.stop()

    with st.sidebar:
        filters, active, bounds = sidebar_filters(holdings)
    selected = apply_filters(holdings, **filters)

    note = " · :blue[Filters active]" if active else ""
    st.caption(f"{label} · Showing **{len(selected)} of {len(holdings)}** holdings{note}")
    st.info("Prices come from the CSV you supply and are **not live**. Results exclude "
            "dividends, fees, taxes, and realized trades.")

    if selected.empty:
        show_empty(holdings, filters, bounds)
        st.stop()

    show_summary(selected, cur)
    show_annualized(selected, as_of)
    show_charts(selected, cur)
    show_health(selected, cur)
    show_table(selected, source, active, cur)


def _tone(value):
    if pd.isna(value) or value == 0:
        return ""
    return f"color: {GAIN_TEXT if value > 0 else LOSS_TEXT}"


def _status_tone(status):
    return {"Gain": f"color: {GAIN_TEXT}", "Loss": f"color: {LOSS_TEXT}"}.get(status, "")


def show_table(selected, source, active, cur):
    st.subheader(f"Holdings ({len(selected)})")
    st.download_button(
        "↓  Download filtered analysis CSV" if active else "↓  Download analysis CSV",
        export_csv(selected, cur), file_name=f"analysis_{Path(source).stem}.csv",
        mime="text/csv",
        help="Selected holdings with invested value, current value, P&L, return %, "
             "status and currency.",
    )
    shown = selected.sort_values("current_value", ascending=False, kind="stable",
                                 ignore_index=True)
    money = ["buy_price", "current_price", "invested_value", "current_value", "unrealized_pnl"]
    styled = (shown.style
              .format({**{c: (lambda v: format_money(v, cur)) for c in money},
                       "unrealized_return_pct": format_pct,
                       "quantity": "{:g}",
                       "buy_date": lambda d: d.strftime("%Y-%m-%d")})
              .map(_tone, subset=["unrealized_pnl", "unrealized_return_pct"])
              .map(_status_tone, subset=["status"])
              .set_properties(subset=["ticker"], **{"font-weight": "600"}))
    labels = {"ticker": "Ticker", "company_name": "Company", "sector": "Sector",
              "quantity": "Qty", "buy_price": "Buy price", "buy_date": "Buy date",
              "current_price": "Current price", "invested_value": "Invested",
              "current_value": "Current value", "unrealized_pnl": "P&L",
              "unrealized_return_pct": "Return", "status": "Status"}
    st.dataframe(styled, hide_index=True, use_container_width=True,
                 column_config={k: st.column_config.Column(v) for k, v in labels.items()})


if __name__ == "__main__":
    main()
