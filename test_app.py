"""Self-checks for loading, validation, and calculations. Run: python test_app.py"""

import io
import math
from datetime import date

import pandas as pd
from pathlib import Path

from app import (FLAT, GAIN, LOSS, MARKETS, OTHER, ticker_colors, SAMPLE_PATH, allocation,
                 apply_filters, export_csv, format_money, format_pct, portfolio_xirr, xirr,
                 format_signed_money, health_summary, load_portfolio, pnl_chart,
                 portfolio_health, portfolio_summary,
                 sector_allocation_chart, stock_allocation_chart)

# The calculation checks use fixed fictional fixtures, not the app's sample files,
# so the samples can change without breaking the expected numbers.
FIXTURES = Path(__file__).parent / "test_data"
FIXTURE_INDIA = FIXTURES / "fictional_india.csv"
FIXTURE_USA = FIXTURES / "fictional_usa.csv"

HEADER = "ticker,company_name,sector,quantity,buy_price,buy_date,current_price\n"


def load(body):
    df, errors = load_portfolio((HEADER + body).encode())
    assert errors == [], errors
    return df


def test_independent_example():
    # Hand-checked example, kept out of sample_portfolio.csv on purpose.
    df = load("AAA,A Co,X,10,100,2024-01-01,120\n"
              "BBB,B Co,Y,5,200,2024-01-01,180\n")
    s = portfolio_summary(df)
    assert s["invested"] == 2000 and s["current"] == 2100 and s["pnl"] == 100
    assert math.isclose(s["return_pct"], 5.0)
    pct = df.set_index("ticker")["unrealized_return_pct"]
    assert math.isclose(pct["AAA"], 20.0) and math.isclose(pct["BBB"], -10.0)
    # The mean of individual returns would be 5.0 here too; this case is not:
    df2 = load("AAA,A Co,X,1,100,2024-01-01,200\nBBB,B Co,Y,100,100,2024-01-01,90\n")
    assert math.isclose(portfolio_summary(df2)["return_pct"], -900 / 10100 * 100)
    assert s["best"] == [{"ticker": "AAA", "return_pct": 20.0, "pnl": 200.0}]
    assert s["worst"] == [{"ticker": "BBB", "return_pct": -10.0, "pnl": -100.0}]


def test_ties_single_and_undefined():
    tie = portfolio_summary(load("AAA,A,X,1,100,2024-01-01,110\n"
                                 "BBB,B,X,3,50,2024-01-01,55\n"
                                 "CCC,C,X,1,100,2024-01-01,90\n"))
    assert [e["ticker"] for e in tie["best"]] == ["AAA", "BBB"]
    assert [e["ticker"] for e in tie["worst"]] == ["CCC"]

    one = portfolio_summary(load("AAA,A,X,2,100,2024-01-01,90\n"))
    assert one["best"] == one["worst"] and one["best"][0]["ticker"] == "AAA"

    # Zero-cost holding: excluded from ranking; all zero cost -> N/A everywhere.
    mixed = portfolio_summary(load("FREE,F,X,1,0,2024-01-01,500\n"
                                   "AAA,A,X,1,100,2024-01-01,90\n"))
    assert [e["ticker"] for e in mixed["best"]] == ["AAA"]
    none = portfolio_summary(load("FREE,F,X,1,0,2024-01-01,500\n"))
    assert math.isnan(none["return_pct"]) and none["best"] == [] and none["worst"] == []
    assert format_pct(none["return_pct"]) == "N/A"


def errors_for(body):
    df, errors = load_portfolio((HEADER + body).encode())
    assert df is None, "expected rejection"
    return " | ".join(errors)


def test_sample_loads():
    df, errors = load_portfolio(FIXTURE_INDIA.read_bytes())
    assert errors == [] and len(df) == 10
    assert (df["unrealized_pnl"] > 0).any() and (df["unrealized_pnl"] < 0).any()
    assert (df["unrealized_pnl"] == 0).any()
    row = df.set_index("ticker").loc["AARVITECH"]
    assert row["invested_value"] == 25 * 1450
    assert abs(row["unrealized_return_pct"] - (1782.5 - 1450) / 1450 * 100) < 1e-9


