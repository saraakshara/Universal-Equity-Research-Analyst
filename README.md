# Universal Equity Research Analyst

Customer enters a public-company name or ticker. The app resolves the listed security, gathers available public financial and market data, validates it, calculates research metrics, dynamically discovers candidate industry peers, and produces an explainable analyst-style research workspace with Excel/PDF export.

## Key capabilities
- Universal company/ticker resolution with ETF/fund filtering and common brand aliases
- Yahoo Finance structured financials with official/regulatory fallback where supported
- Robust financial-statement orientation handling and calculated ratios when source providers do not pre-calculate them
- Revenue growth, margins, ROE/ROA, leverage, liquidity, cash conversion and FCF metrics
- Descriptive valuation multiples and simplified DCF sensitivity
- Dynamic peer discovery using public market industry context, followed by peer metric collection
- Peer median reference statistics
- Risk flags, validation checks and analyst investigation questions
- Business profile, sources and downloadable Excel/PDF research output
- Missing information is shown as unavailable rather than fabricated

## Run
```powershell
py -m venv .venv
.venv\\Scripts\\activate
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Peer analysis note
Peer discovery is a candidate set, not an automatic investment recommendation. The app uses the market-data provider's industry universe where available and labels the output for analyst verification. The underlying yfinance screener supports industry, sector, exchange and peer-group filters; the application uses industry context for broader cross-company coverage. 
