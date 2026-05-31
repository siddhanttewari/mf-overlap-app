#!/usr/bin/env python3
"""
MF Overlap — Groww.in Scraper + Supabase Seeder
=================================================
Scrapes equity mutual fund holdings from Groww.in (server-rendered HTML).
Uses AMFI NAV text file for the complete scheme list.

Groww.in serves holdings in plain HTML tables — no JS rendering needed.

Usage:
  export SUPABASE_URL="https://xxx.supabase.co"
  export SUPABASE_KEY="eyJ..."
  python scrape_groww.py                    # scrape + seed Supabase + update snapshot
  python scrape_groww.py --snapshot-only    # just update snapshot.py
  python scrape_groww.py --dry-run          # scrape only, print results

Requires: pip install requests beautifulsoup4 lxml
"""

import argparse, json, os, re, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}
DELAY = 2.0
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
GROWW_BASE = "https://groww.in/mutual-funds"

session = requests.Session()
session.headers.update(HEADERS)


def fetch_amfi_schemes():
    """Fetch all Direct Growth equity schemes from AMFI NAV text file."""
    print("Fetching AMFI scheme list...")
    resp = session.get(AMFI_NAV_URL, timeout=30)
    if resp.status_code != 200:
        print(f"  AMFI fetch failed: HTTP {resp.status_code}")
        return []

    schemes = []
    current_amc = ""
    equity_cats = {
        "large cap", "mid cap", "small cap", "multi cap", "flexi cap",
        "large & mid cap", "elss", "value fund", "contra fund",
        "focused fund", "dividend yield", "sectoral/thematic",
        "index funds", "aggressive hybrid fund", "balanced advantage fund",
        "equity savings", "multi asset allocation",
    }

    for line in resp.text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # AMC header lines don't have semicolons
        if ";" not in line and "Mutual Fund" in line:
            current_amc = line.strip()
            continue

        parts = line.split(";")
        if len(parts) < 6:
            continue

        scheme_code = parts[0].strip()
        scheme_name = parts[1].strip() if len(parts) > 1 else ""

        # Only Direct Growth plans
        if "Direct" not in scheme_name or "Growth" not in scheme_name:
            continue

        # Try to detect category (AMFI doesn't label categories in this file,
        # but we can infer from scheme name or just take all equity schemes)
        name_lower = scheme_name.lower()

        # Filter: skip debt, liquid, overnight, gilt, money market etc.
        skip_keywords = ["liquid", "overnight", "gilt", "money market", "debt",
                         "credit risk", "banking and psu", "floater", "corporate bond",
                         "low duration", "medium duration", "short duration",
                         "long duration", "ultra short", "dynamic bond", "target maturity",
                         "fixed maturity", "gold", "silver", "commodit", "etf",
                         "fund of fund", "fof", "retirement", "children",
                         "interval", "capital protection"]
        if any(kw in name_lower for kw in skip_keywords):
            continue

        schemes.append({
            "amfi_code": scheme_code,
            "raw_name": scheme_name,
            "amc": current_amc,
        })

    print(f"  Found {len(schemes)} Direct Growth equity schemes from AMFI")
    return schemes


def name_to_groww_slug(raw_name):
    """Convert AMFI scheme name to likely Groww URL slug."""
    name = raw_name.strip()

    # Remove plan/option suffixes
    for suffix in [" - Direct Plan - Growth", " - Direct Plan-Growth",
                   " - Direct - Growth", " -Direct Plan-Growth",
                   " - Direct Plan", " Direct Plan Growth",
                   " Direct Plan - Growth", " Direct-Growth",
                   " - Growth", " -Growth"]:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()

    # Remove "Fund" at the end if present
    if name.endswith(" Fund"):
        name = name[:-5].strip()

    # Lowercase, replace special chars
    slug = name.lower()
    slug = slug.replace("&", "and").replace("'", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug.strip())
    slug = re.sub(r'-+', '-', slug)

    return slug + "-direct-growth"


