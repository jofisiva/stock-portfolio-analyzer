# Layout A: implementation changes

Copy these files into `stock-portfolio-analyzer/`, replacing the old ones:

- `app.py` (replaces the old one)
- `theme.py` (new)
- `.streamlit/config.toml` (new; the folder starts with a dot, so it may be hidden)

Then run `python test_app.py`, then `streamlit run app.py`.

## What changed
- **Theme**: Broadsheet styling. Source Serif 4 everywhere, a paper background and a pale sidebar. Radios now look like segmented buttons, download buttons look like plain cyan links, and the dashed upload box is restyled. Plotly charts share one theme set in `theme.py`.
- **Gain / loss colours**: green and red become cyan `#0088b0` and magenta `#d6006c`. Text uses darker shades of each so it stays readable.
- **No boxes**: info and warning boxes now show as plain italic text. The health summary is a 21px italic pull quote, and the XIRR notes are magenta text with a ⚠.
- **Charts**:
  - The donut has neutral grey slices with the holdings count and total in the middle.
  - The sector bars are dark grey, and **clicking a bar toggles that sector filter**.
  - P&L value labels are coloured by sign.
- **Upload error screen**: shows every problem by row, beside a preview of the file with the bad cells marked. Hovering a problem highlights its row. A "Use sample data instead" button removes the bad file.
- **No-matches state**: lists "Remove *filter* · N holdings back" buttons, sorted by how many holdings each would bring back, plus "Reset all filters".
- **Table**: friendly column names, sorted by current value (largest first), P&L, Return and Status coloured by sign, and the ticker in bold.

## Kept on purpose, so `test_app.py` passes unchanged
- All calculations, validation and formatting functions are the same.
- The 10 metrics, the first caption (the "Showing N of M" line) and the two info elements (the top note, then the health summary) are kept.
- The widget keys (`f_*`, `market`, `reset_empty`) are kept.
- `stock_allocation_chart` and `sector_allocation_chart` gained optional arguments only.
- The ticker filter stays in the sidebar.

## Not done (Streamlit limits)
- **Hover sync** between the charts and the table.
- **Two-line ticker / company cells.**
- **Tag-style status cells**: shown as coloured text instead.
- **The first-run screen**: the app still loads the sample right away, as the tests expect. Say if you want it added behind a `started` flag.

The CSS targets Streamlit 1.37's internal names. If styling breaks after an upgrade, check the selectors in `theme.py`.