def test_zero_invested_is_na():
    df, errors = load_portfolio((HEADER + "abc,A,X,1,0,2024-01-01,10\n").encode())
    assert errors == [] and df.loc[0, "ticker"] == "ABC"
    assert format_pct(df.loc[0, "unrealized_return_pct"]) == "N/A"


def test_rejections():
    assert "empty" in load_portfolio(b"")[1][0]
    assert "no holdings" in load_portfolio(HEADER.encode())[1][0]
    assert "Missing required column" in load_portfolio(b"ticker,sector\nA,X\n")[1][0]
    assert "Row 2: missing value(s) in sector" in errors_for("A,Co,,1,10,2024-01-01,10\n")
    assert "Row 2: buy_date '2024-02-30'" in errors_for("A,Co,X,1,10,2024-02-30,10\n")
    assert "Row 2: quantity '1e999'" in errors_for("A,Co,X,1e999,10,2024-01-01,10\n")
    assert "Row 2: quantity x buy_price is too large" in errors_for(
        "A,Co,X,1e308,1e308,2024-01-01,10\n"
    )
    # Overflow is reported on the real CSV line, after a blank line.
    assert "Row 4: quantity x current_price is too large" in errors_for(
        "A,Co,X,1,10,2024-01-01,10\n\nB,Co,X,1e200,1,2024-01-01,1e200\n"
    )
    assert "Row 2: buy_price 'nan'" in errors_for("A,Co,X,1,nan,2024-01-01,10\n")
    assert "Row 2: quantity must be greater than 0" in errors_for("A,Co,X,0,10,2024-01-01,10\n")
    assert "Row 2: current_price must be 0 or more" in errors_for("A,Co,X,1,10,2024-01-01,-1\n")
    msg = errors_for("abc,Co,X,1,10,2024-01-01,10\n ABC ,Co,X,1,10,2024-01-01,10\n")
    assert "Duplicate ticker ABC in rows 2, 3" in msg
    # Header plus only blank lines: rejected as having no holdings, not silently accepted.
    blank_row = load_portfolio((HEADER + "\n  \n").encode())
    assert blank_row[0] is None and "no holdings rows" in blank_row[1][0]


def test_allocation_weights():
    df = load("AAA,A Co,X,10,100,2024-01-01,120\n"
              "BBB,B Co,Y,5,200,2024-01-01,180\n")
    w = allocation(df, "ticker").set_index("ticker")["weight_pct"]
    assert round(w["AAA"], 2) == 57.14 and round(w["BBB"], 2) == 42.86
    assert allocation(load("AAA,A,X,1,100,2024-01-01,0\n"), "ticker") is None


def test_charts_match_table():
    df, _ = load_portfolio(FIXTURE_INDIA.read_bytes())
    total = df["current_value"].sum()
    by_ticker = df.set_index("ticker")

    pie = stock_allocation_chart(allocation(df, "ticker")).data[0]
    slices = dict(zip(pie.labels, pie.values))
    # The 8 largest get their own slice with their table value; the other 2 fold into Other.
    top8 = df.nlargest(8, "current_value")["ticker"]
    assert all(slices[t] == by_ticker.loc[t, "current_value"] for t in top8)
    assert math.isclose(slices["Other (2)"],
                        by_ticker.drop(list(top8))["current_value"].sum())
    assert math.isclose(sum(pie.values), total) and len(set(pie.marker.colors)) == 9
    # A filtered view keeps each ticker's colour from the full portfolio.
    colors = ticker_colors(df)
    small = apply_filters(df, status="Loss")
    pie2 = stock_allocation_chart(allocation(small, "ticker"), colors=colors).data[0]
    for label, color in zip(pie2.labels, pie2.marker.colors):
        assert color == colors.get(label, OTHER) or label.startswith("Other")

    sector = sector_allocation_chart(allocation(df, "sector")).data[0]
    expected = (df.groupby("sector")["current_value"].sum() / total * 100).to_dict()
    assert all(math.isclose(w, expected[s]) for s, w in zip(sector.y, sector.x))
    assert math.isclose(sum(sector.x), 100)

    bar = pnl_chart(df).data[0]
    assert dict(zip(bar.x, bar.y)) == by_ticker["unrealized_pnl"].to_dict()
    assert list(bar.y) == sorted(bar.y, reverse=True)
    colors = dict(zip(bar.x, bar.marker.color))
    assert colors["AARVITECH"] == GAIN and colors["JALTEL"] == LOSS
    assert colors["CHANDRAPHR"] == FLAT