def fetch_groww_holdings(slug):
    """Fetch and parse holdings from a Groww fund page."""
    url = f"{GROWW_BASE}/{slug}"
    try:
        time.sleep(DELAY)
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return None, None, None
    except Exception:
        return None, None, None

    soup = BeautifulSoup(resp.text, "lxml")

    # Extract fund name from page title
    title_tag = soup.find("h1")
    fund_name = title_tag.get_text(strip=True) if title_tag else ""

    # Find category from breadcrumb or tags
    category = ""
    for link in soup.find_all("a"):
        text = link.get_text(strip=True)
        if text in ["Large Cap", "Mid Cap", "Small Cap", "Flexi Cap", "Multi Cap",
                     "Large & MidCap", "ELSS", "Value Oriented", "Contra",
                     "Focused", "Dividend Yield", "Sectoral", "Thematic",
                     "Aggressive Hybrid", "Balanced Advantage", "Equity Savings",
                     "Index Funds", "Multi Asset Allocation"]:
            category = text
            break

    # Parse holdings table
    holdings = []
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Stock name is usually in first cell with a link
            name_cell = cells[0]
            link = name_cell.find("a")
            stock_name = link.get_text(strip=True) if link else name_cell.get_text(strip=True)
            if not stock_name or len(stock_name) < 2:
                continue

            # Weight/Assets is usually in last cell
            weight_text = cells[-1].get_text(strip=True).replace("%", "").strip()
            try:
                weight = float(weight_text)
                if 0.05 < weight < 100:
                    holdings.append({"stock_name": stock_name, "weight_pct": round(weight, 2)})
            except (ValueError, TypeError):
                continue

    # Also check for holdings in markdown-style text (the fetched content)
    if not holdings:
        # Try regex on full text for "Holdings" section
        text = resp.text
        pattern = re.findall(r'stock_name["\s:]+([^"]+)["\s,]+weight_pct["\s:]+(\d+\.?\d*)', text)
        for name, weight in pattern:
            holdings.append({"stock_name": name.strip(), "weight_pct": round(float(weight), 2)})

    if holdings:
        holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
        holdings = holdings[:25]  # Top 25

    return fund_name, category, holdings


def detect_amc(name):
    """Detect AMC from fund name."""
    patterns = [
        ("HDFC","HDFC Mutual Fund"),("ICICI Prudential","ICICI Prudential Mutual Fund"),
        ("ICICI Pru","ICICI Prudential Mutual Fund"),("SBI","SBI Mutual Fund"),
        ("Axis","Axis Mutual Fund"),("Kotak","Kotak Mahindra Mutual Fund"),
        ("Nippon India","Nippon India Mutual Fund"),("Nippon","Nippon India Mutual Fund"),
        ("Mirae Asset","Mirae Asset Mutual Fund"),("Aditya Birla","Aditya Birla Sun Life Mutual Fund"),
        ("ABSL","Aditya Birla Sun Life Mutual Fund"),("DSP","DSP Mutual Fund"),
        ("Tata","Tata Mutual Fund"),("UTI","UTI Mutual Fund"),
        ("Canara Robeco","Canara Robeco Mutual Fund"),("Franklin","Franklin Templeton Mutual Fund"),
        ("Motilal Oswal","Motilal Oswal Mutual Fund"),("Sundaram","Sundaram Mutual Fund"),
        ("HSBC","HSBC Mutual Fund"),("Invesco","Invesco Mutual Fund"),
        ("Quant","Quant Mutual Fund"),("Parag Parikh","PPFAS Mutual Fund"),
        ("PPFAS","PPFAS Mutual Fund"),("White Oak","White Oak Capital Mutual Fund"),
        ("WhiteOak","White Oak Capital Mutual Fund"),("Bandhan","Bandhan Mutual Fund"),
        ("Edelweiss","Edelweiss Mutual Fund"),("Baroda BNP","Baroda BNP Paribas Mutual Fund"),
        ("PGIM","PGIM India Mutual Fund"),("Mahindra Manulife","Mahindra Manulife Mutual Fund"),
        ("JM ","JM Financial Mutual Fund"),("Navi","Navi Mutual Fund"),
        ("Groww","Groww Mutual Fund"),("360 ONE","360 ONE Mutual Fund"),
        ("Quantum","Quantum Mutual Fund"),("LIC","LIC Mutual Fund"),
        ("Union","Union Mutual Fund"),("ITI","ITI Mutual Fund"),
        ("Bank of India","Bank of India Mutual Fund"),("Bajaj Finserv","Bajaj Finserv Mutual Fund"),
        ("Shriram","Shriram Mutual Fund"),("Samco","Samco Mutual Fund"),
        ("Trust","Trust Mutual Fund"),("Helios","Helios Mutual Fund"),
    ]
    for pattern, amc in patterns:
        if pattern.lower() in name.lower():
            return amc
    return "Unknown"


def strip_plan_suffix(name):
    """Clean fund name for display."""
    suffixes = [" - Direct Plan - Growth"," - Direct Plan-Growth"," - Direct - Growth",
                " Direct Plan Growth"," Direct Plan"," - Direct Plan"," - Growth"," Direct-Growth"]
    for s in suffixes:
        if name.endswith(s):
            name = name[:-len(s)].strip()
    return name


# ─── Supabase helpers ─────────────────────────────────────────
def supabase_upsert(table, rows, sb_url, sb_key):
    if not rows: return 0
    CHUNK = 200
    inserted = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i+CHUNK]
        url = f"{sb_url}/rest/v1/{table}"
        headers = {
            "apikey": sb_key, "Authorization": f"Bearer {sb_key}",
            "Content-Type": "application/json", "Accept": "application/json",
            "Prefer": "return=minimal,resolution=merge-duplicates",
        }
        data = json.dumps(chunk).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=30)
        inserted += len(chunk)
    return inserted


