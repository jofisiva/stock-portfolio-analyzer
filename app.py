"""Stock Portfolio Analyzer: load a holdings CSV, validate it, and analyze the snapshot."""

import csv
import hashlib
import io
import math
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

SAMPLE_PATH = Path(__file__).parent / "sample_portfolio.csv"
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
            if any(f.strip() for f in fields):
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


def allocation(df, by):
    """Current value and portfolio weight % grouped by `by`, largest first.

    Returns None when total current value is 0 (weights are undefined).
    """
    total = df["current_value"].sum()
    if total == 0:
        return None
    out = df.groupby(by, as_index=False)["current_value"].sum()
    out["weight_pct"] = out["current_value"] / total * 100
    out["value_label"] = out["current_value"].map(format_inr)
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


def health_summary(h):
    """Plain-English description built only from portfolio_health() facts."""
    n = h["count"]
    parts = [f"This selection has {plural(n, 'holding')} with a current value of "
             f"{format_inr(h['total'])} at the CSV prices."]
    if h["largest"] is None:
        parts.append("Total current value is ₹0, so holding and sector weights "
                     "cannot be calculated.")
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


def show_health(holdings):
    h = portfolio_health(holdings)
    st.subheader("Portfolio Health: concentration analysis")
    st.caption("Describes how concentrated the selected holdings are by current value. "
               "It is not a comprehensive risk score and does not measure volatility or "
               "drawdown, which need historical prices. Not investment advice.")
    cols = st.columns(4)
    if h["largest"] is None:
        st.warning("Total current value is ₹0, so weights are undefined.")
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
    cols[3].metric("Gain / Loss / Unchanged",
                   f"{h['gains']} / {h['losses']} / {h['unchanged']}")
    st.markdown("**Summary** (written automatically from the figures above)")
    st.info(health_summary(h))


GAIN, LOSS, FLAT = "#1a9850", "#d73027", "#9e9e9e"


def stock_allocation_chart(alloc):
    fig = go.Figure(go.Pie(
        labels=alloc["ticker"], values=alloc["current_value"], hole=0.5,
        sort=False, textinfo="label+percent", textposition="inside",
        customdata=alloc[["value_label", "weight_pct"]],
        hovertemplate="<b>%{label}</b><br>Current value: %{customdata[0]}"
                      "<br>Weight: %{customdata[1]:.2f}%<extra></extra>",
    ))
    fig.update_layout(title="Allocation by stock (% of current value)",
                      legend_title_text="Ticker")
    return fig


def sector_allocation_chart(alloc):
    alloc = alloc.iloc[::-1]  # largest at the top of a horizontal bar chart
    fig = go.Figure(go.Bar(
        x=alloc["weight_pct"], y=alloc["sector"], orientation="h",
        text=alloc["weight_pct"].map("{:.1f}%".format), textposition="auto",
        customdata=alloc[["value_label"]],
        hovertemplate="<b>%{y}</b><br>Current value: %{customdata[0]}"
                      "<br>Weight: %{x:.2f}%<extra></extra>",
    ))
    fig.update_layout(title="Allocation by sector (% of current value)",
                      xaxis_title="Portfolio weight (%)", xaxis_ticksuffix="%",
                      yaxis_title=None)
    return fig