def test_filters():
    df, _ = load_portfolio(FIXTURE_INDIA.read_bytes())
    tickers = lambda d: sorted(d["ticker"])

    assert len(apply_filters(df)) == 10
    assert tickers(apply_filters(df, status="Unchanged")) == ["CHANDRAPHR"]
    assert len(apply_filters(df, status="Gain")) == 5
    assert len(apply_filters(df, status="Loss")) == 4
    # Search: case-insensitive, ticker or company name, plain text (no regex).
    assert tickers(apply_filters(df, search="  steel ")) == ["GANGASTEEL"]
    assert tickers(apply_filters(df, search="aarvi")) == ["AARVITECH"]
    assert apply_filters(df, search=".*").empty

    # Inclusive boundaries: DEVAGRID bought 2023-07-25, HIMRAIL 2023-09-14.
    d = lambda s: date.fromisoformat(s)
    assert tickers(apply_filters(df, date_from=d("2023-07-25"), date_to=d("2023-09-14"))) \
        == ["DEVAGRID", "HIMRAIL"]
    assert tickers(apply_filters(df, date_from=d("2023-07-26"), date_to=d("2023-09-13"))) == []
    assert tickers(apply_filters(df, date_from=d("2023-07-25"), date_to=d("2023-07-25"))) \
        == ["DEVAGRID"]

    # Combined: 2023 purchases that are losses in Industrials or Communication Services.
    combo = apply_filters(df, sectors=["Industrials", "Communication Services", "Utilities"],
                          date_from=d("2023-01-01"), date_to=d("2023-12-31"), status="Loss")
    assert tickers(combo) == ["HIMRAIL", "JALTEL"]
    # Contradictory filters -> empty, summary not computed from stale rows.
    assert apply_filters(df, tickers=["AARVITECH"], status="Loss").empty

    # Summary uses only the filtered rows.
    s = portfolio_summary(combo)
    assert s["invested"] == 80 * 265.50 + 200 * 78.25
    assert [e["ticker"] for e in s["best"]] == ["HIMRAIL"]


def test_export_rows():
    df, _ = load_portfolio(FIXTURE_INDIA.read_bytes())
    sel = apply_filters(df, status="Loss")
    out = pd.read_csv(io.BytesIO(export_csv(sel)))
    assert sorted(out["ticker"]) == sorted(sel["ticker"]) and len(out) == 4
    for col in ["invested_value", "current_value", "unrealized_pnl",
                "unrealized_return_pct", "status"]:
        assert col in out.columns
    row = out.set_index("ticker").loc["JALTEL"]
    assert row["buy_date"] == "2023-02-27" and row["unrealized_pnl"] == -2690
    assert row["unrealized_return_pct"] == round(-2690 / 15650 * 100, 4)
    # N/A return exports as a blank cell.
    free = pd.read_csv(io.BytesIO(export_csv(load("F,F,X,1,0,2024-01-01,5\n"))))
    assert pd.isna(free.loc[0, "unrealized_return_pct"])


