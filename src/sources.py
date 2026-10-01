from __future__ import annotations
import os, requests, pandas as pd, numpy as np, yfinance as yf
from .utils import clean_number

SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def sec_headers():
    return {"User-Agent": os.getenv("SEC_USER_AGENT", "UniversalEquityResearch/1.0 contact@example.com")}


def get_sec_company_facts(cik):
    if not cik:
        return None
    try:
        r = requests.get(SEC_FACTS.format(cik=str(cik).zfill(10)), headers=sec_headers(), timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def find_sec_cik(symbol):
    try:
        from .resolver import sec_ticker_map
        rows = sec_ticker_map()
        for r in rows:
            if r["ticker"].upper() == symbol.upper().replace(".US", ""):
                return r["cik"]
    except Exception:
        return None
    return None


def sec_series(facts, concepts, units=("USD", "shares", "USD/shares")):
    if not facts:
        return pd.Series(dtype=float)
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        obj = usgaap.get(concept)
        if not obj:
            continue
        unit_map = obj.get("units", {})
        unit_name = next((u for u in units if u in unit_map), None)
        if not unit_name and unit_map:
            unit_name = next(iter(unit_map))
        rows = unit_map.get(unit_name, []) if unit_name else []
        vals = []
        for row in rows:
            if row.get("form") not in {"10-K", "20-F", "40-F", "10-K/A", "20-F/A", "40-F/A"}:
                continue
            if row.get("fp") not in {"FY", None}:
                continue
            if not row.get("fy") or not row.get("end"):
                continue
            vals.append({"year": int(row["fy"]), "date": row["end"], "value": clean_number(row.get("val")), "form": row.get("form")})
        if vals:
            df = pd.DataFrame(vals).dropna(subset=["value"])
            df = df.sort_values(["year", "date"]).drop_duplicates("year", keep="last")
            return pd.Series(df["value"].values, index=df["year"].values, dtype=float)
    return pd.Series(dtype=float)


def sec_financials(cik):
    facts = get_sec_company_facts(cik)
    if not facts:
        return None, "SEC CompanyFacts unavailable"
    data = {}
    mappings = {
        "Revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"],
        "Net Income": ["NetIncomeLoss", "ProfitLoss"],
        "Operating Income": ["OperatingIncomeLoss"],
        "Gross Profit": ["GrossProfit"],
        "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities"],
        "Capital Expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "Total Assets": ["Assets"],
        "Total Equity": ["StockholdersEquity"],
        "Cash": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
        "Total Debt": ["LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent"],
    }
    for label, concepts in mappings.items():
        s = sec_series(facts, concepts)
        if not s.empty:
            data[label] = s
    if not data:
        return None, "SEC facts found but no compatible annual concepts"
    df = pd.DataFrame(data).sort_index()
    return df, "SEC EDGAR CompanyFacts/XBRL"


def yahoo_data(symbol):
    t = yf.Ticker(symbol)
    info = {}
    try: info = t.info or {}
    except Exception: pass
    try: fast = t.fast_info
    except Exception: fast = {}
    price = None
    for k in ["last_price", "regularMarketPrice"]:
        try: price = clean_number(fast.get(k) if hasattr(fast, "get") else getattr(fast, k, None))
        except Exception: pass
        if price is not None: break
    if price is None: price = clean_number(info.get("currentPrice"))
    def stmt(method):
        try: return method()
        except Exception: return pd.DataFrame()
    inc = stmt(t.income_stmt)
    bs = stmt(t.balance_sheet)
    cf = stmt(t.cashflow)
    # Explicit annual getters are a compatibility fallback across yfinance versions.
    if inc.empty:
        inc = stmt(lambda: t.get_income_stmt(freq="yearly"))
    if bs.empty:
        bs = stmt(lambda: t.get_balance_sheet(freq="yearly"))
    if cf.empty:
        cf = stmt(lambda: t.get_cash_flow(freq="yearly"))
    return t, info, fast, price, inc, bs, cf


def yahoo_financials(symbol):
    t, info, fast, price, inc, bs, cf = yahoo_data(symbol)
    frames = {}
    for src_name, frame in [("income", inc), ("balance", bs), ("cashflow", cf)]:
        if not frame.empty:
            frames[src_name] = frame
    return {"ticker": t, "info": info, "fast": fast, "price": price, **frames}


