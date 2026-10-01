from __future__ import annotations
import re
import numpy as np
import pandas as pd
from .utils import clean_number


def _norm_label(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _as_year(value):
    try:
        return pd.Timestamp(value).year
    except Exception:
        m = re.search(r"(19|20)\d{2}", str(value))
        return int(m.group(0)) if m else None


def _period_series(s):
    if s is None:
        return pd.Series(dtype=float)
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return pd.Series(dtype=float)
    years = [_as_year(x) for x in s.index]
    keep = [(y is not None) for y in years]
    if not any(keep):
        return pd.Series(dtype=float)
    out = pd.Series(s.to_numpy()[keep], index=[y for y in years if y is not None], dtype=float)
    return out.groupby(level=0).last().sort_index()


def _flatten_columns(frame):
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame
    out = frame.copy()
    out.columns = [" ".join(str(x) for x in col if str(x) not in {"", "nan", "None"}).strip() for col in out.columns]
    return out


def _row_match(frame, names):
    if frame is None or frame.empty:
        return None
    targets = {_norm_label(n) for n in names}
    for original in frame.index:
        n = _norm_label(original)
        if n in targets:
            return original
    # Prefer contains matches, but only after exact normalized matching.
    for original in frame.index:
        n = _norm_label(original)
        for target in targets:
            if target and (target in n or n in target):
                return original
    return None


def yahoo_annual_series(frame, names):
    """Extract an annual metric from yfinance statements across layout/version changes."""
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    frame = _flatten_columns(frame)
    row = _row_match(frame, names)
    if row is not None:
        return _period_series(frame.loc[row])

    # Some providers/versions can return the metric as a column instead of an index row.
    targets = {_norm_label(n) for n in names}
    for col in frame.columns:
        n = _norm_label(col)
        if n in targets or any(t and (t in n or n in t) for t in targets):
            return _period_series(frame[col])
    return pd.Series(dtype=float)


def standardize_yahoo(frames):
    inc, bs, cf = frames.get("income"), frames.get("balance"), frames.get("cashflow")
    out = {}
    mappings = {
        "Revenue": (inc, ["Total Revenue", "Operating Revenue", "TotalRevenue", "Revenue", "Revenues"]),
        "Net Income": (inc, ["Net Income", "Net Income Common Stockholders", "Net Income Including Noncontrolling Interests", "NetIncome", "Net Income Continuous Operations", "Net Income From Continuing Operation Net Minority Interest"]),
        "Operating Income": (inc, ["Operating Income", "OperatingIncome", "Operating Income Loss"]),
        "Gross Profit": (inc, ["Gross Profit", "GrossProfit"]),
        "Operating Cash Flow": (cf, ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash Flow From Continuing Operating Activities", "Operating Cash Flow From Continuing Operations", "Net Cash Provided By Operating Activities"]),
        "Capital Expenditure": (cf, ["Capital Expenditure", "Capital Expenditure Reported", "Purchase Of PPE", "Purchase Of Property Plant And Equipment", "Payments To Acquire Property Plant And Equipment"]),
        "Total Assets": (bs, ["Total Assets", "TotalAssets", "Assets"]),
        "Total Equity": (bs, ["Stockholders Equity", "Stockholders Equity Including Minority Interest", "Total Equity Gross Minority Interest", "Common Stock Equity", "Total Equity", "Stockholders' Equity"]),
        "Cash": (bs, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash Financial", "Cash And Cash Equivalents And Short Term Investments"]),
        "Total Debt": (bs, ["Total Debt", "Total Debt And Capital Lease Obligation", "Long Term Debt And Capital Lease Obligation", "Long Term Debt", "Current Debt", "Long Term Debt Current", "Long Term Debt Noncurrent"]),
        "Current Assets": (bs, ["Current Assets", "Total Current Assets"]),
        "Current Liabilities": (bs, ["Current Liabilities", "Total Current Liabilities"]),
    }
    for key, (frame, names) in mappings.items():
        out[key] = yahoo_annual_series(frame, names)
    return pd.DataFrame(out).sort_index()


def merge_official_then_fallback(sec_df, yahoo_df):
    if sec_df is None or sec_df.empty:
        return yahoo_df.copy(), "Yahoo Finance structured financials"
    if yahoo_df is None or yahoo_df.empty:
        return sec_df.copy(), "SEC EDGAR + available official concepts"
    all_idx = sorted(set(sec_df.index).union(yahoo_df.index))
    result = pd.DataFrame(index=all_idx)
    for col in sorted(set(sec_df.columns).union(yahoo_df.columns)):
        a = sec_df[col] if col in sec_df else pd.Series(index=all_idx, dtype=float)
        b = yahoo_df[col] if col in yahoo_df else pd.Series(index=all_idx, dtype=float)
        result[col] = a.reindex(all_idx).combine_first(b.reindex(all_idx))
    return result, "SEC EDGAR primary + Yahoo Finance fallback"


def _latest_and_previous(df):
    if df is None or df.empty:
        return None, None
    valid = sorted([x for x in df.index if _as_year(x) is not None])
    if not valid:
        return None, None
    latest = valid[-1]
    previous = valid[-2] if len(valid) >= 2 else None
    return latest, previous


def calculate_metrics(df, market=None):
    metrics = {}
    latest, prev = _latest_and_previous(df)

    def val(col, year=None):
        year = latest if year is None else year
        if year is None or df is None or df.empty or col not in df.columns:
            return None
        try:
            return clean_number(df.loc[year, col])
        except Exception:
            return None

    revenue = val("Revenue"); ni = val("Net Income"); op = val("Operating Income"); gp = val("Gross Profit")
    ocf = val("Operating Cash Flow"); capex = val("Capital Expenditure"); assets = val("Total Assets"); equity = val("Total Equity")
    cash = val("Cash"); debt = val("Total Debt"); ca = val("Current Assets"); cl = val("Current Liabilities")

    for label, value in [("Revenue", revenue), ("Net Income", ni), ("Operating Income", op), ("Gross Profit", gp),
                         ("Operating Cash Flow", ocf), ("Capital Expenditure", capex), ("Total Assets", assets),
                         ("Total Equity", equity), ("Cash", cash), ("Total Debt", debt), ("Current Assets", ca),
                         ("Current Liabilities", cl)]:
        metrics[label] = value

    prior_revenue = val("Revenue", prev)
    metrics["Revenue Growth"] = (revenue / prior_revenue - 1) if revenue is not None and prior_revenue not in (None, 0) else None
    metrics["Net Margin"] = ni / revenue if ni is not None and revenue not in (None, 0) else None
    metrics["Operating Margin"] = op / revenue if op is not None and revenue not in (None, 0) else None
    metrics["Gross Margin"] = gp / revenue if gp is not None and revenue not in (None, 0) else None
    metrics["ROE"] = ni / equity if ni is not None and equity not in (None, 0) else None
    metrics["ROA"] = ni / assets if ni is not None and assets not in (None, 0) else None
    metrics["Debt/Equity"] = debt / equity if debt is not None and equity not in (None, 0) else None
    metrics["Current Ratio"] = ca / cl if ca is not None and cl not in (None, 0) else None
    metrics["CFO / Net Income"] = ocf / ni if ocf is not None and ni not in (None, 0) else None
    metrics["FCF"] = ocf - abs(capex) if ocf is not None and capex is not None else None
    metrics["FCF Margin"] = metrics["FCF"] / revenue if metrics["FCF"] is not None and revenue not in (None, 0) else None
    metrics["Latest Fiscal Year"] = _as_year(latest) if latest is not None else None
    metrics["Previous Fiscal Year"] = _as_year(prev) if prev is not None else None
    if market:
        metrics.update({k: clean_number(v) if isinstance(v, (int, float, np.number)) else v for k, v in market.items()})
    return metrics, latest


def valuation(m):
    price = m.get("Price"); shares = m.get("Shares Outstanding"); ni = m.get("Net Income"); equity = m.get("Total Equity"); revenue = m.get("Revenue")
    out = {}
    out["Market Cap"] = price * shares if price is not None and shares is not None else m.get("Market Cap")
    mc = out["Market Cap"]
    if mc is not None and ni not in (None, 0): out["P/E"] = mc / ni
    if mc is not None and revenue not in (None, 0): out["P/S"] = mc / revenue
    if mc is not None and equity not in (None, 0): out["P/B"] = mc / equity
    return out


def risk_flags(m, df):
    flags = []
    if m.get("Revenue Growth") is not None and m["Revenue Growth"] < 0: flags.append(("Growth", "Latest annual revenue declined."))
    if m.get("Net Margin") is not None and m["Net Margin"] < 0: flags.append(("Profitability", "Latest annual net income is negative."))
    if m.get("Debt/Equity") is not None and m["Debt/Equity"] > 2: flags.append(("Leverage", "Debt-to-equity is above 2x."))
    if m.get("Current Ratio") is not None and m["Current Ratio"] < 1: flags.append(("Liquidity", "Current ratio is below 1x."))
    if m.get("CFO / Net Income") is not None and m["CFO / Net Income"] < 0.7: flags.append(("Cash quality", "Operating cash flow is relatively weak versus reported net income."))
    if m.get("FCF") is not None and m["FCF"] < 0: flags.append(("Cash flow", "Free cash flow is negative in the latest period."))
    if not flags: flags.append(("Data check", "No rule-based red flag was triggered by the available metrics; this is not a conclusion that risk is absent."))
    return flags


def analyst_insights(m, df):
    items = []
    rg = m.get("Revenue Growth"); nm = m.get("Net Margin"); roe = m.get("ROE"); de = m.get("Debt/Equity"); cfo = m.get("CFO / Net Income")
    if rg is not None: items.append(("Growth", f"Latest annual revenue growth is {rg*100:.1f}% based on the available financial series."))
    if nm is not None: items.append(("Profitability", f"Latest net margin is {nm*100:.1f}%, based on reported net income and revenue."))
    if roe is not None: items.append(("Returns", f"Latest ROE is {roe*100:.1f}%; interpret alongside leverage and business mix."))
    if de is not None: items.append(("Leverage", f"Debt/equity is {de:.2f}x; compare with sector norms before drawing conclusions."))
    if cfo is not None: items.append(("Cash conversion", f"Operating cash flow is {cfo:.2f}x net income in the latest comparable period."))
    return items


def peer_symbols(info, symbol):
    peers = []
    for p in (info.get("recommendedSymbols") or []):
        if isinstance(p, dict) and p.get("symbol") and p.get("symbol") != symbol:
            peers.append(p["symbol"])
        elif isinstance(p, str) and p != symbol:
            peers.append(p)
    return list(dict.fromkeys(peers))[:8]