def test_app_filter_reset_and_empty():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py").run(timeout=30)
    assert not at.exception and len(at.metric) == 10
    assert "10 of 10" in at.caption[0].value and "Filters active" not in at.caption[0].value

    at.radio(key="f_status").set_value("Loss").run()
    assert "3 of 10" in at.caption[0].value and "Filters active" in at.caption[0].value
    assert len(at.dataframe[0].value) == 3

    at.text_input(key="f_search").set_value("zzz").run()  # nothing matches
    assert "0 of 10" in at.caption[0].value
    assert at.warning and not at.metric and not at.dataframe and not at.get("plotly_chart")

    at.button(key="reset_empty").click().run()
    assert at.radio(key="f_status").value == "All" and at.text_input(key="f_search").value == ""
    assert "10 of 10" in at.caption[0].value and len(at.metric) == 10

    # A different data file (simulated by a changed fingerprint) clears filters.
    at.radio(key="f_status").set_value("Gain").run()
    at.session_state["data_id"] = "other-file"
    at.run()
    assert at.radio(key="f_status").value == "All" and "10 of 10" in at.caption[0].value


def test_app_market_switch():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("app.py").run(timeout=30)
    assert at.metric[0].value.startswith("₹") and "India" in at.caption[0].value

    at.radio(key="f_status").set_value("Loss").run()
    at.radio(key="market").set_value("USA ($ USD)").run()
    assert not at.exception
    # The US sample loaded, filters reset, and no ₹ appears in cards or table.
    assert "USA" in at.caption[0].value and "10 of 10" in at.caption[0].value
    assert at.radio(key="f_status").value == "All"
    values = [m.value for m in at.metric[:3]]
    assert all("$" in v and "₹" not in v for v in values), values
    assert "AAPL" in set(at.dataframe[0].value["ticker"])
    assert "$" in at.info[1].value and "₹" not in at.info[1].value  # health summary


def test_parsing_edge_cases():
    # Excel's UTF-8 BOM and blank lines are accepted.
    df, errors = load_portfolio(b"\xef\xbb\xbf" + HEADER.encode()
                                + b"AAA,A,X,1,10,2024-01-01,10\n\n")
    assert errors == [] and list(df["ticker"]) == ["AAA"]
    # Row numbers stay correct after a blank line.
    assert "Row 4: quantity 'x'" in errors_for("AAA,A,X,1,10,2024-01-01,10\n\n"
                                               "BBB,B,X,x,10,2024-01-01,10\n")
    # Too many / too few fields is reported, not silently shifted.
    assert "Row 2: expected 7 values but found 8" in errors_for("A,Co,X,1,10,2024-01-01,10,9\n")
    assert "Row 2: expected 7 values but found 2" in errors_for("A,Co\n")
    # YYYY-MM-DD only.
    assert "Row 2: buy_date '2024-1-5'" in errors_for("A,Co,X,1,10,2024-1-5,10\n")
    assert "Row 2: buy_date '05/01/2024'" in errors_for("A,Co,X,1,10,05/01/2024,10\n")
    assert "not UTF-8" in load_portfolio(b"\xff\xfe\x00bad")[1][0]
    # Quoted commas inside a company name are fine.
    assert load("AAA,\"Aarvi, Ltd\",X,1,10,2024-01-01,10\n").loc[0, "company_name"] \
        == "Aarvi, Ltd"


def test_health():
    df, _ = load_portfolio(FIXTURE_INDIA.read_bytes())
    h = portfolio_health(df)
    total = df["current_value"].sum()
    top3 = df.nlargest(3, "current_value")
    assert h["largest"] == (["AARVITECH"], df["current_value"].max() / total * 100)
    assert h["top"][0] == list(top3["ticker"])
    assert math.isclose(h["top"][1], top3["current_value"].sum() / total * 100)
    assert h["sector"][0] == ["Information Technology"]
    assert (h["gains"], h["losses"], h["unchanged"]) == (5, 4, 1)
    text = health_summary(h)
    assert "AARVITECH at 15.73%" in text and "5 holdings show an unrealized gain" in text
    for word in ("buy", "sell", "risk score", "volatility", "AI", "LLM"):
        assert word not in text, word

    # AAA/BBB example: 2 holdings, weights 57.14 / 42.86.
    two = portfolio_health(load("AAA,A,X,10,100,2024-01-01,120\nBBB,B,Y,5,200,2024-01-01,180\n"))
    assert two["largest"][0] == ["AAA"] and round(two["largest"][1], 2) == 57.14
    assert math.isclose(two["top"][1], 100)
    assert "All 2 holdings together make up 100.00%" in health_summary(two)

    one = health_summary(portfolio_health(load("AAA,A,X,1,10,2024-01-01,10\n")))
    assert "AAA is the only holding" in one and "1 holding shows" not in one

    tie = portfolio_health(load("AAA,A,X,1,100,2024-01-01,100\nBBB,B,Y,1,100,2024-01-01,100\n"))
    assert tie["largest"][0] == ["AAA", "BBB"] and tie["sector"][0] == ["X", "Y"]
    assert "each at 50.00%" in health_summary(tie)

    zero = portfolio_health(load("AAA,A,X,1,100,2024-01-01,0\n"))
    assert zero["largest"] is None and zero["losses"] == 1
    assert "cannot be calculated" in health_summary(zero)


