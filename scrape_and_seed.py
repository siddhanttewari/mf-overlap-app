#!/usr/bin/env python3
"""
MF Overlap — Moneycontrol Scraper + Supabase Seeder
=====================================================
Scrapes equity mutual fund holdings from Moneycontrol.com
and pushes them to Supabase. No dependency on MFData.in.

Sources:
  - Moneycontrol.com category listings → fund list
  - Moneycontrol.com portfolio pages → stock holdings

Usage:
  # Set env vars (or pass as args)
  export SUPABASE_URL="https://xxx.supabase.co"
  export SUPABASE_KEY="eyJ..."

  python scrape_and_seed.py                    # scrape + seed Supabase
  python scrape_and_seed.py --snapshot-only     # just update snapshot.py (no Supabase)
  python scrape_and_seed.py --dry-run           # scrape only, don't write anywhere

Schedule via GitHub Actions (10th of each month).
Requires: pip install requests beautifulsoup4 lxml
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from bs4 import BeautifulSoup
import requests

# ─── Config ───────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

DELAY = 2.5  # seconds between requests
MAX_RETRIES = 3

# Moneycontrol category URLs → lists funds in each category
MC_CATEGORIES = {
    "Large Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/large-cap",
    "Mid Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/mid-cap",
    "Small Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/small-cap",
    "Multi Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/multi-cap",
    "Large & Mid Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/large-and-mid-cap",
    "Flexi Cap": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/flexi-cap",
    "ELSS": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/elss",
    "Value Fund": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/value",
    "Contra Fund": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/contra",
    "Focused Fund": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/focused",
    "Dividend Yield": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/dividend-yield",
    "Sectoral/Thematic": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/sectoral-thematic",
    "Index Funds": "https://www.moneycontrol.com/mutual-funds/best-funds/equity/index-funds",
    "Aggressive Hybrid": "https://www.moneycontrol.com/mutual-funds/best-funds/hybrid/aggressive-hybrid",
    "Balanced Advantage": "https://www.moneycontrol.com/mutual-funds/best-funds/hybrid/balanced-advantage",
    "Equity Savings": "https://www.moneycontrol.com/mutual-funds/best-funds/hybrid/equity-savings",
}

# Alternative: Value Research category pages (backup)
VR_CATEGORIES = {
    "Large Cap": "https://www.valueresearchonline.com/funds/selector/category/1/equity-large-cap/",
    "Mid Cap": "https://www.valueresearchonline.com/funds/selector/category/2/equity-mid-cap/",
    "Small Cap": "https://www.valueresearchonline.com/funds/selector/category/3/equity-small-cap/",
    "Flexi Cap": "https://www.valueresearchonline.com/funds/selector/category/36/equity-flexi-cap/",
    "Large & Mid Cap": "https://www.valueresearchonline.com/funds/selector/category/4/equity-large-and-mid-cap/",
    "Multi Cap": "https://www.valueresearchonline.com/funds/selector/category/79/equity-multi-cap/",
    "ELSS": "https://www.valueresearchonline.com/funds/selector/category/7/equity-elss/",
    "Value Fund": "https://www.valueresearchonline.com/funds/selector/category/5/equity-value/",
    "Focused Fund": "https://www.valueresearchonline.com/funds/selector/category/6/equity-focused/",
}


# ─── HTTP helpers ─────────────────────────────────────────────────────

session = requests.Session()
session.headers.update(HEADERS)


def fetch_page(url, retries=MAX_RETRIES):
    """GET a page with retries and rate limiting."""
    for attempt in range(retries):
        try:
            time.sleep(DELAY)
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.text
            print(f"  HTTP {resp.status_code} for {url}")
        except Exception as e:
            print(f"  Attempt {attempt+1}/{retries} failed: {e}")
            time.sleep(2 ** attempt)
    return None


# ─── Moneycontrol scraper ─────────────────────────────────────────────

def scrape_mc_fund_list(category, url):
    """Scrape Moneycontrol category page to get list of fund names + portfolio URLs."""
    print(f"\n[{category}] Fetching fund list from {url}")
    html = fetch_page(url)
    if not html:
        print(f"  Failed to fetch {category} listing")
        return []

    soup = BeautifulSoup(html, "lxml")
    funds = []

    # MC lists funds as links — look for fund name links
    # Pattern: /mutual-funds/nav/{slug}/portfolio-holdings or just fund detail links
    for link in soup.find_all("a", href=True):
        href = link["href"]
        name = link.get_text(strip=True)

        # Match fund detail/NAV pages
        if "/mutual-funds/nav/" in href and name and len(name) > 5:
            # Skip non-direct plans
            name_lower = name.lower()
            if "regular" in name_lower and "direct" not in name_lower:
                continue

            # Extract the slug
            slug_match = re.search(r"/mutual-funds/nav/([^/]+)", href)
            if slug_match:
                slug = slug_match.group(1)
                # Build portfolio URL
                portfolio_url = f"https://www.moneycontrol.com/mutual-funds/nav/{slug}/portfolio-holdings"

                # Clean fund name
                clean_name = name.strip()
                for suffix in [" - Direct Plan - Growth", " - Direct Plan", " Direct Plan Growth",
                               " Direct Plan", " - Growth", " Growth", " Direct"]:
                    if clean_name.endswith(suffix):
                        clean_name = clean_name[:-len(suffix)].strip()

                # Detect AMC from name
                amc = detect_amc(clean_name)

                funds.append({
                    "name": clean_name,
                    "category": category,
                    "amc": amc,
                    "mc_slug": slug,
                    "portfolio_url": portfolio_url,
                })

    # Deduplicate by name
    seen = set()
    unique = []
    for f in funds:
        key = f["name"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)

    print(f"  Found {len(unique)} funds in {category}")
    return unique


def scrape_mc_holdings(fund):
    """Scrape portfolio holdings from a Moneycontrol fund page."""
    url = fund["portfolio_url"]
    html = fetch_page(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    holdings = []

    # Try multiple table patterns MC uses
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # First cell usually has the stock name
            stock_cell = cells[0]
            link = stock_cell.find("a")
            stock_name = link.get_text(strip=True) if link else stock_cell.get_text(strip=True)
            if not stock_name or len(stock_name) < 2:
                continue
            # Skip header rows
            if stock_name.lower() in ("company", "stock name", "name", "holding", "equity"):
                continue

            # Find weight percentage in remaining cells
            weight = None
            for cell in cells[1:]:
                text = cell.get_text(strip=True).replace("%", "").replace(",", "").strip()
                try:
                    val = float(text)
                    if 0.05 < val < 100:
                        weight = val
                        break
                except (ValueError, TypeError):
                    continue

            if weight and weight > 0.1:
                holdings.append({
                    "stock_name": stock_name.strip(),
                    "weight_pct": round(weight, 2),
                })

    # Also try JSON embedded in page scripts
    if not holdings:
        holdings = parse_embedded_json(soup)

    if holdings:
        # Sort by weight, take top 25
        holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
        holdings = holdings[:25]

    return holdings


def parse_embedded_json(soup):
    """Try to find holdings data in page scripts."""
    holdings = []
    for script in soup.find_all("script"):
        text = script.string or ""
        if "portfolio" in text.lower() or "holding" in text.lower():
            # Look for JSON-like data
            for match in re.findall(r'\{[^{}]*"stock_name"[^{}]*\}', text):
                try:
                    item = json.loads(match)
                    name = item.get("stock_name") or item.get("name", "")
                    weight = item.get("weight_pct") or item.get("percentage", 0)
                    if name and weight:
                        holdings.append({"stock_name": str(name), "weight_pct": float(weight)})
                except (json.JSONDecodeError, ValueError):
                    continue
    return holdings


def detect_amc(fund_name):
    """Detect AMC from fund name."""
    amc_patterns = {
        "HDFC": "HDFC Mutual Fund",
        "ICICI Prudential": "ICICI Prudential Mutual Fund",
        "ICICI Pru": "ICICI Prudential Mutual Fund",
        "SBI": "SBI Mutual Fund",
        "Axis": "Axis Mutual Fund",
        "Kotak": "Kotak Mahindra Mutual Fund",
        "Nippon India": "Nippon India Mutual Fund",
        "Nippon": "Nippon India Mutual Fund",
        "Mirae Asset": "Mirae Asset Mutual Fund",
        "Aditya Birla": "Aditya Birla Sun Life Mutual Fund",
        "ABSL": "Aditya Birla Sun Life Mutual Fund",
        "DSP": "DSP Mutual Fund",
        "Tata": "Tata Mutual Fund",
        "UTI": "UTI Mutual Fund",
        "Canara Robeco": "Canara Robeco Mutual Fund",
        "Franklin": "Franklin Templeton Mutual Fund",
        "Motilal Oswal": "Motilal Oswal Mutual Fund",
        "Sundaram": "Sundaram Mutual Fund",
        "HSBC": "HSBC Mutual Fund",
        "Invesco": "Invesco Mutual Fund",
        "Quant": "Quant Mutual Fund",
        "Parag Parikh": "PPFAS Mutual Fund",
        "PPFAS": "PPFAS Mutual Fund",
        "White Oak": "White Oak Capital Mutual Fund",
        "Bandhan": "Bandhan Mutual Fund",
        "Edelweiss": "Edelweiss Mutual Fund",
        "Baroda BNP": "Baroda BNP Paribas Mutual Fund",
        "PGIM": "PGIM India Mutual Fund",
        "Mahindra Manulife": "Mahindra Manulife Mutual Fund",
        "JM ": "JM Financial Mutual Fund",
        "Navi": "Navi Mutual Fund",
        "Groww": "Groww Mutual Fund",
        "360 ONE": "360 ONE Mutual Fund",
        "IIFL": "360 ONE Mutual Fund",
        "Quantum": "Quantum Mutual Fund",
        "Bank of India": "Bank of India Mutual Fund",
        "LIC": "LIC Mutual Fund",
        "Union": "Union Mutual Fund",
        "ITI": "ITI Mutual Fund",
        "Samco": "Samco Mutual Fund",
        "Trust": "Trust Mutual Fund",
        "Shriram": "Shriram Mutual Fund",
        "Bajaj Finserv": "Bajaj Finserv Mutual Fund",
        "Zerodha": "Zerodha Mutual Fund",
    }
    for pattern, amc in amc_patterns.items():
        if pattern.lower() in fund_name.lower():
            return amc
    return "Unknown"


# ─── Supabase helpers ─────────────────────────────────────────────────

def supabase_request(method, table, params=None, body=None,
                     supabase_url=None, supabase_key=None):
    """Direct REST call to Supabase PostgREST."""
    url = f"{supabase_url}/rest/v1/{table}"
    if params:
        url += "?" + urllib.parse.urlencode(params, safe=".*,()<>=:")

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal,resolution=merge-duplicates"
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8") if e.fp else ""
        print(f"  Supabase error {e.code}: {body_text[:200]}")
        raise


def supabase_upsert(table, rows, supabase_url=None, supabase_key=None):
    """Batch upsert rows into Supabase."""
    if not rows:
        return 0
    CHUNK = 200
    inserted = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        supabase_request("POST", table, body=chunk,
                         supabase_url=supabase_url, supabase_key=supabase_key)
        inserted += len(chunk)
    return inserted


# ─── Snapshot writer ──────────────────────────────────────────────────

def write_snapshot(all_funds, output_path="snapshot.py"):
    """Write snapshot.py from scraped data."""
    month = datetime.now().strftime("%b %Y")
    lines = []
    lines.append('"""')
    lines.append('snapshot.py — Last-known-good fallback dataset')
    lines.append('================================================')
    lines.append(f'Auto-scraped from Moneycontrol.com on {datetime.now().strftime("%Y-%m-%d")}')
    lines.append(f'Total funds: {len(all_funds)}')
    lines.append('"""')
    lines.append('')
    lines.append(f'SNAPSHOT_DATE = "{month}"')
    lines.append('')
    lines.append('SNAPSHOT_SCHEMES = {')

    for i, fund in enumerate(all_funds):
        fid = -(i + 1)
        name = fund["name"].replace('"', '\\"')
        amc = fund["amc"].replace('"', '\\"')
        cat = fund["category"].replace('"', '\\"')
        lines.append(f"    {fid}: {{")
        lines.append(f'        "family_id": {fid}, "name": "{name}",')
        lines.append(f'        "category": "{cat}", "amc": "{amc}",')
        lines.append(f'        "month": SNAPSHOT_DATE,')
        lines.append(f'        "holdings": {{')
        for h in fund["holdings"]:
            sname = h["stock_name"].replace('"', '\\"')
            lines.append(f'            "{sname}": {h["weight_pct"]},')
        lines.append(f'        }},')
        lines.append(f"    }},")

    lines.append("}")
    lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n✅ Wrote {output_path} — {len(all_funds)} funds, {os.path.getsize(output_path)//1024}KB")


# ─── Main pipeline ────────────────────────────────────────────────────

def run_scrape():
    """Scrape all categories from Moneycontrol."""
    all_funds = []
    errors = []

    for category, url in MC_CATEGORIES.items():
        fund_list = scrape_mc_fund_list(category, url)

        for fund in fund_list:
            print(f"  → {fund['name']}...", end=" ", flush=True)
            holdings = scrape_mc_holdings(fund)

            if holdings:
                fund["holdings"] = holdings
                all_funds.append(fund)
                print(f"✓ {len(holdings)} stocks")
            else:
                print("✗ no holdings")
                errors.append(fund["name"])

    print(f"\n{'='*60}")
    print(f"Scrape complete: {len(all_funds)} funds OK, {len(errors)} failed")
    if errors:
        print(f"Failed: {', '.join(errors[:10])}{'...' if len(errors)>10 else ''}")

    return all_funds


def seed_supabase(all_funds, supabase_url, supabase_key):
    """Push scraped funds to Supabase."""
    print(f"\nSeeding Supabase ({len(all_funds)} funds)...")

    month = datetime.now().strftime("%Y-%m")

    # Prepare scheme rows (negative IDs for snapshot entries)
    scheme_rows = []
    holdings_rows = []
    for i, fund in enumerate(all_funds):
        fid = -(i + 1)
        scheme_rows.append({
            "family_id": fid,
            "name": fund["name"],
            "amc": fund["amc"],
            "category": fund["category"],
            "amfi_code": None,
        })
        for h in fund["holdings"]:
            holdings_rows.append({
                "family_id": fid,
                "stock_name": h["stock_name"],
                "weight_pct": h["weight_pct"],
                "sector": None,
                "as_of_month": month,
            })

    s_count = supabase_upsert("schemes", scheme_rows,
                              supabase_url=supabase_url, supabase_key=supabase_key)
    print(f"  Schemes upserted: {s_count}")

    h_count = supabase_upsert("holdings", holdings_rows,
                              supabase_url=supabase_url, supabase_key=supabase_key)
    print(f"  Holdings upserted: {h_count}")

    return s_count, h_count


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape MF holdings from Moneycontrol → Supabase")
    parser.add_argument("--snapshot-only", action="store_true",
                        help="Only write snapshot.py, don't seed Supabase")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape only, don't write anything")
    parser.add_argument("--output", default="snapshot.py",
                        help="Snapshot output path")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", ""),
                        help="Supabase project URL")
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY", ""),
                        help="Supabase anon/service key")
    args = parser.parse_args()

    # Normalize Supabase URL
    sb_url = args.supabase_url.rstrip("/")
    if sb_url.endswith("/rest/v1"):
        sb_url = sb_url[:-len("/rest/v1")]
    sb_key = args.supabase_key

    print("=" * 60)
    print("  MF Overlap — Moneycontrol Scraper")
    print("=" * 60)
    print(f"  Source: Moneycontrol.com")
    print(f"  Categories: {len(MC_CATEGORIES)}")
    print(f"  Supabase: {'configured' if sb_url and sb_key else 'not configured'}")
    print("=" * 60)

    # 1. Scrape
    all_funds = run_scrape()
    if not all_funds:
        print("ERROR: No funds scraped. Check if Moneycontrol is accessible.")
        sys.exit(1)

    if args.dry_run:
        print(f"\nDry run — {len(all_funds)} funds scraped, nothing written.")
        return

    # 2. Write snapshot.py (always — serves as fallback)
    write_snapshot(all_funds, args.output)

    # 3. Seed Supabase (if configured and not snapshot-only)
    if not args.snapshot_only and sb_url and sb_key:
        try:
            seed_supabase(all_funds, sb_url, sb_key)
            print("✅ Supabase seeded successfully!")
        except Exception as e:
            print(f"⚠️ Supabase seeding failed: {e}")
            print("   Snapshot.py was still written — app will use that as fallback.")
    elif not args.snapshot_only:
        print("\nℹ️ Supabase not configured — skipping. Set SUPABASE_URL + SUPABASE_KEY env vars.")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
