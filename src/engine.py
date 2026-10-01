from __future__ import annotations
import pandas as pd
from .resolver import resolve_company
from .sources import find_sec_cik, sec_financials, yahoo_financials, discover_peer_candidates, peer_metrics
from .analysis import standardize_yahoo, merge_official_then_fallback, calculate_metrics, valuation, risk_flags, analyst_insights, peer_symbols
from .utils import now_utc


def run_research(query):
    resolved=resolve_company(query)
    symbol=resolved["symbol"]
    y=yahoo_financials(symbol)
    sec_cik=find_sec_cik(symbol)
    sec_df, sec_source = sec_financials(sec_cik) if sec_cik else (None,"SEC CIK not found")
    ydf=standardize_yahoo(y)
    financials, source=merge_official_then_fallback(sec_df,ydf)
    info=y.get("info",{})
    price=y.get("price")
    market={
        "Price": price,
        "Shares Outstanding": info.get("sharesOutstanding"),
        "Market Cap": info.get("marketCap"),
        "Beta": info.get("beta"),
        "52W High": info.get("fiftyTwoWeekHigh"),
        "52W Low": info.get("fiftyTwoWeekLow"),
    }
    metrics, latest=calculate_metrics(financials,market)
    val=valuation(metrics)
    metrics.update(val)
    flags=risk_flags(metrics,financials)
    insights=analyst_insights(metrics,financials)
    peer_candidates=discover_peer_candidates(info, symbol, limit=6)
    peer_df=peer_metrics(peer_candidates)
    # Keep the legacy recommendation list only as a final fallback.
    if peer_df.empty:
        legacy=peer_symbols(info,symbol)
        peer_df=peer_metrics([{"symbol":x,"name":x} for x in legacy])
    peers=peer_df["Symbol"].tolist() if not peer_df.empty else [x["symbol"] for x in peer_candidates]
    profile={
        "Name": info.get("longName") or resolved["name"],
        "Symbol": symbol,
        "Exchange": info.get("exchange") or resolved.get("exchange"),
        "Country": info.get("country"),
        "Sector": info.get("sector") or resolved.get("sector"),
        "Industry": info.get("industry") or resolved.get("industry"),
        "Website": info.get("website"),
        "Business Summary": info.get("longBusinessSummary"),
        "SEC CIK": sec_cik,
        "Data Timestamp": now_utc(),
        "Financial Source": source,
        "Market Source": "Yahoo Finance market data",
    }
    official=[]
    if profile["Website"]: official.append(("Company website / investor information",profile["Website"]))
    if sec_cik: official.append(("SEC EDGAR company facts",f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(sec_cik).zfill(10)}.json"))
    # Exchange source map is deliberately a navigation aid, not represented as the actual financial data source.
    ex=str(profile.get("Exchange") or "").upper()
    if ".NS" in symbol.upper() or "NSE" in ex: official.append(("NSE India", "https://www.nseindia.com/"))
    if ".BO" in symbol.upper() or "BSE" in ex: official.append(("BSE India", "https://www.bseindia.com/"))
    return {"profile":profile,"financials":financials,"metrics":metrics,"valuation":val,"flags":flags,"insights":insights,"peers":peers,"peer_candidates":peer_candidates,"peer_df":peer_df,"official":official,"resolved_candidates":resolved["candidates"],"sec_source":sec_source}