def pnl_chart(df):
    data = df.sort_values("unrealized_pnl", ascending=False)
    pnl = data["unrealized_pnl"]
    colors = [GAIN if v > 0 else LOSS if v < 0 else FLAT for v in pnl]
    fig = go.Figure(go.Bar(
        x=data["ticker"], y=pnl, marker_color=colors,
        text=pnl.map(format_signed_inr), textposition="outside", cliponaxis=False,
        customdata=list(zip(pnl.map(format_signed_inr),
                            data["unrealized_return_pct"].map(format_pct),
                            data["current_value"].map(format_inr))),
        hovertemplate="<b>%{x}</b><br>Unrealized P&L: %{customdata[0]}"
                      "<br>Return: %{customdata[1]}"
                      "<br>Current value: %{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(title="Unrealized P&L by stock (₹, sorted high to low; green gain, red loss)",
                      xaxis_title="Ticker", yaxis_title="Unrealized P&L (₹)",
                      yaxis_tickprefix="₹", yaxis_zeroline=True)
    return fig


def show_charts(holdings):
    st.subheader("Dashboard")
    st.caption("Snapshot of the CSV prices only. No historical performance, volatility, "
               "drawdown, or benchmark comparison is shown; those need historical "
               "price and transaction data.")
    by_stock, by_sector = allocation(holdings, "ticker"), allocation(holdings, "sector")
    if by_stock is None:
        st.warning("Total current value is ₹0, so allocation weights are undefined. "
                   "Allocation charts are hidden.")
    else:
        left, right = st.columns(2)
        left.plotly_chart(stock_allocation_chart(by_stock), use_container_width=True)
        right.plotly_chart(sector_allocation_chart(by_sector), use_container_width=True)
    st.plotly_chart(pnl_chart(holdings), use_container_width=True)


def format_inr(value):
    """Format as rupees with Indian digit grouping, e.g. -₹1,23,456.78."""
    if pd.isna(value):
        return "N/A"
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join(groups + [tail])}.{frac}"


def format_pct(value):
    return "N/A" if pd.isna(value) else f"{value:+.2f}%"


def format_signed_inr(value):
    """Like format_inr but with an explicit + for gains."""
    return ("+" if not pd.isna(value) and value > 0 else "") + format_inr(value)


def colored(text, value):
    """Streamlit markdown color: green for gains, red for losses, plain otherwise."""
    if pd.isna(value) or value == 0:
        return text
    return f":{'green' if value > 0 else 'red'}[{text}]"


def delta_color(value):
    return "off" if pd.isna(value) or value == 0 else "normal"


def performer_card(label, entries, holding_count):
    """Metric card for best/worst performer, handling ties, one holding, and no data."""
    if not entries:
        st.metric(label, "N/A", help="No holding has a defined return (invested value is 0).")
        return
    pct = entries[0]["return_pct"]
    tickers = ", ".join(e["ticker"] for e in entries)
    st.metric(label, tickers, delta=f"{format_pct(pct)} return", delta_color=delta_color(pct))
    pnl = " · ".join(f"{e['ticker']}: {colored(format_signed_inr(e['pnl']), e['pnl'])}"
                     for e in entries)
    st.caption(f"P&L {pnl}")
    if holding_count == 1:
        st.caption("Only one holding, so it is both best and worst.")
    elif len(entries) > 1:
        st.caption(f"Tie: {len(entries)} holdings share this return.")


def show_summary(holdings):
    s = portfolio_summary(holdings)
    cols = st.columns(5)
    cols[0].metric("Total invested", format_inr(s["invested"]))
    cols[1].metric("Current value", format_inr(s["current"]))
    with cols[2]:
        st.metric("Unrealized P&L", format_signed_inr(s["pnl"]),
                  delta=f"{format_pct(s['return_pct'])} portfolio return",
                  delta_color=delta_color(s["pnl"]))
        st.caption("Total P&L ÷ total invested (not an average of holdings).")
    with cols[3]:
        performer_card("Best performer", s["best"], len(holdings))
    with cols[4]:
        performer_card("Worst performer", s["worst"], len(holdings))


def load_portfolio(data):
    """CSV bytes -> (holdings with metrics, errors)."""
    raw, errors = parse_csv(data)
    if errors:
        return None, errors
    clean, errors = validate_portfolio(raw)
    if errors:
        return None, errors
    return add_metrics(clean), []


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


def export_csv(df):
    """Filtered holdings with calculated columns as CSV bytes (N/A return -> blank)."""
    out = df.copy()
    out["buy_date"] = out["buy_date"].dt.strftime("%Y-%m-%d")
    return out.round(4).to_csv(index=False).encode()