# ─── Snapshot writer ──────────────────────────────────────────
def write_snapshot(all_funds, output_path="snapshot.py"):
    month = datetime.now().strftime("%b %Y")
    lines = ['"""',f'snapshot.py — {len(all_funds)} funds scraped from Groww.in',
             f'Generated: {datetime.now().strftime("%Y-%m-%d")}','"""','',
             f'SNAPSHOT_DATE = "{month}"','','SNAPSHOT_SCHEMES = {']
    for i, f in enumerate(all_funds):
        fid = -(i+1)
        n = f["name"].replace('"','\\"')
        a = f["amc"].replace('"','\\"')
        c = f.get("category","Equity").replace('"','\\"')
        lines.append(f"    {fid}: {{")
        lines.append(f'        "family_id": {fid}, "name": "{n}",')
        lines.append(f'        "category": "{c}", "amc": "{a}",')
        lines.append(f'        "month": SNAPSHOT_DATE,')
        lines.append(f'        "holdings": {{')
        for h in f["holdings"]:
            s = h["stock_name"].replace('"','\\"')
            lines.append(f'            "{s}": {h["weight_pct"]},')
        lines.append('        },')
        lines.append('    },')
    lines.append('}'); lines.append('')
    with open(output_path, "w", encoding="utf-8") as fout:
        fout.write("\n".join(lines))
    print(f"\n✅ Wrote {output_path} — {len(all_funds)} funds, {os.path.getsize(output_path)//1024}KB")


# ─── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="snapshot.py")
    parser.add_argument("--max-funds", type=int, default=300, help="Max funds to scrape")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL",""))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY",""))
    args = parser.parse_args()

    sb_url = args.supabase_url.rstrip("/")
    if sb_url.endswith("/rest/v1"): sb_url = sb_url[:-8]
    sb_key = args.supabase_key

    print("="*60)
    print("  MF Overlap — Groww.in Scraper")
    print("="*60)

    # 1. Get scheme list from AMFI
    amfi_schemes = fetch_amfi_schemes()
    if not amfi_schemes:
        print("ERROR: Could not fetch AMFI scheme list")
        sys.exit(1)

    # Limit
    amfi_schemes = amfi_schemes[:args.max_funds]

    # 2. For each scheme, try to fetch from Groww
    all_funds = []
    tried = 0
    for i, scheme in enumerate(amfi_schemes):
        slug = name_to_groww_slug(scheme["raw_name"])
        clean_name = strip_plan_suffix(scheme["raw_name"])
        print(f"  [{i+1}/{len(amfi_schemes)}] {clean_name} → {slug}...", end=" ", flush=True)

        fund_name, category, holdings = fetch_groww_holdings(slug)
        tried += 1

        if holdings:
            display_name = fund_name if fund_name else clean_name
            # Clean the display name
            display_name = strip_plan_suffix(display_name)
            amc = detect_amc(display_name) if detect_amc(display_name) != "Unknown" else scheme.get("amc","Unknown")

            all_funds.append({
                "name": display_name,
                "amc": amc,
                "category": category or "Equity",
                "amfi_code": scheme["amfi_code"],
                "holdings": holdings,
            })
            print(f"✓ {len(holdings)} stocks")
        else:
            print("✗")

        # Progress
        if tried % 50 == 0:
            print(f"\n  --- Progress: {tried} tried, {len(all_funds)} found ---\n")

    print(f"\n{'='*60}")
    print(f"Scrape complete: {len(all_funds)} funds with holdings out of {tried} tried")

    if not all_funds:
        print("ERROR: No funds found. Groww might be blocking or slug patterns changed.")
        sys.exit(1)

    if args.dry_run:
        for f in all_funds[:5]:
            print(f"  {f['name']} ({f['amc']}) — {len(f['holdings'])} stocks")
        return

    # 3. Write snapshot
    write_snapshot(all_funds, args.output)

    # 4. Seed Supabase
    if not args.snapshot_only and sb_url and sb_key:
        print(f"\nSeeding Supabase ({len(all_funds)} funds)...")
        month = datetime.now().strftime("%Y-%m")
        scheme_rows = []; holdings_rows = []
        for i, f in enumerate(all_funds):
            fid = -(i+1)
            scheme_rows.append({"family_id":fid,"name":f["name"],"amc":f["amc"],
                                "category":f["category"],"amfi_code":f.get("amfi_code")})
            for h in f["holdings"]:
                holdings_rows.append({"family_id":fid,"stock_name":h["stock_name"],
                                      "weight_pct":h["weight_pct"],"sector":None,"as_of_month":month})
        try:
            s = supabase_upsert("schemes", scheme_rows, sb_url, sb_key)
            h = supabase_upsert("holdings", holdings_rows, sb_url, sb_key)
            print(f"  ✅ Seeded: {s} schemes, {h} holdings")
        except Exception as e:
            print(f"  ⚠️ Supabase failed: {e}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
