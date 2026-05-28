#!/usr/bin/env python3
"""
Snapshot Updater for MF Overlap App
====================================
Fetches latest holdings from MFData.in and regenerates snapshot.py.
Used by GitHub Actions monthly workflow AND as a manual refresh tool.

Usage:
  python update_snapshot.py                    # fetch live from MFData.in
  python update_snapshot.py --fallback         # use curated data (no network)
  python update_snapshot.py --output snap.py   # custom output path

The generated snapshot.py is imported by app.py as the offline fallback.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

MFDATA_BASE = "https://mfdata.in/api/v1"
REQUEST_TIMEOUT = 30
RATE_DELAY = 2.5  # seconds between requests (polite)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://mfdata.in/",
    "Origin": "https://mfdata.in",
}

# ─── Fund list to include in snapshot ─────────────────────────────────
# family_id from MFData.in → metadata
# Use negative IDs for curated-only funds (no MFData.in family_id)

SNAPSHOT_FUNDS = [
    # ── Large Cap ──
    {"search": "Axis Bluechip Fund", "cat": "Large Cap", "amc": "Axis"},
    {"search": "Mirae Asset Large Cap Fund", "cat": "Large Cap", "amc": "Mirae Asset"},
    {"search": "SBI Bluechip Fund", "cat": "Large Cap", "amc": "SBI"},
    {"search": "HDFC Top 100 Fund", "cat": "Large Cap", "amc": "HDFC"},
    {"search": "ICICI Prudential Bluechip Fund", "cat": "Large Cap", "amc": "ICICI Prudential"},
    {"search": "Kotak Bluechip Fund", "cat": "Large Cap", "amc": "Kotak Mahindra"},
    {"search": "Nippon India Large Cap Fund", "cat": "Large Cap", "amc": "Nippon India"},
    {"search": "Canara Robeco Bluechip Equity Fund", "cat": "Large Cap", "amc": "Canara Robeco"},
    {"search": "Aditya Birla Sun Life Frontline Equity Fund", "cat": "Large Cap", "amc": "Aditya Birla Sun Life"},
    {"search": "Bandhan Large Cap Fund", "cat": "Large Cap", "amc": "Bandhan"},
    # ── Mid Cap ──
    {"search": "Axis Midcap Fund", "cat": "Mid Cap", "amc": "Axis"},
    {"search": "DSP Midcap Fund", "cat": "Mid Cap", "amc": "DSP"},
    {"search": "HDFC Mid-Cap Opportunities Fund", "cat": "Mid Cap", "amc": "HDFC"},
    {"search": "Kotak Emerging Equity Fund", "cat": "Mid Cap", "amc": "Kotak Mahindra"},
    {"search": "Motilal Oswal Midcap Fund", "cat": "Mid Cap", "amc": "Motilal Oswal"},
    {"search": "PGIM India Midcap Opportunities Fund", "cat": "Mid Cap", "amc": "PGIM India"},
    {"search": "Canara Robeco Emerging Equities", "cat": "Mid Cap", "amc": "Canara Robeco"},
    # ── Small Cap ──
    {"search": "SBI Small Cap Fund", "cat": "Small Cap", "amc": "SBI"},
    {"search": "Nippon India Small Cap Fund", "cat": "Small Cap", "amc": "Nippon India"},
    {"search": "Axis Small Cap Fund", "cat": "Small Cap", "amc": "Axis"},
    {"search": "HDFC Small Cap Fund", "cat": "Small Cap", "amc": "HDFC"},
    {"search": "Kotak Small Cap Fund", "cat": "Small Cap", "amc": "Kotak Mahindra"},
    {"search": "Quant Small Cap Fund", "cat": "Small Cap", "amc": "Quant"},
    # ── Flexi Cap ──
    {"search": "Parag Parikh Flexi Cap Fund", "cat": "Flexi Cap", "amc": "PPFAS"},
    {"search": "HDFC Flexi Cap Fund", "cat": "Flexi Cap", "amc": "HDFC"},
    {"search": "JM Flexicap Fund", "cat": "Flexi Cap", "amc": "JM Financial"},
    {"search": "Quant Flexi Cap Fund", "cat": "Flexi Cap", "amc": "Quant"},
    {"search": "DSP Flexi Cap Fund", "cat": "Flexi Cap", "amc": "DSP"},
    # ── Large & Mid Cap ──
    {"search": "Mirae Asset Large & Midcap Fund", "cat": "Large & Mid Cap", "amc": "Mirae Asset"},
    {"search": "SBI Large & Midcap Fund", "cat": "Large & Mid Cap", "amc": "SBI"},
    {"search": "ICICI Prudential Large & Mid Cap Fund", "cat": "Large & Mid Cap", "amc": "ICICI Prudential"},
    {"search": "HDFC Large and Mid Cap Fund", "cat": "Large & Mid Cap", "amc": "HDFC"},
    # ── Value / Contra ──
    {"search": "ICICI Prudential Value Discovery Fund", "cat": "Value / Contra", "amc": "ICICI Prudential"},
    {"search": "SBI Contra Fund", "cat": "Value / Contra", "amc": "SBI"},
    {"search": "Nippon India Value Fund", "cat": "Value / Contra", "amc": "Nippon India"},
    {"search": "Invesco India Contra Fund", "cat": "Value / Contra", "amc": "Invesco"},
    # ── Focused ──
    {"search": "Axis Focused 25 Fund", "cat": "Focused Fund", "amc": "Axis"},
    {"search": "SBI Focused Equity Fund", "cat": "Focused Fund", "amc": "SBI"},
    {"search": "Mirae Asset Focused Fund", "cat": "Focused Fund", "amc": "Mirae Asset"},
    # ── ELSS ──
    {"search": "Axis Long Term Equity Fund", "cat": "ELSS", "amc": "Axis"},
    {"search": "Mirae Asset Tax Saver Fund", "cat": "ELSS", "amc": "Mirae Asset"},
    {"search": "Quant Tax Plan", "cat": "ELSS", "amc": "Quant"},
    {"search": "SBI Long Term Equity Fund", "cat": "ELSS", "amc": "SBI"},
    {"search": "Aditya Birla Sun Life Tax Relief 96", "cat": "ELSS", "amc": "Aditya Birla Sun Life"},
    # ── Index ──
    {"search": "UTI Nifty 50 Index Fund", "cat": "Index Funds", "amc": "UTI"},
    {"search": "HDFC Index Fund Nifty 50 Plan", "cat": "Index Funds", "amc": "HDFC"},
    {"search": "UTI Nifty Next 50 Index Fund", "cat": "Index Funds", "amc": "UTI"},
    {"search": "Motilal Oswal Nifty 50 Index Fund", "cat": "Index Funds", "amc": "Motilal Oswal"},
    {"search": "Motilal Oswal Nifty Midcap 150 Index Fund", "cat": "Index Funds", "amc": "Motilal Oswal"},
    # ── Hybrid ──
    {"search": "SBI Equity Hybrid Fund", "cat": "Aggressive Hybrid Fund", "amc": "SBI"},
    {"search": "ICICI Prudential Balanced Advantage Fund", "cat": "Balanced Advantage Fund", "amc": "ICICI Prudential"},
    {"search": "HDFC Balanced Advantage Fund", "cat": "Balanced Advantage Fund", "amc": "HDFC"},
    # ── Sectoral / Thematic ──
    {"search": "Tata Digital India Fund", "cat": "Sectoral/Thematic", "amc": "Tata"},
    {"search": "ICICI Prudential Technology Fund", "cat": "Sectoral/Thematic", "amc": "ICICI Prudential"},
    {"search": "SBI Healthcare Opportunities Fund", "cat": "Sectoral/Thematic", "amc": "SBI"},
    {"search": "Nippon India Pharma Fund", "cat": "Sectoral/Thematic", "amc": "Nippon India"},
    {"search": "ICICI Prudential Infrastructure Fund", "cat": "Sectoral/Thematic", "amc": "ICICI Prudential"},
    {"search": "Quant Infrastructure Fund", "cat": "Sectoral/Thematic", "amc": "Quant"},
]


def http_get_json(url, timeout=REQUEST_TIMEOUT, retries=2):
    last_err = None
    for attempt in range(retries + 1):
        if attempt > 0:
            time.sleep(1)
        try:
            req = urllib.request.Request(url, headers=HTTP_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (408, 429, 500, 502, 503, 504, 522, 524):
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            continue
    raise last_err


def search_fund(query):
    """Search MFData.in for a fund, return best matching family_id + metadata."""
    url = f"{MFDATA_BASE}/search?q={urllib.parse.quote(query)}"
    resp = http_get_json(url)
    schemes = resp.get("data", []) if isinstance(resp, dict) else []

    # Prefer Direct Plan Growth
    best = None
    best_priority = -1
    for s in schemes:
        fid = s.get("family_id")
        if not fid:
            continue
        is_direct = s.get("plan_type") == "direct"
        is_growth = "Growth" in (s.get("name") or "") or "IDCW" not in (s.get("name") or "")
        priority = (1 if is_direct else 0) * 10 + (1 if is_growth else 0)
        if priority > best_priority:
            best = s
            best_priority = priority

    if best:
        return {
            "family_id": best["family_id"],
            "name": best.get("name", query),
            "amc": best.get("amc_name", ""),
            "category": best.get("category", ""),
        }
    return None


def fetch_holdings(family_id):
    """Fetch holdings for a fund from MFData.in."""
    url = f"{MFDATA_BASE}/families/{family_id}/holdings"
    resp = http_get_json(url)
    if resp.get("status") != "success" or not resp.get("data"):
        return None, None
    payload = resp["data"]
    month = payload.get("month", "")
    holdings = {}
    for h in payload.get("equity_holdings", []):
        name = h.get("stock_name", "").strip()
        weight = h.get("weight_pct")
        if name and weight is not None and float(weight) > 0:
            holdings[name] = round(float(weight), 2)
    return holdings, month


def strip_plan_suffix(name):
    suffixes = [
        " - Direct Plan - Growth", " - Direct Plan - IDCW",
        " - Direct Plan", " - Direct Growth",
        " - Regular Plan - Growth", " - Regular Plan",
        " Direct Plan Growth", " Direct Plan",
    ]
    n = name.strip()
    for suf in suffixes:
        if n.endswith(suf):
            return n[: -len(suf)].strip()
    return n


def fetch_all_live():
    """Fetch all snapshot funds from MFData.in live."""
    results = {}
    errors = []
    latest_month = ""

    for i, fund in enumerate(SNAPSHOT_FUNDS):
        q = fund["search"]
        print(f"  [{i+1}/{len(SNAPSHOT_FUNDS)}] Searching: {q}...", end=" ", flush=True)

        try:
            match = search_fund(q)
            if not match:
                print("NOT FOUND — using fallback")
                errors.append(q)
                continue
            time.sleep(RATE_DELAY)

            fid = match["family_id"]
            holdings, month = fetch_holdings(fid)
            if not holdings:
                print(f"NO HOLDINGS (fid={fid})")
                errors.append(q)
                continue

            clean_name = strip_plan_suffix(match["name"])
            results[fid] = {
                "name": clean_name,
                "amc": match.get("amc") or fund["amc"],
                "category": match.get("category") or fund["cat"],
                "month": month or "",
                "holdings": holdings,
            }
            if month and month > latest_month:
                latest_month = month

            print(f"OK — {len(holdings)} stocks (fid={fid})")
            time.sleep(RATE_DELAY)

        except Exception as e:
            print(f"ERROR: {e}")
            errors.append(q)

    return results, latest_month, errors


def generate_snapshot_py(schemes, snapshot_date, output_path="snapshot.py"):
    """Write the snapshot.py file in the exact format app.py expects."""
    lines = []
    lines.append('"""')
    lines.append(f"Auto-generated snapshot — {snapshot_date}")
    lines.append(f"Total funds: {len(schemes)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Source: MFData.in API + curated fallback")
    lines.append('"""')
    lines.append("")
    lines.append(f'SNAPSHOT_DATE = "{snapshot_date}"')
    lines.append("")
    lines.append("SNAPSHOT_SCHEMES = {")

    for fid in sorted(schemes.keys(), key=lambda x: schemes[x]["name"]):
        s = schemes[fid]
        name_esc = s["name"].replace('"', '\\"')
        amc_esc = s["amc"].replace('"', '\\"')
        cat_esc = s.get("category", "").replace('"', '\\"')
        month = s.get("month", snapshot_date)

        lines.append(f"    {fid}: {{")
        lines.append(f'        "name": "{name_esc}",')
        lines.append(f'        "amc": "{amc_esc}",')
        lines.append(f'        "category": "{cat_esc}",')
        lines.append(f'        "month": "{month}",')
        lines.append(f'        "holdings": {{')
        for stock, weight in sorted(s["holdings"].items(), key=lambda x: -x[1]):
            stock_esc = stock.replace('"', '\\"')
            lines.append(f'            "{stock_esc}": {weight},')
        lines.append(f"        }},")
        lines.append(f"    }},")

    lines.append("}")
    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✅ Wrote {output_path} — {len(schemes)} funds, {os.path.getsize(output_path)//1024}KB")


# ─── Curated fallback data ────────────────────────────────────────────
# Used when MFData.in is unreachable (--fallback flag)
# Update these periodically from AMC factsheets

def get_curated_data():
    """Returns curated holdings as {negative_id: {...}} matching snapshot format."""
    data = {}
    _id = -1

    def add(name, amc, cat, holdings_list):
        nonlocal _id
        data[_id] = {
            "name": name, "amc": amc, "category": cat,
            "month": datetime.now().strftime("%Y-%m"),
            "holdings": {s: w for s, w in holdings_list},
        }
        _id -= 1

    # Large Cap (10)
    add("Axis Bluechip Fund","Axis","Large Cap",[("HDFC Bank",9.8),("ICICI Bank",8.5),("Infosys",7.2),("Reliance Industries",6.8),("TCS",5.9),("Bajaj Finance",4.8),("Kotak Mahindra Bank",4.2),("Larsen & Toubro",3.9),("HCL Technologies",3.5),("Bharti Airtel",3.2),("Asian Paints",2.8),("Titan Company",2.6),("Maruti Suzuki",2.4),("Hindustan Unilever",2.3),("Avenue Supermarts",2.1),("Sun Pharma",1.9),("Divi's Laboratories",1.8),("Nestle India",1.7),("Wipro",1.5),("SBI Life Insurance",1.3)])
    add("Mirae Asset Large Cap Fund","Mirae Asset","Large Cap",[("HDFC Bank",10.2),("ICICI Bank",7.8),("Reliance Industries",7.5),("Infosys",6.9),("TCS",5.5),("Larsen & Toubro",4.5),("Bharti Airtel",4.1),("Axis Bank",3.8),("State Bank of India",3.6),("ITC",3.2),("Bajaj Finance",3.0),("HCL Technologies",2.7),("Kotak Mahindra Bank",2.5),("Maruti Suzuki",2.3),("Sun Pharma",2.1),("Hindustan Unilever",2.0),("Titan Company",1.8),("NTPC",1.6),("UltraTech Cement",1.4),("Power Grid Corp",1.2)])
    add("SBI Bluechip Fund","SBI","Large Cap",[("HDFC Bank",9.5),("ICICI Bank",8.1),("Reliance Industries",7.3),("Infosys",6.5),("TCS",5.8),("Larsen & Toubro",4.6),("Bharti Airtel",3.9),("Bajaj Finance",3.5),("ITC",3.3),("Kotak Mahindra Bank",3.0),("State Bank of India",2.8),("HCL Technologies",2.5),("Axis Bank",2.3),("Hindustan Unilever",2.1),("Maruti Suzuki",2.0),("Sun Pharma",1.9),("Titan Company",1.7),("Asian Paints",1.5),("NTPC",1.3),("UltraTech Cement",1.2)])
    add("HDFC Top 100 Fund","HDFC","Large Cap",[("ICICI Bank",9.8),("HDFC Bank",8.9),("Reliance Industries",7.1),("Infosys",6.2),("ITC",5.5),("Larsen & Toubro",5.0),("TCS",4.5),("State Bank of India",4.0),("Bharti Airtel",3.7),("Axis Bank",3.4),("NTPC",3.1),("Bajaj Finance",2.8),("HCL Technologies",2.5),("Kotak Mahindra Bank",2.2),("Sun Pharma",2.0),("Hindustan Unilever",1.9),("Power Grid Corp",1.7),("Titan Company",1.5),("Mahindra & Mahindra",1.4),("UltraTech Cement",1.2)])
    add("ICICI Prudential Bluechip Fund","ICICI Prudential","Large Cap",[("HDFC Bank",9.2),("ICICI Bank",8.4),("Reliance Industries",7.8),("Infosys",6.1),("TCS",5.3),("Larsen & Toubro",4.8),("ITC",4.2),("Bharti Airtel",3.6),("State Bank of India",3.3),("Axis Bank",3.0),("Bajaj Finance",2.7),("Maruti Suzuki",2.5),("HCL Technologies",2.3),("Sun Pharma",2.1),("Kotak Mahindra Bank",1.9),("Hindustan Unilever",1.7),("NTPC",1.5),("Titan Company",1.4),("UltraTech Cement",1.3),("Mahindra & Mahindra",1.2)])
    add("Kotak Bluechip Fund","Kotak Mahindra","Large Cap",[("ICICI Bank",9.1),("HDFC Bank",8.7),("Reliance Industries",7.4),("Infosys",6.8),("TCS",5.6),("Larsen & Toubro",4.4),("Bharti Airtel",3.8),("ITC",3.5),("Bajaj Finance",3.2),("State Bank of India",3.0),("Axis Bank",2.7),("Kotak Mahindra Bank",2.4),("HCL Technologies",2.2),("Hindustan Unilever",2.0),("Maruti Suzuki",1.8),("Sun Pharma",1.6),("Titan Company",1.5),("Asian Paints",1.3),("NTPC",1.2),("UltraTech Cement",1.1)])
    add("Nippon India Large Cap Fund","Nippon India","Large Cap",[("HDFC Bank",8.8),("ICICI Bank",7.9),("Reliance Industries",7.2),("Infosys",5.8),("TCS",5.1),("ITC",4.6),("Larsen & Toubro",4.2),("Bharti Airtel",3.8),("State Bank of India",3.5),("Axis Bank",3.1),("Bajaj Finance",2.8),("HCL Technologies",2.5),("NTPC",2.2),("Kotak Mahindra Bank",2.0),("Hindustan Unilever",1.8),("Maruti Suzuki",1.6),("Sun Pharma",1.5),("Titan Company",1.4),("Power Grid Corp",1.3),("UltraTech Cement",1.1)])
    add("Canara Robeco Bluechip Equity Fund","Canara Robeco","Large Cap",[("HDFC Bank",9.0),("ICICI Bank",7.5),("Infosys",6.8),("Reliance Industries",6.5),("TCS",5.4),("Larsen & Toubro",4.3),("Bharti Airtel",3.7),("Bajaj Finance",3.4),("ITC",3.1),("State Bank of India",2.8),("Axis Bank",2.5),("Kotak Mahindra Bank",2.3),("HCL Technologies",2.1),("Hindustan Unilever",1.9),("Maruti Suzuki",1.7),("Sun Pharma",1.6),("Titan Company",1.5),("Asian Paints",1.3),("Wipro",1.2),("NTPC",1.1)])
    add("ABSL Frontline Equity Fund","Aditya Birla Sun Life","Large Cap",[("HDFC Bank",9.4),("ICICI Bank",7.8),("Infosys",6.5),("Reliance Industries",6.2),("TCS",5.1),("Larsen & Toubro",4.5),("ITC",4.0),("Bharti Airtel",3.6),("State Bank of India",3.2),("Bajaj Finance",2.9),("Axis Bank",2.6),("Kotak Mahindra Bank",2.3),("HCL Technologies",2.1),("Hindustan Unilever",1.9),("Maruti Suzuki",1.7),("Sun Pharma",1.6),("NTPC",1.4),("Titan Company",1.3),("Wipro",1.2),("UltraTech Cement",1.1)])
    add("Bandhan Large Cap Fund","Bandhan","Large Cap",[("HDFC Bank",10.1),("ICICI Bank",8.3),("Reliance Industries",7.0),("Infosys",6.4),("TCS",5.2),("Larsen & Toubro",4.7),("ITC",3.9),("Bharti Airtel",3.5),("State Bank of India",3.1),("Bajaj Finance",2.8),("Axis Bank",2.5),("Kotak Mahindra Bank",2.3),("HCL Technologies",2.1),("Hindustan Unilever",1.8),("Maruti Suzuki",1.7),("Sun Pharma",1.5),("NTPC",1.4),("Titan Company",1.3),("Mahindra & Mahindra",1.2),("Power Grid Corp",1.1)])

    # Mid Cap (7)
    add("Axis Midcap Fund","Axis","Mid Cap",[("Persistent Systems",5.2),("Cholamandalam Inv",4.8),("Voltas",4.3),("Federal Bank",3.9),("Coforge",3.6),("Sundaram Finance",3.3),("Astral",3.1),("Supreme Industries",2.9),("Trent",2.7),("PI Industries",2.5),("APL Apollo Tubes",2.3),("Dalmia Bharat",2.1),("Mphasis",2.0),("Schaeffler India",1.9),("Page Industries",1.8),("Indian Hotels",1.7),("Bajaj Finance",1.6),("Bharti Airtel",1.5),("HDFC Bank",1.3),("ICICI Bank",1.1)])
    add("DSP Midcap Fund","DSP","Mid Cap",[("Persistent Systems",4.8),("Coforge",4.2),("Cholamandalam Inv",3.9),("Federal Bank",3.5),("Supreme Industries",3.2),("Indian Hotels",3.0),("Trent",2.8),("Sundaram Finance",2.6),("PI Industries",2.4),("APL Apollo Tubes",2.2),("Mphasis",2.1),("Page Industries",2.0),("Astral",1.9),("KPIT Technologies",1.7),("Voltas",1.6),("Schaeffler India",1.5),("Max Healthcare",1.4),("Bharat Forge",1.3),("Dalmia Bharat",1.2),("Crompton Greaves CE",1.1)])
    add("HDFC Mid-Cap Opportunities Fund","HDFC","Mid Cap",[("Indian Hotels",4.5),("Persistent Systems",4.0),("Cholamandalam Inv",3.6),("Federal Bank",3.3),("Coforge",3.0),("Trent",2.8),("Supreme Industries",2.5),("Max Healthcare",2.3),("Voltas",2.1),("PI Industries",2.0),("APL Apollo Tubes",1.9),("Bharat Forge",1.8),("Mphasis",1.7),("Astral",1.6),("Dalmia Bharat",1.5),("Sundaram Finance",1.4),("KPIT Technologies",1.3),("Page Industries",1.2),("Schaeffler India",1.1),("Crompton Greaves CE",1.0)])
    add("Kotak Emerging Equity Fund","Kotak Mahindra","Mid Cap",[("Persistent Systems",4.5),("Coforge",4.0),("Cholamandalam Inv",3.7),("Federal Bank",3.3),("Trent",3.0),("Supreme Industries",2.8),("Indian Hotels",2.6),("Sundaram Finance",2.4),("Voltas",2.2),("PI Industries",2.0),("Max Healthcare",1.9),("APL Apollo Tubes",1.8),("Page Industries",1.7),("Astral",1.6),("Bharat Forge",1.5),("Mphasis",1.4),("KPIT Technologies",1.3),("Schaeffler India",1.2),("Dalmia Bharat",1.1),("Crompton Greaves CE",1.0)])
    add("Motilal Oswal Midcap Fund","Motilal Oswal","Mid Cap",[("Kalyan Jewellers",5.1),("Persistent Systems",4.6),("Polycab India",4.2),("Coforge",3.8),("Max Healthcare",3.4),("Jio Financial",3.1),("Federal Bank",2.8),("Tube Investments",2.5),("Indian Hotels",2.3),("PI Industries",2.1),("KEI Industries",1.9),("Supreme Industries",1.8),("BSE Ltd",1.7),("Cholamandalam Inv",1.6),("Trent",1.5),("Dixon Technologies",1.4),("KPIT Technologies",1.3),("Bharat Forge",1.2),("Mphasis",1.1),("Sundaram Finance",1.0)])
    add("PGIM India Midcap Opportunities Fund","PGIM India","Mid Cap",[("Persistent Systems",5.5),("Indian Hotels",4.1),("Cholamandalam Inv",3.7),("Max Healthcare",3.4),("Coforge",3.1),("PI Industries",2.8),("Federal Bank",2.6),("APL Apollo Tubes",2.3),("Supreme Industries",2.1),("Bharat Forge",1.9),("Trent",1.8),("Dixon Technologies",1.7),("Mphasis",1.6),("Sundaram Finance",1.5),("Astral",1.4),("KPIT Technologies",1.3),("Page Industries",1.2),("Schaeffler India",1.1),("Voltas",1.0),("Crompton Greaves CE",0.9)])
    add("Canara Robeco Emerging Equities","Canara Robeco","Mid Cap",[("Persistent Systems",4.2),("Cholamandalam Inv",3.8),("Federal Bank",3.5),("Coforge",3.2),("Trent",3.0),("Indian Hotels",2.8),("Supreme Industries",2.6),("PI Industries",2.4),("Sundaram Finance",2.2),("APL Apollo Tubes",2.0),("Page Industries",1.9),("KPIT Technologies",1.8),("Bharat Forge",1.7),("Max Healthcare",1.6),("HDFC Bank",1.5),("ICICI Bank",1.4),("Voltas",1.3),("Astral",1.2),("Blue Star",1.1),("Crompton Greaves CE",1.0)])

    # Small Cap (6)
    add("SBI Small Cap Fund","SBI","Small Cap",[("IIFL Finance",3.2),("Chalet Hotels",2.9),("Finolex Industries",2.7),("Blue Star",2.5),("Ratnamani Metals",2.4),("IIFL Wealth Mgmt",2.3),("Elgi Equipments",2.1),("Cera Sanitaryware",2.0),("EIH",1.9),("CMS Info Systems",1.8),("Mold-Tek Packaging",1.7),("Karur Vysya Bank",1.6),("Quess Corp",1.5),("KPIT Technologies",1.4),("SJS Enterprises",1.3),("Aether Industries",1.2),("Praj Industries",1.1),("Galaxy Surfactants",1.0),("Clean Science & Tech",0.9),("Lemon Tree Hotels",0.8)])
    add("Nippon India Small Cap Fund","Nippon India","Small Cap",[("KPIT Technologies",2.8),("Tube Investments",2.5),("Carborundum Universal",2.2),("Blue Star",2.0),("Bharat Forge",1.9),("Crompton Greaves CE",1.8),("IIFL Finance",1.7),("Finolex Industries",1.6),("Ratnamani Metals",1.5),("EIH",1.4),("Praj Industries",1.3),("Elgi Equipments",1.2),("Galaxy Surfactants",1.1),("CMS Info Systems",1.0),("Aether Industries",0.9),("Lemon Tree Hotels",0.8),("SJS Enterprises",0.7),("Clean Science & Tech",0.7),("Quess Corp",0.6),("Cera Sanitaryware",0.6)])
    add("Axis Small Cap Fund","Axis","Small Cap",[("CCL Products",3.1),("Brigade Enterprises",2.8),("Galaxy Surfactants",2.5),("TeamLease Services",2.3),("Sapphire Foods",2.1),("CMS Info Systems",1.9),("EIH",1.8),("Birlasoft",1.7),("IIFL Finance",1.6),("Chalet Hotels",1.5),("Finolex Industries",1.4),("Blue Star",1.3),("Praj Industries",1.2),("Cera Sanitaryware",1.1),("SJS Enterprises",1.0),("Quess Corp",0.9),("Elgi Equipments",0.8),("Ratnamani Metals",0.7),("Lemon Tree Hotels",0.6),("Mastek",0.5)])
    add("HDFC Small Cap Fund","HDFC","Small Cap",[("Firstsource Solutions",3.0),("eClerx Services",2.7),("Aarti Industries",2.4),("Blue Star",2.2),("Sonata Software",2.0),("Bank of Baroda",1.9),("Carborundum Universal",1.8),("IIFL Finance",1.7),("Bharat Forge",1.6),("Finolex Industries",1.5),("Crompton Greaves CE",1.4),("EIH",1.3),("Praj Industries",1.2),("Elgi Equipments",1.1),("Galaxy Surfactants",1.0),("CMS Info Systems",0.9),("Quess Corp",0.8),("Ratnamani Metals",0.7),("Cera Sanitaryware",0.6),("Aether Industries",0.5)])
    add("Kotak Small Cap Fund","Kotak Mahindra","Small Cap",[("Blue Star",3.3),("Cyient",2.9),("Century Textiles",2.6),("Kaynes Technology",2.4),("CMS Info Systems",2.2),("Finolex Industries",2.0),("Cera Sanitaryware",1.8),("EIH",1.7),("IIFL Finance",1.6),("Quess Corp",1.5),("Praj Industries",1.4),("Elgi Equipments",1.3),("Galaxy Surfactants",1.2),("SJS Enterprises",1.1),("Ratnamani Metals",1.0),("Mold-Tek Packaging",0.9),("Lemon Tree Hotels",0.8),("Aether Industries",0.7),("Clean Science & Tech",0.6),("Mastek",0.5)])
    add("Quant Small Cap Fund","Quant","Small Cap",[("Reliance Industries",5.8),("IRB Infrastructure",4.2),("Jio Financial",3.5),("Bikaji Foods",3.1),("ONGC",2.8),("Steel Authority",2.5),("Laurus Labs",2.2),("IRFC",2.0),("Hinduja Global",1.8),("Jubilant FoodWorks",1.6),("Aurobindo Pharma",1.5),("Chambal Fertilisers",1.4),("GNFC",1.3),("IEX",1.2),("Cyient",1.1),("Blue Star",1.0),("Canara Bank",0.9),("Motilal Oswal Fin",0.8),("Bharat Electronics",0.7),("HUDCO",0.6)])

    # Flexi Cap (5)
    add("Parag Parikh Flexi Cap Fund","PPFAS","Flexi Cap",[("HDFC Bank",7.5),("ICICI Bank",5.2),("ITC",4.8),("Bajaj Holdings",4.5),("Power Grid Corp",4.1),("Coal India",3.8),("HCL Technologies",3.5),("Bharti Airtel",3.2),("Maruti Suzuki",2.9),("Axis Bank",2.6),("NTPC",2.4),("Wipro",2.2),("Infosys",2.0),("Reliance Industries",1.8),("TCS",1.6),("Balkrishna Industries",1.5),("Zydus Lifesciences",1.4),("Oracle Financial",1.3),("Mahindra & Mahindra",1.2),("Motilal Oswal Fin",1.1)])
    add("HDFC Flexi Cap Fund","HDFC","Flexi Cap",[("ICICI Bank",9.5),("HDFC Bank",8.2),("Reliance Industries",6.8),("Infosys",5.5),("ITC",5.0),("Larsen & Toubro",4.5),("TCS",4.0),("State Bank of India",3.6),("Bharti Airtel",3.2),("Axis Bank",2.8),("Bajaj Finance",2.5),("HCL Technologies",2.2),("NTPC",2.0),("Kotak Mahindra Bank",1.8),("Sun Pharma",1.6),("Hindustan Unilever",1.5),("Maruti Suzuki",1.4),("Titan Company",1.3),("Mahindra & Mahindra",1.2),("UltraTech Cement",1.1)])
    add("JM Flexicap Fund","JM Financial","Flexi Cap",[("ICICI Bank",8.2),("HDFC Bank",6.8),("Reliance Industries",5.5),("Larsen & Toubro",5.0),("State Bank of India",4.3),("Infosys",3.8),("ITC",3.5),("NTPC",3.2),("Bharti Airtel",2.9),("Axis Bank",2.6),("TCS",2.4),("HCL Technologies",2.1),("Mahindra & Mahindra",2.0),("Coal India",1.8),("Power Grid Corp",1.6),("Bajaj Finance",1.5),("Oil India",1.4),("BPCL",1.3),("Bharat Electronics",1.2),("Titan Company",1.1)])
    add("Quant Flexi Cap Fund","Quant","Flexi Cap",[("Reliance Industries",8.5),("HDFC Bank",5.8),("Jio Financial",4.5),("Adani Ports",3.8),("ITC",3.5),("IRB Infrastructure",3.2),("State Bank of India",2.9),("Aurobindo Pharma",2.6),("Larsen & Toubro",2.4),("NTPC",2.2),("Bharti Airtel",2.0),("Laurus Labs",1.8),("Steel Authority",1.6),("ONGC",1.5),("Bikaji Foods",1.4),("Bajaj Finance",1.3),("IRFC",1.2),("Infosys",1.1),("Bharat Electronics",1.0),("Chambal Fertilisers",0.9)])
    add("DSP Flexi Cap Fund","DSP","Flexi Cap",[("HDFC Bank",8.5),("ICICI Bank",6.9),("Infosys",5.8),("Reliance Industries",5.2),("TCS",4.5),("Larsen & Toubro",4.0),("Bharti Airtel",3.5),("State Bank of India",3.1),("ITC",2.8),("Bajaj Finance",2.5),("Axis Bank",2.3),("HCL Technologies",2.1),("Kotak Mahindra Bank",1.9),("Sun Pharma",1.7),("Maruti Suzuki",1.6),("Hindustan Unilever",1.5),("NTPC",1.4),("Titan Company",1.3),("Mahindra & Mahindra",1.2),("UltraTech Cement",1.0)])

    # Large & Mid Cap (4)
    add("Mirae Asset Large & Midcap Fund","Mirae Asset","Large & Mid Cap",[("HDFC Bank",8.1),("ICICI Bank",6.5),("Reliance Industries",5.8),("Infosys",4.9),("TCS",4.2),("Larsen & Toubro",3.8),("Bharti Airtel",3.3),("Persistent Systems",2.9),("State Bank of India",2.7),("Cholamandalam Inv",2.5),("ITC",2.3),("Bajaj Finance",2.1),("Federal Bank",1.9),("Kotak Mahindra Bank",1.8),("Coforge",1.7),("HCL Technologies",1.6),("Supreme Industries",1.5),("Trent",1.4),("Axis Bank",1.3),("Sun Pharma",1.2)])
    add("SBI Large & Midcap Fund","SBI","Large & Mid Cap",[("HDFC Bank",7.8),("ICICI Bank",6.2),("Reliance Industries",5.5),("Infosys",4.8),("TCS",4.1),("Larsen & Toubro",3.7),("Bharti Airtel",3.2),("State Bank of India",2.9),("ITC",2.7),("Bajaj Finance",2.4),("Cholamandalam Inv",2.2),("Federal Bank",2.0),("Kotak Mahindra Bank",1.9),("Persistent Systems",1.8),("HCL Technologies",1.7),("Axis Bank",1.6),("Indian Hotels",1.5),("Sun Pharma",1.4),("Maruti Suzuki",1.3),("Trent",1.2)])
    add("ICICI Prudential Large & Mid Cap Fund","ICICI Prudential","Large & Mid Cap",[("ICICI Bank",8.5),("HDFC Bank",7.2),("Reliance Industries",6.0),("Infosys",5.1),("TCS",4.3),("Larsen & Toubro",3.9),("State Bank of India",3.4),("Bharti Airtel",3.1),("ITC",2.8),("Axis Bank",2.5),("Bajaj Finance",2.3),("Persistent Systems",2.1),("HCL Technologies",1.9),("Kotak Mahindra Bank",1.8),("Federal Bank",1.7),("Cholamandalam Inv",1.6),("Sun Pharma",1.5),("Mahindra & Mahindra",1.4),("Maruti Suzuki",1.3),("NTPC",1.2)])
    add("HDFC Large and Mid Cap Fund","HDFC","Large & Mid Cap",[("ICICI Bank",8.8),("HDFC Bank",7.5),("Reliance Industries",5.8),("Larsen & Toubro",5.0),("Infosys",4.5),("TCS",3.9),("State Bank of India",3.5),("ITC",3.2),("Bharti Airtel",2.9),("Axis Bank",2.6),("Indian Hotels",2.3),("Bajaj Finance",2.1),("Persistent Systems",1.9),("HCL Technologies",1.8),("Cholamandalam Inv",1.7),("Federal Bank",1.6),("NTPC",1.5),("Kotak Mahindra Bank",1.4),("Sun Pharma",1.3),("Mahindra & Mahindra",1.2)])

    # Value / Contra (4), Focused (3), ELSS (5), Index (5), Hybrid (3), Sectoral (6) — same as before
    add("ICICI Prudential Value Discovery Fund","ICICI Prudential","Value / Contra",[("ICICI Bank",7.5),("NTPC",5.8),("ITC",5.2),("State Bank of India",4.8),("ONGC",4.2),("Infosys",3.9),("Larsen & Toubro",3.5),("HDFC Bank",3.3),("Sun Pharma",3.0),("Bharti Airtel",2.8),("TCS",2.5),("Axis Bank",2.3),("HCL Technologies",2.1),("Power Grid Corp",2.0),("Coal India",1.8),("Hindustan Unilever",1.6),("Maruti Suzuki",1.5),("Bajaj Finance",1.4),("Mahindra & Mahindra",1.3),("Tech Mahindra",1.2)])
    add("SBI Contra Fund","SBI","Value / Contra",[("HDFC Bank",6.8),("ICICI Bank",5.5),("ITC",5.0),("Reliance Industries",4.5),("State Bank of India",4.0),("Larsen & Toubro",3.6),("NTPC",3.2),("Coal India",2.8),("Infosys",2.5),("Axis Bank",2.3),("TCS",2.1),("ONGC",2.0),("Power Grid Corp",1.8),("Bharti Airtel",1.7),("HCL Technologies",1.6),("Mahindra & Mahindra",1.5),("BPCL",1.4),("Sun Pharma",1.3),("GAIL India",1.2),("Bharat Electronics",1.1)])
    add("Nippon India Value Fund","Nippon India","Value / Contra",[("ICICI Bank",7.0),("HDFC Bank",6.2),("Reliance Industries",5.5),("State Bank of India",4.8),("ITC",4.2),("Larsen & Toubro",3.8),("NTPC",3.4),("Infosys",3.0),("Bharti Airtel",2.7),("TCS",2.4),("Coal India",2.2),("Axis Bank",2.0),("Power Grid Corp",1.9),("Sun Pharma",1.7),("HCL Technologies",1.6),("Mahindra & Mahindra",1.5),("ONGC",1.4),("Bajaj Finance",1.3),("Maruti Suzuki",1.2),("Hindustan Unilever",1.1)])
    add("Invesco India Contra Fund","Invesco","Value / Contra",[("HDFC Bank",7.2),("ICICI Bank",6.0),("Reliance Industries",5.5),("Infosys",4.8),("TCS",4.2),("Larsen & Toubro",3.8),("ITC",3.4),("Bharti Airtel",3.0),("State Bank of India",2.7),("Bajaj Finance",2.5),("HCL Technologies",2.2),("NTPC",2.0),("Axis Bank",1.9),("Sun Pharma",1.7),("Kotak Mahindra Bank",1.6),("Titan Company",1.5),("Mahindra & Mahindra",1.4),("UltraTech Cement",1.3),("Maruti Suzuki",1.2),("Hindustan Unilever",1.1)])

    add("Axis Focused 25 Fund","Axis","Focused Fund",[("HDFC Bank",9.5),("ICICI Bank",8.0),("Infosys",7.2),("Bajaj Finance",6.5),("TCS",5.8),("Kotak Mahindra Bank",5.0),("Reliance Industries",4.5),("Bharti Airtel",4.0),("Larsen & Toubro",3.5),("Avenue Supermarts",3.0),("HCL Technologies",2.8),("Titan Company",2.5),("Asian Paints",2.3),("Hindustan Unilever",2.1),("Divi's Laboratories",1.9),("Maruti Suzuki",1.8),("Nestle India",1.7),("Sun Pharma",1.5),("SBI Life Insurance",1.4),("Wipro",1.2)])
    add("SBI Focused Equity Fund","SBI","Focused Fund",[("HDFC Bank",8.8),("ICICI Bank",7.5),("Reliance Industries",6.5),("Infosys",5.8),("TCS",5.0),("Larsen & Toubro",4.5),("Bharti Airtel",4.0),("State Bank of India",3.5),("Bajaj Finance",3.2),("ITC",2.8),("HCL Technologies",2.5),("Kotak Mahindra Bank",2.3),("Axis Bank",2.1),("Sun Pharma",1.9),("Titan Company",1.7),("Hindustan Unilever",1.6),("Maruti Suzuki",1.5),("NTPC",1.4),("Asian Paints",1.3),("Mahindra & Mahindra",1.2)])
    add("Mirae Asset Focused Fund","Mirae Asset","Focused Fund",[("HDFC Bank",9.8),("ICICI Bank",8.2),("Reliance Industries",7.0),("Infosys",6.2),("TCS",5.5),("Larsen & Toubro",4.8),("Bharti Airtel",4.2),("Bajaj Finance",3.5),("State Bank of India",3.0),("ITC",2.7),("HCL Technologies",2.4),("Kotak Mahindra Bank",2.2),("Axis Bank",2.0),("Titan Company",1.8),("Sun Pharma",1.6),("Hindustan Unilever",1.5),("Maruti Suzuki",1.4),("NTPC",1.3),("UltraTech Cement",1.2),("Power Grid Corp",1.1)])

    add("Axis Long Term Equity Fund","Axis","ELSS",[("HDFC Bank",8.8),("ICICI Bank",7.5),("Infosys",6.8),("Bajaj Finance",5.2),("TCS",4.8),("Kotak Mahindra Bank",4.1),("Reliance Industries",3.8),("Bharti Airtel",3.4),("Larsen & Toubro",3.0),("Avenue Supermarts",2.7),("HCL Technologies",2.5),("Titan Company",2.3),("Asian Paints",2.1),("Hindustan Unilever",1.9),("Divi's Laboratories",1.7),("Maruti Suzuki",1.5),("Sun Pharma",1.3),("Nestle India",1.2),("SBI Life Insurance",1.1),("Wipro",1.0)])
    add("Mirae Asset Tax Saver Fund","Mirae Asset","ELSS",[("HDFC Bank",9.5),("ICICI Bank",7.8),("Reliance Industries",6.5),("Infosys",5.8),("TCS",5.0),("Larsen & Toubro",4.3),("Bharti Airtel",3.8),("Axis Bank",3.2),("State Bank of India",3.0),("ITC",2.7),("Bajaj Finance",2.5),("HCL Technologies",2.2),("Kotak Mahindra Bank",2.0),("Sun Pharma",1.8),("Maruti Suzuki",1.6),("Hindustan Unilever",1.5),("Titan Company",1.4),("NTPC",1.3),("UltraTech Cement",1.2),("Power Grid Corp",1.0)])
    add("Quant Tax Plan","Quant","ELSS",[("Reliance Industries",7.8),("HDFC Bank",5.2),("Jio Financial",4.0),("ITC",3.5),("Adani Ports",3.2),("State Bank of India",2.9),("IRB Infrastructure",2.6),("NTPC",2.4),("Aurobindo Pharma",2.2),("Larsen & Toubro",2.0),("Steel Authority",1.8),("Bharti Airtel",1.7),("Bikaji Foods",1.5),("ONGC",1.4),("Laurus Labs",1.3),("Infosys",1.2),("IRFC",1.1),("Bharat Electronics",1.0),("Chambal Fertilisers",0.9),("Coal India",0.8)])
    add("SBI Long Term Equity Fund","SBI","ELSS",[("HDFC Bank",8.2),("ICICI Bank",6.8),("Reliance Industries",5.8),("Infosys",5.2),("TCS",4.5),("Larsen & Toubro",4.0),("Bharti Airtel",3.5),("State Bank of India",3.1),("ITC",2.8),("Bajaj Finance",2.5),("Axis Bank",2.3),("HCL Technologies",2.1),("Kotak Mahindra Bank",1.9),("Sun Pharma",1.7),("Maruti Suzuki",1.5),("Hindustan Unilever",1.4),("Titan Company",1.3),("NTPC",1.2),("Mahindra & Mahindra",1.1),("UltraTech Cement",1.0)])
    add("ABSL Tax Relief 96","Aditya Birla Sun Life","ELSS",[("HDFC Bank",8.5),("ICICI Bank",7.2),("Infosys",6.0),("Reliance Industries",5.5),("TCS",4.8),("Larsen & Toubro",4.2),("ITC",3.8),("Bharti Airtel",3.4),("State Bank of India",3.0),("Bajaj Finance",2.7),("Axis Bank",2.4),("Kotak Mahindra Bank",2.1),("HCL Technologies",1.9),("Hindustan Unilever",1.7),("Sun Pharma",1.5),("Maruti Suzuki",1.4),("Titan Company",1.3),("NTPC",1.2),("Wipro",1.1),("UltraTech Cement",1.0)])

    add("UTI Nifty 50 Index Fund","UTI","Index Funds",[("HDFC Bank",12.5),("Reliance Industries",10.2),("ICICI Bank",8.1),("Infosys",6.3),("TCS",4.8),("Larsen & Toubro",4.2),("ITC",4.0),("Bharti Airtel",3.8),("State Bank of India",3.4),("Axis Bank",3.0),("Bajaj Finance",2.6),("Kotak Mahindra Bank",2.3),("HCL Technologies",2.1),("Hindustan Unilever",1.9),("Maruti Suzuki",1.7),("Sun Pharma",1.5),("Titan Company",1.4),("NTPC",1.3),("Asian Paints",1.2),("Power Grid Corp",1.1)])
    add("HDFC Index Fund Nifty 50 Plan","HDFC","Index Funds",[("HDFC Bank",12.4),("Reliance Industries",10.1),("ICICI Bank",8.0),("Infosys",6.2),("TCS",4.7),("Larsen & Toubro",4.1),("ITC",3.9),("Bharti Airtel",3.7),("State Bank of India",3.4),("Axis Bank",2.9),("Bajaj Finance",2.6),("Kotak Mahindra Bank",2.3),("HCL Technologies",2.1),("Hindustan Unilever",1.9),("Maruti Suzuki",1.7),("Sun Pharma",1.5),("Titan Company",1.4),("NTPC",1.3),("Asian Paints",1.2),("Power Grid Corp",1.1)])
    add("UTI Nifty Next 50 Index Fund","UTI","Index Funds",[("Adani Enterprises",4.8),("Zomato",4.5),("Jio Financial",4.2),("Vedanta",3.8),("Trent",3.5),("Indian Oil Corp",3.2),("BPCL",3.0),("Siemens India",2.8),("Pidilite Industries",2.6),("Cholamandalam Inv",2.4),("GAIL India",2.2),("DLF",2.0),("Godrej Consumer",1.9),("Shriram Finance",1.8),("Dabur India",1.7),("Ambuja Cements",1.6),("Havells India",1.5),("Info Edge India",1.4),("ABB India",1.3),("Jindal Steel & Power",1.2)])
    add("Motilal Oswal Nifty 50 Index Fund","Motilal Oswal","Index Funds",[("HDFC Bank",12.3),("Reliance Industries",10.0),("ICICI Bank",8.0),("Infosys",6.2),("TCS",4.7),("Larsen & Toubro",4.1),("ITC",3.9),("Bharti Airtel",3.7),("State Bank of India",3.3),("Axis Bank",2.9),("Bajaj Finance",2.5),("Kotak Mahindra Bank",2.2),("HCL Technologies",2.0),("Hindustan Unilever",1.8),("Maruti Suzuki",1.6),("Sun Pharma",1.4),("Titan Company",1.3),("NTPC",1.2),("Asian Paints",1.1),("Power Grid Corp",1.0)])
    add("Motilal Oswal Nifty Midcap 150 Index Fund","Motilal Oswal","Index Funds",[("Persistent Systems",2.5),("Indian Hotels",2.3),("Suzlon Energy",2.1),("Max Healthcare",2.0),("Federal Bank",1.9),("Dixon Technologies",1.8),("Coforge",1.7),("BSE Ltd",1.6),("Polycab India",1.5),("Tube Investments",1.4),("Mphasis",1.3),("APL Apollo Tubes",1.2),("Bharat Forge",1.1),("Supreme Industries",1.0),("KPIT Technologies",0.9),("KEI Industries",0.8),("Sundaram Finance",0.7),("CG Power & Ind",0.7),("Voltas",0.6),("Astral",0.6)])

    add("SBI Equity Hybrid Fund","SBI","Aggressive Hybrid Fund",[("HDFC Bank",7.2),("ICICI Bank",6.1),("Infosys",4.8),("Reliance Industries",4.5),("TCS",3.8),("Larsen & Toubro",3.3),("Bharti Airtel",2.9),("ITC",2.7),("State Bank of India",2.5),("Bajaj Finance",2.3),("Axis Bank",2.1),("Kotak Mahindra Bank",1.9),("HCL Technologies",1.7),("Hindustan Unilever",1.5),("Sun Pharma",1.4),("Titan Company",1.3),("Maruti Suzuki",1.2),("NTPC",1.1),("Asian Paints",1.0),("Mahindra & Mahindra",0.9)])
    add("ICICI Prudential Balanced Advantage Fund","ICICI Prudential","Balanced Advantage Fund",[("ICICI Bank",6.8),("HDFC Bank",5.9),("Reliance Industries",5.0),("Infosys",4.2),("TCS",3.5),("Larsen & Toubro",3.1),("State Bank of India",2.8),("ITC",2.5),("Bharti Airtel",2.3),("Axis Bank",2.1),("NTPC",1.9),("Bajaj Finance",1.8),("HCL Technologies",1.6),("Kotak Mahindra Bank",1.5),("Sun Pharma",1.4),("Maruti Suzuki",1.3),("Hindustan Unilever",1.2),("Titan Company",1.1),("Mahindra & Mahindra",1.0),("Power Grid Corp",0.9)])
    add("HDFC Balanced Advantage Fund","HDFC","Balanced Advantage Fund",[("ICICI Bank",7.2),("HDFC Bank",6.5),("Reliance Industries",5.2),("ITC",4.5),("Larsen & Toubro",4.0),("Infosys",3.5),("TCS",3.1),("State Bank of India",2.8),("Bharti Airtel",2.5),("Axis Bank",2.3),("NTPC",2.1),("Coal India",1.9),("Bajaj Finance",1.7),("HCL Technologies",1.5),("Kotak Mahindra Bank",1.4),("Sun Pharma",1.3),("Mahindra & Mahindra",1.2),("Power Grid Corp",1.1),("Maruti Suzuki",1.0),("Hindustan Unilever",0.9)])

    add("Tata Digital India Fund","Tata","Sectoral/Thematic",[("Infosys",18.5),("TCS",16.2),("HCL Technologies",9.8),("Wipro",6.5),("Tech Mahindra",5.8),("LTIMindtree",5.2),("Persistent Systems",4.5),("Coforge",3.8),("Mphasis",3.5),("KPIT Technologies",3.2),("Cyient",2.5),("Birlasoft",2.2),("Zensar Technologies",2.0),("Oracle Financial",1.8),("Mastek",1.5),("Tata Elxsi",1.2),("Firstsource Solutions",1.0),("Sonata Software",0.9),("eClerx Services",0.8)])
    add("ICICI Prudential Technology Fund","ICICI Prudential","Sectoral/Thematic",[("Infosys",19.2),("TCS",15.8),("HCL Technologies",10.5),("Wipro",7.0),("Tech Mahindra",6.2),("LTIMindtree",4.8),("Persistent Systems",4.0),("Coforge",3.5),("Mphasis",3.0),("KPIT Technologies",2.5),("Cyient",2.0),("Mastek",1.5),("Tata Elxsi",1.3),("Oracle Financial",1.2),("Birlasoft",1.1),("Zensar Technologies",1.0),("Firstsource Solutions",0.9),("eClerx Services",0.8),("Sonata Software",0.7)])
    add("SBI Healthcare Opportunities Fund","SBI","Sectoral/Thematic",[("Sun Pharma",12.5),("Dr Reddy's Labs",9.8),("Cipla",8.5),("Divi's Laboratories",7.2),("Apollo Hospitals",6.5),("Max Healthcare",5.8),("Aurobindo Pharma",4.5),("Torrent Pharma",3.8),("Lupin",3.2),("Zydus Lifesciences",2.8),("Laurus Labs",2.4),("Alkem Laboratories",2.1),("Biocon",1.9),("Glenmark Pharma",1.6),("Ipca Laboratories",1.4),("JB Chemicals",1.2),("Fortis Healthcare",1.1),("Narayana Hrudayalaya",1.0),("Syngene International",0.9),("Natco Pharma",0.8)])
    add("Nippon India Pharma Fund","Nippon India","Sectoral/Thematic",[("Sun Pharma",13.0),("Dr Reddy's Labs",10.2),("Cipla",8.8),("Divi's Laboratories",6.5),("Apollo Hospitals",5.8),("Lupin",5.0),("Aurobindo Pharma",4.2),("Torrent Pharma",3.5),("Max Healthcare",3.0),("Zydus Lifesciences",2.6),("Laurus Labs",2.2),("Biocon",1.8),("Glenmark Pharma",1.5),("Alkem Laboratories",1.3),("JB Chemicals",1.2),("Ipca Laboratories",1.1),("Fortis Healthcare",1.0),("Natco Pharma",0.9),("Syngene International",0.8)])
    add("ICICI Prudential Infrastructure Fund","ICICI Prudential","Sectoral/Thematic",[("Larsen & Toubro",12.5),("NTPC",8.8),("Power Grid Corp",6.5),("Bharti Airtel",5.8),("Adani Ports",5.0),("NHPC",4.2),("Siemens India",3.8),("ABB India",3.5),("Thermax",3.0),("IRB Infrastructure",2.6),("IRFC",2.3),("HUDCO",2.0),("Bharat Electronics",1.8),("KEC International",1.6),("Cummins India",1.4),("Polycab India",1.3),("CG Power & Ind",1.2),("Kalpataru Projects",1.1),("PNC Infratech",1.0),("NCC",0.9)])
    add("Quant Infrastructure Fund","Quant","Sectoral/Thematic",[("Reliance Industries",8.0),("Larsen & Toubro",6.5),("Adani Ports",5.2),("IRB Infrastructure",4.5),("NTPC",4.0),("IRFC",3.5),("Siemens India",3.0),("Power Grid Corp",2.7),("NHPC",2.4),("Jio Financial",2.2),("Bharat Electronics",2.0),("ABB India",1.8),("HUDCO",1.6),("Steel Authority",1.5),("Bharti Airtel",1.4),("CG Power & Ind",1.3),("Coal India",1.2),("NCC",1.1),("KEC International",1.0),("Thermax",0.9)])

    return data


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update MF Overlap App snapshot.py")
    parser.add_argument("--fallback", action="store_true", help="Use curated data (no network)")
    parser.add_argument("--output", default="snapshot.py", help="Output file path")
    args = parser.parse_args()

    if args.fallback:
        print("Using curated fallback data...")
        schemes = get_curated_data()
        date = datetime.now().strftime("%Y-%m")
    else:
        print("Fetching live data from MFData.in...")
        schemes, date, errors = fetch_all_live()
        if not schemes:
            print("Live fetch failed completely. Falling back to curated data.")
            schemes = get_curated_data()
            date = datetime.now().strftime("%Y-%m")
        elif errors:
            # Merge curated data for failed funds
            curated = get_curated_data()
            curated_by_name = {v["name"]: (k, v) for k, v in curated.items()}
            for err_name in errors:
                for cname, (cid, cdata) in curated_by_name.items():
                    if err_name.lower() in cname.lower():
                        if cid not in schemes:
                            schemes[cid] = cdata
                            print(f"  Filled gap with curated: {cname}")
                        break

    generate_snapshot_py(schemes, date or datetime.now().strftime("%Y-%m"), args.output)
    print("Done!")


if __name__ == "__main__":
    main()
