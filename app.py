from __future__ import annotations
import streamlit as st
import pandas as pd
import plotly.express as px
from src.engine import run_research
from src.reporting import excel_bytes, pdf_bytes
from src.utils import fmt_number,pct

st.set_page_config(page_title="Universal Equity Research Analyst",layout="wide")
st.title("Universal Equity Research Analyst")
st.caption("Enter a publicly listed company name or ticker. The system resolves the security, gathers available public data, validates it, and produces explainable research-analyst work.")

with st.sidebar:
    st.header("Research input")
    query=st.text_input("Company name or ticker",placeholder="e.g. Reliance, Apple, Microsoft, Toyota")
    run=st.button("Run research",type="primary",use_container_width=True)
    st.markdown("**Source policy**")
    st.write("Official/regulatory data is preferred where structured data is available. Market-data providers are used as fallback/supplement. Missing information is labelled N/A.")

if run:
    if not query.strip(): st.error("Enter a company name or ticker."); st.stop()
    with st.spinner("Resolving company and building research..."):
        try: st.session_state["research"]=run_research(query)
        except Exception as e: st.error(f"Research could not be completed: {e}"); st.stop()

r=st.session_state.get("research")
if not r:
    st.info("Enter a company name or ticker and click **Run research**.")
    st.markdown("### What this product does")
    st.markdown("Company identification → public-source collection → validation → financial analysis → valuation → peer context → risk analysis → explainable analyst report → Excel/PDF export.")
    st.stop()

p=r["profile"]; m=r["metrics"]; df=r["financials"]
st.subheader(p["Name"])
if df is None or df.empty:
    st.error("Financial statements could not be retrieved from the current public-data sources. Market data may still be available. Check the Sources tab and the latest company/regulatory filing.")
elif len(df) < 2:
    st.warning("Only limited annual financial history was retrieved. Ratios requiring prior-year or balance-sheet data may be unavailable.")
st.caption(f"{p['Symbol']} · {p.get('Exchange') or 'Exchange unavailable'} · {p.get('Sector') or 'Sector unavailable'} · Data: {p['Data Timestamp']}")

cols=st.columns(6)
for c,label,key,formatter in [(cols[0],"Price","Price",lambda x: fmt_number(x)),(cols[1],"Market Cap","Market Cap",lambda x: fmt_number(x)),(cols[2],"Revenue Growth","Revenue Growth",pct),(cols[3],"Net Margin","Net Margin",pct),(cols[4],"ROE","ROE",pct),(cols[5],"Debt/Equity","Debt/Equity",lambda x: fmt_number(x))]:
    c.metric(label,formatter(m.get(key)))

tabs=st.tabs(["Executive Summary","Financials","Ratios","Valuation","Peers","Risks & Validation","Business","Sources","Downloads"])

with tabs[0]:
    st.markdown("### Analyst-style summary")
    for cat,text in r["insights"]: st.write(f"**{cat}:** {text}")
    st.markdown("### What an analyst should investigate")
    questions=["Are the latest growth rates sustainable across the major business segments?","How does valuation compare with the company's growth, profitability and peers?","Is operating cash flow consistently supporting reported earnings?","What are the main leverage, liquidity and industry-specific risks?","Which disclosures or assumptions are missing and should be verified from the latest filing?"]
    for q in questions: st.write("• "+q)
    st.caption("This tool provides research analysis and evidence-based questions; it does not automatically issue a buy/sell recommendation.")

with tabs[1]:
    st.dataframe(df, use_container_width=True)
    if not df.empty and "Revenue" in df.columns:
        plot=df.reset_index().rename(columns={"index":"Year"})
        plot["Year"]=plot["Year"].astype(str)
        available=[c for c in ["Revenue","Net Income","Operating Cash Flow"] if c in plot.columns]
        if available:
            fig=px.line(plot,x="Year",y=available,markers=True,title="Historical financial trend")
            st.plotly_chart(fig,use_container_width=True)

with tabs[2]:
    ratio_keys=["Revenue Growth","Gross Margin","Operating Margin","Net Margin","ROE","ROA","Debt/Equity","Current Ratio","CFO / Net Income","FCF Margin","Beta"]
    ratio_df=pd.DataFrame({"Metric":ratio_keys,"Value":[m.get(k) for k in ratio_keys]})
    st.dataframe(ratio_df,hide_index=True,use_container_width=True)
    st.caption("Ratios are calculated from the latest comparable annual data available to the engine.")

