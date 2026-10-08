# Stock Portfolio Analyzer

A Streamlit app that reads a portfolio of Indian (₹ INR) or US ($ USD) stock holdings from a CSV file. It checks the file for errors and shows:

- summary cards
- interactive Plotly charts
- a concentration-focused Portfolio Health view
- a holdings table you can filter and download

It was built as a Week 1 vibe-coding project, using an AI coding assistant.

> **Important:**
> - All holdings and prices in `sample_portfolio.csv` (India) and `sample_portfolio_us.csv` (USA) are **fictional**.
> - The app uses only the prices in your CSV. It does **not** fetch live prices.
> - Results exclude dividends, fees, taxes, and realized trades.
> - Nothing in the app is investment advice.

## Features

- **Market:** choose India (₹ INR) or USA ($ USD) in the sidebar. This sets the currency for every card, chart, the summary, the table and the export, and picks which fictional sample loads. Values are not converted between currencies, so one CSV must use one currency.
- **Data:** the app opens with fictional sample data. You can upload your own CSV and download the sample CSV.
- **Validation:** an invalid file is rejected as a whole. Every problem is listed with its CSV row number. The app never drops bad rows silently and never switches back to the sample data without telling you.
- **Summary cards:**
  - Total invested and current value.
  - Unrealized P&L in money and as a percentage.
  - Best and worst performer, which handle ties, a single holding, and holdings with an N/A return.
- **Charts:**
  - Allocation by stock (donut).
  - Allocation by sector (bar).
  - Unrealized P&L by stock (bar, green for gain and red for loss, with signed labels).
- **Portfolio Health (concentration analysis):**
  - The largest holding and its weight.
  - The combined weight of the top three holdings.
  - The largest sector.
  - Counts of gains, losses, and unchanged holdings.
  - A plain-English summary written automatically from those calculated figures.
- **Filters:** search by company or ticker, sector, ticker, buy-date range (includes both end dates), and status (All, Gain, Loss, or Unchanged). Every card, chart, the health view, the table, and the export use the same filtered holdings. **Reset filters** clears them, and they also reset when you upload a different file.
- **Export:** downloads the selected holdings with all calculated columns and a `currency` column.
- **Formatting:** India uses ₹ with Indian digit grouping (₹12,34,567.89); USA uses $ with thousands grouping ($1,234,567.89). Returns are signed percentages.

## CSV schema

There must be one row per ticker, with a header row containing these columns (extra columns are ignored):

| Column | Type | Rule |
|---|---|---|
| `ticker` | text | Required. Spaces are trimmed and letters uppercased. Must be unique. |
| `company_name` | text | Required. |
| `sector` | text | Required. |
| `quantity` | number | Must be greater than 0. |
| `buy_price` | number (₹ or $) | Must be 0 or more and a finite number. |
| `buy_date` | date | Must be exactly `YYYY-MM-DD`, for example `2024-01-18`. |
| `current_price` | number (₹ or $) | Must be 0 or more and a finite number. |

The file must be saved as UTF-8; a "CSV UTF-8" file from Excel works. Blank lines are ignored. A row with too many or too few values is reported as an error.

Example:

```csv
ticker,company_name,sector,quantity,buy_price,buy_date,current_price
AARVITECH,Aarvi Technologies,Information Technology,25,1450.00,2023-04-12,1782.50
```

## Formulas

| Value | Formula |
|---|---|
| invested_value | quantity × buy_price |
| current_value | quantity × current_price |
| unrealized_pnl | current_value − invested_value |
| unrealized_return_pct | unrealized_pnl ÷ invested_value × 100. Shows N/A when invested_value is 0. |
| Portfolio return % | total unrealized_pnl ÷ total invested_value × 100. This is not an average of the holdings' returns. Shows N/A when total invested is 0. |
| Weight % | holding (or sector) current_value ÷ total current_value × 100. Undefined when the total is 0, in which case weight charts and figures are hidden and a message explains why. |
| Status | Gain if P&L > 0, Loss if P&L < 0, otherwise Unchanged. |

Best and worst performers are ranked by return %. Holdings with an N/A return are left out of the ranking.

## Limitations

- The CSV is a single **snapshot**, so the app does not show historical performance, volatility, maximum drawdown, or benchmark comparisons. Adding those would need historical price data and holdings or transaction history.
- Portfolio Health only describes **concentration**. It is not a comprehensive risk score.
- The summary text is written by fixed rules from the calculated figures. No AI service is involved.
- Only one row per ticker is allowed, so multiple buy lots and partial sales can't be entered.
- Prices are only as up to date as your CSV.
- Dividends, fees, taxes, corporate actions, and realized P&L are not included.

## Setup and run

The app was tested on Python 3.12 with the versions pinned in `requirements.txt`. Other Python 3 versions have not been tested.

### macOS / Linux

```bash
cd stock-portfolio-analyzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Windows (PowerShell)

```powershell
cd stock-portfolio-analyzer
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks the activation script, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. In cmd.exe, use `.venv\Scripts\activate.bat` instead.

The app opens at http://localhost:8501. Press `Ctrl+C` in the terminal to stop it.

## Checks

```bash
python test_app.py
```

The checks cover:

- parsing and validation
- the formulas, including a hand-checked AAA/BBB example
- ties, a single holding, and zero values
- allocation weights, and that the charts match the table
- filters, including date boundaries, combined filters, and empty results
- the exported rows
- the health figures and summary text
- a headless run of the app that tests filters and reset

## Uploading to GitHub

`.gitignore` already excludes virtual environments, `.env` files, Streamlit secrets, the local `.claude/` settings folder, and **every CSV except the two sample files**. That keeps your private portfolio files and exported analysis out of the repository.

1. Create an **empty** repository on GitHub. Don't add a README or .gitignore there, because this project already has them.
2. In the project folder, run:

   ```bash
   git init
   git add .
   git status   # check the list before committing
   ```

3. Check that `git status` lists only these files:
   - `app.py`
   - `test_app.py`
   - `requirements.txt`
   - `sample_portfolio.csv`
   - `sample_portfolio_us.csv`
   - `README.md`
   - `submission_notes.txt`
   - `demo_script.txt`
   - `.gitignore`

   It must **not** list `.venv/`, any other `.csv` file, `.env`, or anything in `.claude/`.
4. Commit and push:

   ```bash
   git commit -m "Stock Portfolio Analyzer: Week 1"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

If a private file was ever committed, removing it in a later commit is not enough, because it stays in the git history. Remove it from the history before pushing, or start a fresh repository.