def test_xirr():
    # Excel's documented XIRR example: result 0.373362535 (37.34%).
    flows = [(date(2008, 1, 1), -10000), (date(2008, 3, 1), 2750), (date(2008, 10, 30), 4250),
             (date(2009, 2, 15), 3250), (date(2009, 4, 1), 2750)]
    assert abs(xirr(flows) - 37.3362535) < 1e-4

    as_of = date(2025, 1, 1)
    # One holding doubled over 1827 days: XIRR = 2^(365/1827) - 1.
    one = load("AAA,A,X,10,100,2020-01-01,200\n")
    assert math.isclose(portfolio_xirr(one, as_of), (2 ** (365 / 1827) - 1) * 100, abs_tol=1e-6)

    # Two buys a year apart: the rate must make NPV zero.
    two = load("AAA,A,X,10,100,2020-01-01,150\nBBB,B,X,10,100,2021-01-01,100\n")
    r = portfolio_xirr(two, as_of) / 100
    npv = (-1000 - 1000 / (1 + r) ** (366 / 365)
           + 2500 / (1 + r) ** ((as_of - date(2020, 1, 1)).days / 365))
    assert abs(npv) < 1e-6
    # It differs from the simple return (25%) because money was invested at different times.
    assert 4 < r * 100 < 7

    assert portfolio_xirr(load("AAA,A,X,1,100,2020-01-01,0\n"), as_of) == -100.0
    assert math.isnan(portfolio_xirr(load("AAA,A,X,1,100,2026-01-01,120\n"), as_of))
    assert math.isnan(portfolio_xirr(load("AAA,A,X,1,0,2020-01-01,120\n"), as_of))
    # A very old buy date near -100% must not crash on overflow.
    assert -100 < portfolio_xirr(load("AAA,A,X,1,100,1900-01-01,0.0001\n"), as_of) < 0


def test_format_money():
    assert format_money(1234567.891) == "₹12,34,567.89"
    assert format_money(-999.5) == "-₹999.50"
    assert format_money(0) == "₹0.00"
    assert format_signed_money(100) == "+₹100.00"
    assert format_signed_money(-100) == "-₹100.00"
    assert format_signed_money(0) == "₹0.00"
    assert format_money(1234567.891, "USD") == "$1,234,567.89"
    assert format_signed_money(-2690, "USD") == "-$2,690.00"
    assert format_signed_money(53.06, "USD") == "+$53.06"
    assert format_money(float("nan"), "USD") == "N/A"


def test_us_sample_and_currency_outputs():
    df, errors = load_portfolio(FIXTURE_USA.read_bytes())
    assert errors == [] and len(df) == 10
    assert set(df["status"]) == {"Gain", "Loss", "Unchanged"}
    fig = pnl_chart(df, "USD")
    assert fig.layout.yaxis.tickprefix == "$" and "$" in fig.layout.title.text
    assert all("₹" not in t for t in fig.data[0].text)
    assert "$" in allocation(df, "ticker", "USD")["value_label"].iloc[0]
    assert "$" in health_summary(portfolio_health(df), "USD")
    out = pd.read_csv(io.BytesIO(export_csv(df, "USD")))
    assert set(out["currency"]) == {"USD"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all checks passed")