def reset_filters():
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def sidebar_filters(holdings):
    """Render filter widgets and return apply_filters kwargs plus whether any is active."""
    first, last = holdings["buy_date"].min().date(), holdings["buy_date"].max().date()
    st.header("Filters")
    st.caption("Filters combine (a holding must match all of them). "
               "Leave a list empty to include everything.")
    search = st.text_input("Search company or ticker", key="f_search",
                           placeholder="e.g. steel or GANGA")
    sectors = st.multiselect("Sector", sorted(holdings["sector"].unique()), key="f_sectors")
    tickers = st.multiselect("Ticker", sorted(holdings["ticker"]), key="f_tickers")
    dates = st.date_input("Buy date", value=(first, last), min_value=first,
                          max_value=last, key="f_dates", format="YYYY-MM-DD")
    st.caption("Selects holdings by their **purchase date** (inclusive). "
               "It does not show historical portfolio performance.")
    status = st.radio("Status", STATUSES, horizontal=True, key="f_status")
    st.button("Reset filters", on_click=reset_filters, use_container_width=True)

    date_from = dates[0] if len(dates) > 0 else None
    date_to = dates[1] if len(dates) > 1 else None  # one date picked: open-ended until the second
    active = bool(search.strip() or sectors or tickers or status != "All"
                  or (date_from, date_to) != (first, last))
    return dict(search=search, sectors=sectors, tickers=tickers, date_from=date_from,
                date_to=date_to, status=status), active


def main():
    st.set_page_config(page_title="Stock Portfolio Analyzer", layout="wide")
    st.title("Stock Portfolio Analyzer")
    st.info(
        "Prices come from the CSV you supply and are **not live**. Results exclude "
        "dividends, fees, taxes, and realized trades."
    )

    sample_bytes = SAMPLE_PATH.read_bytes()
    with st.sidebar:
        st.header("Data")
        uploaded = st.file_uploader("Upload portfolio CSV", type="csv",
                                    help="Remove the uploaded file to return to sample data.")
        st.download_button("Download sample CSV", sample_bytes,
                           file_name="sample_portfolio.csv", mime="text/csv")
        st.caption("Required columns: " + ", ".join(REQUIRED_COLUMNS))

    if uploaded is None:
        data, source = sample_bytes, "sample_portfolio.csv"
        label = "**Sample data**: all holdings and prices are fictional."
    else:
        data, source = uploaded.getvalue(), uploaded.name
        label = f"**Uploaded data**: {uploaded.name}"

    # Filter values from a previous file may not exist in this one: start fresh.
    data_id = hashlib.sha256(data).hexdigest()
    if st.session_state.get("data_id") != data_id:
        reset_filters()
        st.session_state["data_id"] = data_id

    holdings, errors = load_portfolio(data)
    if errors:
        st.error(f"Could not load **{source}**. Fix these issues and upload again:")
        st.markdown("\n".join(f"- {e}" for e in errors))
        st.stop()

    with st.sidebar:
        filters, active = sidebar_filters(holdings)
    selected = apply_filters(holdings, **filters)

    note = " · **Filters active**" if active else ""
    st.caption(f"{label} · Showing **{len(selected)} of {len(holdings)}** holdings{note}")

    if selected.empty:
        st.warning("No holdings match the current filters. Widen the buy-date range, "
                   "clear the search, or choose status **All**.")
        st.button("Reset filters", on_click=reset_filters, key="reset_empty")
        st.stop()

    show_summary(selected)
    show_charts(selected)
    show_health(selected)
    show_table(selected, source, active)


def show_table(selected, source, active):
    st.subheader(f"Holdings ({len(selected)})")
    st.download_button(
        "Download filtered analysis CSV" if active else "Download analysis CSV",
        export_csv(selected), file_name=f"analysis_{Path(source).stem}.csv",
        mime="text/csv",
        help="Selected holdings with invested value, current value, P&L, return % and status.",
    )
    money = ["buy_price", "current_price", "invested_value", "current_value", "unrealized_pnl"]
    styled = selected.style.format(
        {**{c: format_inr for c in money},
         "unrealized_return_pct": format_pct,
         "quantity": "{:g}",
         "buy_date": lambda d: d.strftime("%Y-%m-%d")}
    )
    st.dataframe(styled, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
