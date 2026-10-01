from __future__ import annotations
import os, re, requests, yfinance as yf

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Common public-brand/company-name aliases. These are resolver hints, not a fixed universe.
# They prevent search engines from selecting an unrelated ETF/fund when a well-known
# public company is entered by its consumer-facing name.
ALIASES = {
    "google": ["GOOGL", "GOOG"],
    "google inc": ["GOOGL", "GOOG"],
    "alphabet": ["GOOGL", "GOOG"],
    "facebook": ["META"],
    "meta platforms": ["META"],
    "instagram": ["META"],
    "youtube": ["GOOGL", "GOOG"],
    "tesla motors": ["TSLA"],
    "shell": ["SHEL"],
    "jpmorgan": ["JPM"],
    "jp morgan": ["JPM"],
    "jpmorgan chase": ["JPM"],
}


def _sec_headers():
    ua = os.getenv("SEC_USER_AGENT", "UniversalEquityResearch/1.1 contact@example.com")
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate", "Host": "www.sec.gov"}


def sec_ticker_map():
    try:
        r = requests.get(SEC_TICKERS_URL, headers=_sec_headers(), timeout=12)
        r.raise_for_status()
        data = r.json()
        return [{
            "ticker": str(row.get("ticker", "")).upper(),
            "name": row.get("title", ""),
            "cik": str(row.get("cik_str", "")).zfill(10),
        } for row in data.values()]
    except Exception:
        return []


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _is_etf_or_fund(c):
    qt = str(c.get("quoteType", "")).upper()
    text = _norm(f"{c.get('longname','')} {c.get('shortname','')}")
    return qt in {"ETF", "MUTUALFUND", "FUND"} or " etf " in f" {text} "


def resolve_company(query: str):
    q = query.strip()
    if not q:
        raise ValueError("Enter a company name or ticker.")
    ql = _norm(q)
    candidates = []

    # 1) Deterministic aliases first for well-known public-company brands.
    alias_symbols = ALIASES.get(ql, [])
    for sym in alias_symbols:
        candidates.append({
            "symbol": sym,
            "shortname": "Alphabet Inc." if sym in {"GOOG", "GOOGL"} else sym,
            "longname": "Alphabet Inc." if sym in {"GOOG", "GOOGL"} else sym,
            "exchange": "NMS",
            "quoteType": "EQUITY",
            "alias_match": True,
        })

    # 2) Yahoo public search for the global universe. ETFs/funds are excluded unless
    # the user explicitly asks for one.
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        params = {"q": q, "quotesCount": 25, "newsCount": 0}
        r = requests.get(url, params=params, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        for item in r.json().get("quotes", []):
            if item.get("quoteType") == "EQUITY" or ("etf" in ql and item.get("quoteType") == "ETF"):
                candidates.append(item)
    except Exception:
        pass

    # 3) SEC company ticker universe for US-listed issuers. This helps map names such
    # as Alphabet even when Yahoo's ranking is noisy.
    if not alias_symbols:
        sec_rows = sec_ticker_map()
        for row in sec_rows:
            ticker = row["ticker"]
            name = row["name"]
            n = _norm(name)
            if ql == _norm(ticker) or ql == n or ql in n or n in ql:
                candidates.append({
                    "symbol": ticker, "shortname": name, "longname": name,
                    "exchange": "US", "quoteType": "EQUITY", "cik": row["cik"],
                    "sec_match": True,
                })

    # 4) Direct ticker fallback.
    if not candidates:
        try:
            t = yf.Ticker(q.upper())
            info = t.fast_info
            price = getattr(info, "last_price", None)
            if price is not None:
                candidates.append({"symbol": q.upper(), "shortname": q.upper(), "longname": q.upper(), "exchange": "", "quoteType": "EQUITY"})
        except Exception:
            pass

    if not candidates:
        raise ValueError("Company/ticker could not be resolved from the available public sources.")

    def score(c):
        sym = _norm(str(c.get("symbol", "")))
        nm = _norm(str(c.get("longname", c.get("shortname", ""))))
        s = 0
        if c.get("alias_match"): s += 300
        if c.get("sec_match"): s += 80
        if sym == ql: s += 220
        if nm == ql: s += 180
        if ql in nm: s += 70
        if nm.startswith(ql): s += 25
        if c.get("quoteType") == "EQUITY": s += 20
        if _is_etf_or_fund(c) and "etf" not in ql: s -= 500
        return s

    # Remove duplicate symbols while retaining the strongest candidate.
    by_symbol = {}
    for c in candidates:
        sym = str(c.get("symbol", "")).upper()
        if sym and (sym not in by_symbol or score(c) > score(by_symbol[sym])):
            by_symbol[sym] = c
    candidates = list(by_symbol.values())
    candidates.sort(key=score, reverse=True)
    c = candidates[0]
    symbol = c.get("symbol") or c.get("ticker")

    return {
        "symbol": symbol,
        "name": c.get("longname") or c.get("shortname") or symbol,
        "exchange": c.get("exchange", ""),
        "quote_type": c.get("quoteType", "EQUITY"),
        "sector": c.get("sector", ""),
        "industry": c.get("industry", ""),
        "cik": c.get("cik"),
        "candidates": candidates[:10],
    }