def _region_for_profile(info):
    country = str(info.get("country") or "").lower()
    mapping = {
        "india": "IN", "united states": "US", "united kingdom": "GB", "japan": "JP", "china": "CN",
        "hong kong": "HK", "canada": "CA", "australia": "AU", "germany": "DE", "france": "FR",
        "switzerland": "CH", "singapore": "SG", "south korea": "KR", "taiwan": "TW", "brazil": "BR",
        "south africa": "ZA", "netherlands": "NL", "spain": "ES", "italy": "IT", "mexico": "MX",
    }
    return mapping.get(country, "US")


def _slugify_industry_key(key):
    if not key:
        return None
    return str(key).strip().lower().replace(" ", "-").replace("&", "and")


def discover_peer_candidates(info, symbol, limit=6):
    """Discover same-industry public-equity peers dynamically.

    Uses Yahoo's current sector/industry universe where available. This is a
    discovery layer only; the report still labels the set as candidate peers
    and encourages verification against company filings.
    """
    peers = []
    try:
        region = _region_for_profile(info)
        industry_key = info.get("industryKey") or _slugify_industry_key(info.get("industry"))
        if industry_key:
            industry = yf.Industry(industry_key, region=region)
            table = industry.top_companies
            if table is not None:
                if isinstance(table, pd.DataFrame):
                    for idx, row in table.iterrows():
                        sym = row.get("symbol") or row.get("ticker") or (idx if isinstance(idx, str) else None)
                        if sym and str(sym).upper() != str(symbol).upper():
                            peers.append({"symbol": str(sym), "name": row.get("name") or row.get("shortName") or str(sym)})
                elif isinstance(table, dict):
                    for sym, row in table.items():
                        if str(sym).upper() != str(symbol).upper():
                            peers.append({"symbol": str(sym), "name": (row or {}).get("name") or str(sym)})
    except Exception:
        pass

    # Fall back to Yahoo's recommendation list when the industry endpoint is unavailable.
    if not peers:
        for p in (info.get("recommendedSymbols") or []):
            if isinstance(p, dict):
                sym = p.get("symbol"); name = p.get("shortname") or p.get("longname") or sym
            else:
                sym = p; name = p
            if sym and str(sym).upper() != str(symbol).upper():
                peers.append({"symbol": str(sym), "name": name})

    # De-duplicate and cap.
    seen = set(); out = []
    for p in peers:
        sym = p["symbol"].upper()
        if sym in seen:
            continue
        seen.add(sym)
        out.append(p)
        if len(out) >= limit:
            break
    return out


def peer_metrics(peers):
    rows = []
    for p in peers:
        sym = p["symbol"]
        try:
            t = yf.Ticker(sym)
            info = t.info or {}
            quote_type = str(info.get("quoteType") or "").upper()
            if quote_type and quote_type != "EQUITY":
                continue
            price = clean_number(info.get("currentPrice") or info.get("regularMarketPrice"))
            market_cap = clean_number(info.get("marketCap"))
            revenue_growth = clean_number(info.get("revenueGrowth"))
            net_margin = clean_number(info.get("profitMargins"))
            roe = clean_number(info.get("returnOnEquity"))
            debt_equity = clean_number(info.get("debtToEquity"))
            # Provider ratios are preferred, but calculate from annual statements when absent.
            if any(v is None for v in [revenue_growth, net_margin, roe, debt_equity]):
                try:
                    from .analysis import standardize_yahoo, calculate_metrics
                    raw = yahoo_financials(sym)
                    sdf = standardize_yahoo(raw)
                    pm, _ = calculate_metrics(sdf, {"Price": price, "Market Cap": market_cap})
                    revenue_growth = revenue_growth if revenue_growth is not None else pm.get("Revenue Growth")
                    net_margin = net_margin if net_margin is not None else pm.get("Net Margin")
                    roe = roe if roe is not None else pm.get("ROE")
                    debt_equity = debt_equity if debt_equity is not None else pm.get("Debt/Equity")
                except Exception:
                    pass
            rows.append({
                "Symbol": sym,
                "Company": info.get("longName") or info.get("shortName") or p.get("name") or sym,
                "Price": price,
                "Market Cap": market_cap,
                "Revenue Growth": revenue_growth,
                "Net Margin": net_margin,
                "ROE": roe,
                "Debt/Equity": debt_equity,
                "P/E": clean_number(info.get("trailingPE")),
                "P/B": clean_number(info.get("priceToBook")),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)
