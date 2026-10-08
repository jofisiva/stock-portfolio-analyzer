"""Self-checks for loading, validation, and calculations. Run: python test_app.py"""

import io
import math
from datetime import date

import pandas as pd

from app import (FLAT, GAIN, LOSS, SAMPLE_PATH, allocation, apply_filters, export_csv,
                 format_inr, format_pct,
                 format_signed_inr, health_summary, load_portfolio, pnl_chart,
                 portfolio_health, portfolio_summary,
                 sector_allocation_chart, stock_allocation_chart)

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
    df, errors = load_portfolio(SAMPLE_PATH.read_bytes())
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
    assert "Row 2: buy_price 'nan'" in errors_for("A,Co,X,1,nan,2024-01-01,10\n")
    assert "Row 2: quantity must be greater than 0" in errors_for("A,Co,X,0,10,2024-01-01,10\n")
    assert "Row 2: current_price must be 0 or more" in errors_for("A,Co,X,1,10,2024-01-01,-1\n")
    msg = errors_for("abc,Co,X,1,10,2024-01-01,10\n ABC ,Co,X,1,10,2024-01-01,10\n")
    assert "Duplicate ticker ABC in rows 2, 3" in msg


def test_allocation_weights():
    df = load("AAA,A Co,X,10,100,2024-01-01,120\n"
              "BBB,B Co,Y,5,200,2024-01-01,180\n")
    w = allocation(df, "ticker").set_index("ticker")["weight_pct"]
    assert round(w["AAA"], 2) == 57.14 and round(w["BBB"], 2) == 42.86
    assert allocation(load("AAA,A,X,1,100,2024-01-01,0\n"), "ticker") is None


def test_charts_match_table():
    df, _ = load_portfolio(SAMPLE_PATH.read_bytes())
    total = df["current_value"].sum()
    by_ticker = df.set_index("ticker")

    pie = stock_allocation_chart(allocation(df, "ticker")).data[0]
    assert dict(zip(pie.labels, pie.values)) == by_ticker["current_value"].to_dict()

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
    df, _ = load_portfolio(SAMPLE_PATH.read_bytes())
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
    df, _ = load_portfolio(SAMPLE_PATH.read_bytes())
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
    assert not at.exception and len(at.metric) == 9
    assert "10 of 10" in at.caption[0].value and "Filters active" not in at.caption[0].value

    at.radio(key="f_status").set_value("Loss").run()
    assert "4 of 10" in at.caption[0].value and "Filters active" in at.caption[0].value
    assert len(at.dataframe[0].value) == 4

    at.text_input(key="f_search").set_value("zzz").run()  # nothing matches
    assert "0 of 10" in at.caption[0].value
    assert at.warning and not at.metric and not at.dataframe and not at.get("plotly_chart")

    at.button(key="reset_empty").click().run()
    assert at.radio(key="f_status").value == "All" and at.text_input(key="f_search").value == ""
    assert "10 of 10" in at.caption[0].value and len(at.metric) == 9

    # A different data file (simulated by a changed fingerprint) clears filters.
    at.radio(key="f_status").set_value("Gain").run()
    at.session_state["data_id"] = "other-file"
    at.run()
    assert at.radio(key="f_status").value == "All" and "10 of 10" in at.caption[0].value


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
    df, _ = load_portfolio(SAMPLE_PATH.read_bytes())
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


def test_format_inr():
    assert format_inr(1234567.891) == "₹12,34,567.89"
    assert format_inr(-999.5) == "-₹999.50"
    assert format_inr(0) == "₹0.00"
    assert format_signed_inr(100) == "+₹100.00"
    assert format_signed_inr(-100) == "-₹100.00"
    assert format_signed_inr(0) == "₹0.00"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all checks passed")