with tabs[3]:
    st.dataframe(pd.DataFrame({"Valuation Metric":list(r["valuation"].keys()),"Value":list(r["valuation"].values())}),hide_index=True,use_container_width=True)
    st.markdown("### Valuation interpretation")
    st.write("Valuation multiples are descriptive snapshots. They should be compared with peer multiples, growth, margins, capital intensity and business quality rather than interpreted in isolation.")
    if m.get("Price") is not None and m.get("FCF") is not None and m.get("Shares Outstanding") is not None:
        st.markdown("### Simplified DCF scenario")
        st.caption("Scenario only — not a price target. Change assumptions and treat the output as an analytical sensitivity, not a forecast guarantee.")
        c1,c2,c3=st.columns(3)
        growth=c1.slider("FCF growth",-20,30,8)/100
        wacc=c2.slider("Discount rate",6,20,11)/100
        terminal=c3.slider("Terminal growth",0,6,3)/100
        fcf=m["FCF"]
        if fcf is not None and fcf>0 and wacc>terminal:
            pv=0
            for yr in range(1,6): pv += fcf*((1+growth)**yr)/((1+wacc)**yr)
            tv=fcf*((1+growth)**5)*(1+terminal)/(wacc-terminal)
            ev=pv+tv/((1+wacc)**5)
            equity=ev-(m.get("Total Debt") or 0)+(m.get("Cash") or 0)
            per_share=equity/m["Shares Outstanding"]
            st.metric("Scenario value per share",fmt_number(per_share))
        else: st.warning("DCF scenario requires positive FCF, shares outstanding and a discount rate above terminal growth.")

with tabs[4]:
    peer_df = r.get("peer_df")
    if peer_df is not None and not peer_df.empty:
        st.markdown("### Candidate peer group")
        st.caption("Peers are discovered dynamically from the company's industry/market context. Verify the final peer set against the latest company disclosures before using it for investment work.")
        display_cols = [c for c in ["Symbol","Company","Market Cap","Revenue Growth","Net Margin","ROE","Debt/Equity","P/E","P/B"] if c in peer_df.columns]
        st.dataframe(peer_df[display_cols], hide_index=True, use_container_width=True)
        numeric = [c for c in ["Revenue Growth","Net Margin","ROE","Debt/Equity","P/E","P/B"] if c in peer_df.columns]
        if numeric:
            med = peer_df[numeric].median(numeric_only=True)
            st.markdown("### Peer-group reference statistics")
            st.dataframe(pd.DataFrame({"Metric": med.index, "Peer median": med.values}), hide_index=True, use_container_width=True)
    else:
        st.info("No reliable peer group was surfaced automatically from the available public market-data universe. The report does not invent peers.")

with tabs[5]:
    st.markdown("### Rule-based risk flags")
    for cat,text in r["flags"]: st.warning(f"**{cat}:** {text}")
    st.markdown("### Data validation")
    checks=[]
    checks.append(("Revenue available",m.get("Revenue") is not None))
    checks.append(("Net income available",m.get("Net Income") is not None))
    checks.append(("Balance sheet available",m.get("Total Assets") is not None and m.get("Total Equity") is not None))
    checks.append(("Cash-flow data available",m.get("Operating Cash Flow") is not None))
    checks.append(("Market price available",m.get("Price") is not None))
    st.dataframe(pd.DataFrame({"Check":[x[0] for x in checks],"Status":["Available" if x[1] else "Unavailable" for x in checks]}),hide_index=True,use_container_width=True)

with tabs[6]:
    st.write(p.get("Business Summary") or "Business description unavailable from the selected public profile source.")
    st.write(f"**Sector:** {p.get('Sector') or 'N/A'}")
    st.write(f"**Industry:** {p.get('Industry') or 'N/A'}")
    st.write("**Business-analysis prompts:**")
    for q in ["What are the company's main revenue engines?","Which segments drive margins and cash flow?","What competitive advantages are disclosed by the company?","What external factors could change demand, margins or capital requirements?"]: st.write("• "+q)

with tabs[7]:
    st.markdown("### Data sources")
    st.write(f"Financial source: **{p['Financial Source']}**")
    st.write(f"Market source: **{p['Market Source']}**")
    for label,url in r["official"]:
        st.markdown(f"- [{label}]({url})")
    st.caption("Source links are provided for verification. The application should be used alongside the latest official filing and company disclosures.")

with tabs[8]:
    summary=[["Company",p["Name"]],["Symbol",p["Symbol"]],["Financial source",p["Financial Source"]],["Market source",p["Market Source"]]]
    sheets={"Profile":pd.DataFrame([p]),"Financials":df,"Metrics":pd.DataFrame({"Metric":list(m.keys()),"Value":list(m.values())}),"Risk Flags":pd.DataFrame(r["flags"],columns=["Category","Observation"]),"Insights":pd.DataFrame(r["insights"],columns=["Category","Observation"]),"Valuation":pd.DataFrame({"Metric":list(r["valuation"].keys()),"Value":list(r["valuation"].values())}),"Peers":r.get("peer_df",pd.DataFrame())}
    ep=excel_bytes({"summary":summary,"sheets":sheets})
    sections=[("Executive Summary",[f"Company: {p['Name']}",f"Symbol: {p['Symbol']}"]+[x[1] for x in r["insights"]]),("Risk Flags",[f"{a}: {b}" for a,b in r["flags"]]),("Valuation",[f"{k}: {v}" for k,v in r["valuation"].items()])]
    pp=pdf_bytes({"title":f"Equity Research Report — {p['Name']}","sections":sections})
    st.download_button("Download Excel research workbook",ep,file_name=f"{p['Symbol']}_equity_research.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Download PDF research report",pp,file_name=f"{p['Symbol']}_equity_research.pdf",mime="application/pdf")
