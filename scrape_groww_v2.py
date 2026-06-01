#!/usr/bin/env python3
"""
MF Overlap — Groww.in Scraper v2 (Auto-discover URLs)
======================================================
1. Gets fund list from MFapi.in (free, reliable, no auth)
2. Auto-discovers correct Groww URLs by trying multiple slug patterns
3. Caches discovered URLs in groww_urls.json (reused on future runs)
4. Parses holdings from Groww HTML pages
5. Updates snapshot.py + Supabase

The first run is slow (discovering URLs). Subsequent runs are fast (cached URLs).

Usage:
  python scrape_groww_v2.py                     # full run
  python scrape_groww_v2.py --discover-only      # just build URL mapping
  python scrape_groww_v2.py --snapshot-only       # skip Supabase
  python scrape_groww_v2.py --max-funds 50        # limit for testing
"""

import argparse, json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.5",
}
DELAY = 1.5
MFAPI_BASE = "https://api.mfapi.in/mf"
GROWW_BASE = "https://groww.in/mutual-funds"
URL_CACHE_FILE = "groww_urls.json"

session = requests.Session()
session.headers.update(HEADERS)

# ─── Step 1: Get fund list from MFapi.in ────────────────────────────

def fetch_mfapi_schemes():
    """Get all mutual fund schemes from MFapi.in (free API)."""
    print("Fetching scheme list from MFapi.in...")
    try:
        resp = session.get(f"{MFAPI_BASE}", timeout=30)
        if resp.status_code != 200:
            print(f"  MFapi.in returned HTTP {resp.status_code}")
            return []
        data = resp.json()
        # Filter: Direct Plan + Growth only, skip debt/liquid/etc
        skip = ["liquid", "overnight", "gilt", "money market", "debt",
                "credit risk", "banking and psu", "floater", "corporate bond",
                "low duration", "medium duration", "short duration", "long duration",
                "ultra short", "dynamic bond", "target maturity", "fixed maturity",
                "gold", "silver", "commodit", "etf", "fund of fund", "fof",
                "retirement", "children", "interval", "capital protection",
                "arbitrage", "nifty 1d rate"]
        schemes = []
        for s in data:
            name = s.get("schemeName", "")
            code = s.get("schemeCode")
            if not name or not code:
                continue
            nl = name.lower()
            if "direct" not in nl:
                continue
            if "growth" not in nl:
                continue
            if any(kw in nl for kw in skip):
                continue
            schemes.append({"code": str(code), "name": name})
        print(f"  Found {len(schemes)} Direct Growth equity schemes")
        return schemes
    except Exception as e:
        print(f"  MFapi.in error: {e}")
        return []


# ─── Step 2: Auto-discover Groww URLs ───────────────────────────────

def load_url_cache():
    """Load previously discovered Groww URLs."""
    if os.path.exists(URL_CACHE_FILE):
        with open(URL_CACHE_FILE) as f:
            return json.load(f)
    return {}

def save_url_cache(cache):
    """Save discovered URLs for future runs."""
    with open(URL_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def clean_fund_name(name):
    """Strip plan/option suffixes for slug generation. Case-insensitive."""
    name = re.sub(r'\s+', ' ', name.strip())
    suffixes = [
        " - Direct Plan - Growth Option", " - Direct Plan-Growth Option",
        " - Direct Plan - Growth", " - Direct Plan-Growth",
        " - Direct - Growth Option", " - Direct - Growth",
        " -Direct Plan-Growth", " - Direct Plan",
        " Direct Plan Growth Option", " Direct Plan - Growth Option",
        " Direct Plan Growth", " Direct Plan - Growth",
        " Direct-Growth", " Direct Growth",
        " - Growth Option", " -Growth Option",
        " - Growth", " -Growth", " Growth Option",
        " Fund - Direct", " - Direct", " Direct",
        # Hyphenated formats (no spaces)
        "-Direct Plan-Growth", "-Direct-Plan-Growth",
        "-Direct Plan Growth", "-Direct-Growth",
    ]
    nl = name.lower()
    for suffix in suffixes:
        if nl.endswith(suffix.lower()):
            name = name[:len(name)-len(suffix)].strip()
            break
    # Also try regex for remaining weird formats
    name = re.sub(r'[\s-]*(Direct|Growth|Option|Plan)[\s-]*(Direct|Growth|Option|Plan)?[\s-]*(Direct|Growth|Option|Plan)?$', '', name, flags=re.IGNORECASE).strip()
    if name.lower().endswith(" fund"):
        name = name[:-5].strip()
    # Clean trailing hyphens/dashes
    name = name.strip(' -–—')
    return name

def generate_slug_variants(name):
    """Generate many possible Groww URL slugs for a fund name."""
    clean = clean_fund_name(name)
    def slugify(s):
        s = s.lower().replace("&", "and").replace("'", "").replace("\u2019", "")
        s = re.sub(r'[^a-z0-9\s-]', '', s)
        s = re.sub(r'\s+', '-', s.strip())
        return re.sub(r'-+', '-', s)
    base = slugify(clean)
    base_nf = re.sub(r'-?fund-?', '-', base).strip('-')
    base_nf = re.sub(r'-+', '-', base_nf)
    variants = [
        f"{base}-direct-growth",
        f"{base}-fund-direct-growth",
        f"{base_nf}-fund-direct-growth",
        f"{base_nf}-direct-growth",
        f"{base}-direct-plan-growth",
        f"{base}-fund-direct-plan-growth",
        f"{base_nf}-fund-direct-plan-growth",
        f"{base_nf}-direct-plan-growth",
    ]
    for word in ["mutual", "scheme", "plan", "option", "regular"]:
        if f"-{word}" in base_nf:
            alt = re.sub(rf'-?{word}-?', '-', base_nf).strip('-')
            alt = re.sub(r'-+', '-', alt)
            if alt:
                variants.append(f"{alt}-fund-direct-growth")
                variants.append(f"{alt}-direct-growth")
    seen = set()
    unique = []
    for v in variants:
        v = re.sub(r'-+', '-', v).strip('-')
        if v and v not in seen:
            seen.add(v)
            unique.append(v)
    return unique

def discover_groww_url(fund_name):
    """Try multiple slug patterns to find the correct Groww URL."""
    slugs = generate_slug_variants(fund_name)
    
    for slug in slugs:
        url = f"{GROWW_BASE}/{slug}"
        try:
            time.sleep(0.5)  # Quick check — just HEAD request
            resp = session.head(url, timeout=8, allow_redirects=True)
            if resp.status_code == 200:
                # Verify it's actually a fund page (not a generic page)
                final_url = resp.url if resp.url else url
                if "/mutual-funds/" in final_url:
                    return slug
        except Exception:
            continue
    
    return None


# ─── Step 3: Parse holdings from Groww page ─────────────────────────

def fetch_holdings(slug):
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
    
    # Fund name from page
    title = soup.find("h1")
    fund_name = title.get_text(strip=True) if title else ""
    
    # Category detection
    category = ""
    cat_keywords = {"Large Cap", "Mid Cap", "Small Cap", "Flexi Cap", "Multi Cap",
                    "Large & MidCap", "Large & Mid Cap", "ELSS", "Value", "Contra",
                    "Focused", "Dividend Yield", "Sectoral", "Thematic", "Index",
                    "Aggressive Hybrid", "Balanced Advantage", "Equity Savings"}
    for el in soup.find_all(["a", "span", "div"]):
        text = el.get_text(strip=True)
        for kw in cat_keywords:
            if kw.lower() in text.lower() and len(text) < 50:
                category = kw
                break
        if category:
            break

    # Parse holdings table
    holdings = []
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link = cells[0].find("a")
            stock = link.get_text(strip=True) if link else cells[0].get_text(strip=True)
            if not stock or len(stock) < 2 or stock.lower() in ("company", "stock", "name"):
                continue
            # Find weight in last cells
            for cell in reversed(cells[1:]):
                text = cell.get_text(strip=True).replace("%", "").strip()
                try:
                    w = float(text)
                    if 0.05 < w < 100:
                        holdings.append({"stock_name": stock, "weight_pct": round(w, 2)})
                        break
                except (ValueError, TypeError):
                    continue

    if holdings:
        holdings.sort(key=lambda x: x["weight_pct"], reverse=True)
        holdings = holdings[:25]

    return fund_name, category, holdings


# ─── AMC detection ──────────────────────────────────────────────────

def detect_amc(name):
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


# ─── Snapshot writer ────────────────────────────────────────────────

def write_snapshot(all_funds, output_path="snapshot.py"):
    month = datetime.now().strftime("%b %Y")
    lines = ['"""',
        f'snapshot.py — {len(all_funds)} funds scraped from Groww.in',
        f'Generated: {datetime.now().strftime("%Y-%m-%d")}',
        '"""', '',
        f'SNAPSHOT_DATE = "{month}"', '', 'SNAPSHOT_SCHEMES = {']
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
    with open(output_path,"w") as fout:
        fout.write("\n".join(lines))
    print(f"\n✅ Wrote {output_path} — {len(all_funds)} funds, {os.path.getsize(output_path)//1024}KB")


# ─── Supabase ───────────────────────────────────────────────────────

def supabase_delete(table, filter_param, sb_url, sb_key):
    """DELETE rows matching a filter."""
    url = f"{sb_url}/rest/v1/{table}?{filter_param}"
    headers = {"apikey":sb_key,"Authorization":f"Bearer {sb_key}",
                "Content-Type":"application/json"}
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"    Delete from {table} warning: {e}")

def supabase_insert(table, rows, sb_url, sb_key):
    """Simple INSERT (no conflict resolution)."""
    if not rows: return 0
    CHUNK = 100; inserted = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i+CHUNK]
        url = f"{sb_url}/rest/v1/{table}"
        headers = {"apikey":sb_key,"Authorization":f"Bearer {sb_key}",
                    "Content-Type":"application/json","Accept":"application/json",
                    "Prefer":"return=minimal"}
        data = json.dumps(chunk).encode()
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            urllib.request.urlopen(req, timeout=30)
            inserted += len(chunk)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300] if e.fp else ""
            print(f"    Insert error ({e.code}): {body}")
            raise
    return inserted


# ─── Main pipeline ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--discover-only", action="store_true", help="Just build URL mapping, don't scrape")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="snapshot.py")
    parser.add_argument("--max-funds", type=int, default=300)
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL",""))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_KEY",""))
    args = parser.parse_args()

    sb_url = args.supabase_url.rstrip("/")
    if sb_url.endswith("/rest/v1"): sb_url = sb_url[:-8]
    sb_key = args.supabase_key

    print("="*60)
    print("  MF Overlap — Groww.in Scraper v2 (Auto-discover)")
    print("="*60)

    # 1. Get scheme list from MFapi.in
    schemes = fetch_mfapi_schemes()
    if not schemes:
        print("ERROR: Could not get schemes from MFapi.in")
        sys.exit(1)
    schemes = schemes[:args.max_funds]

    # 2. Load cached Groww URLs
    url_cache = load_url_cache()
    print(f"URL cache: {len(url_cache)} previously discovered slugs")

    # 3. Discover + fetch holdings
    all_funds = []
    new_discoveries = 0
    
    for i, scheme in enumerate(schemes):
        raw_name = scheme["name"]
        clean_name = clean_fund_name(raw_name)
        cache_key = scheme["code"]

        # Check URL cache first
        cached_slug = url_cache.get(cache_key)
        
        if cached_slug:
            slug = cached_slug
            print(f"  [{i+1}/{len(schemes)}] {clean_name} → cached slug", end=" ", flush=True)
        else:
            # Discover the correct Groww URL
            print(f"  [{i+1}/{len(schemes)}] {clean_name} → discovering...", end=" ", flush=True)
            slug = discover_groww_url(raw_name)
            if slug:
                url_cache[cache_key] = slug
                new_discoveries += 1
                print(f"found! ({slug})", end=" ", flush=True)
            else:
                print("✗ no Groww page found")
                continue

        if args.discover_only:
            print(f"→ {slug}")
            continue

        # Fetch holdings
        fund_name, category, holdings = fetch_holdings(slug)
        if holdings:
            display_name = clean_fund_name(fund_name) if fund_name else clean_name
            amc = detect_amc(display_name)
            all_funds.append({
                "name": display_name,
                "amc": amc,
                "category": category or "Equity",
                "amfi_code": scheme["code"],
                "holdings": holdings,
            })
            print(f"✓ {len(holdings)} stocks")
        else:
            print("✗ no holdings parsed")

        # Save URL cache periodically
        if new_discoveries > 0 and i % 20 == 0:
            save_url_cache(url_cache)

        # Progress
        if (i+1) % 50 == 0:
            print(f"\n  --- Progress: {i+1}/{len(schemes)} tried, {len(all_funds)} with holdings, {new_discoveries} new URLs discovered ---\n")

    # Save final URL cache
    if new_discoveries > 0:
        save_url_cache(url_cache)
        print(f"\n📁 Saved {len(url_cache)} URLs to {URL_CACHE_FILE} ({new_discoveries} newly discovered)")

    if args.discover_only:
        print(f"\nDiscovery complete: {len(url_cache)} total URLs mapped")
        return

    print(f"\n{'='*60}")
    print(f"Scrape complete: {len(all_funds)} funds with holdings")

    if args.dry_run:
        for f in all_funds[:10]:
            print(f"  {f['name']} ({f['amc']}) — {len(f['holdings'])} stocks")
        return

    if not all_funds:
        print("ERROR: No funds scraped. Keeping existing snapshot.")
        sys.exit(0)

    # ── MERGE with existing snapshot (never lose curated funds) ──
    existing_funds = {}
    if os.path.exists(args.output):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("ex", args.output)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            for fid, s in getattr(mod, 'SNAPSHOT_SCHEMES', {}).items():
                existing_funds[s["name"].lower().strip()] = {
                    "name": s["name"], "amc": s.get("amc",""),
                    "category": s.get("category",""), "holdings": [
                        {"stock_name": k, "weight_pct": v} for k, v in s.get("holdings", {}).items()
                    ],
                }
            print(f"\nExisting snapshot: {len(existing_funds)} funds")
        except Exception as e:
            print(f"\nCould not load existing snapshot: {e}")

    # Match scraped funds to existing ones and update holdings
    updated = 0
    added = 0
    for fund in all_funds:
        key = fund["name"].lower().strip()
        # Try exact match first, then fuzzy
        matched_key = None
        if key in existing_funds:
            matched_key = key
        else:
            # Try partial matching (first 3 words)
            fund_words = key.split()[:3]
            for ek in existing_funds:
                ek_words = ek.split()[:3]
                if fund_words == ek_words:
                    matched_key = ek
                    break
        
        if matched_key:
            # Update existing fund with fresh Groww holdings
            existing_funds[matched_key]["holdings"] = fund["holdings"]
            if fund.get("category") and fund["category"] != "Equity":
                existing_funds[matched_key]["category"] = fund["category"]
            updated += 1
        else:
            # New fund from Groww — add it
            existing_funds[key] = fund
            added += 1

    merged = list(existing_funds.values())
    print(f"Merge result: {len(merged)} total ({updated} updated with fresh Groww data, {added} new funds added, {len(merged) - updated - added} unchanged)")

    # Write merged snapshot
    write_snapshot(merged, args.output)

    # Seed Supabase with merged data
    if not args.snapshot_only and sb_url and sb_key:
        print(f"\nSeeding Supabase ({len(merged)} funds)...")
        month = datetime.now().strftime("%Y-%m")
        scheme_rows = []; holdings_rows = []
        for i, f in enumerate(merged):
            fid = -(i+1)
            scheme_rows.append({"family_id":fid,"name":f["name"],"amc":f.get("amc",""),
                                "category":f.get("category",""),"amfi_code":f.get("amfi_code")})
            for h in f["holdings"]:
                holdings_rows.append({"family_id":fid,"stock_name":h["stock_name"],
                                      "weight_pct":h["weight_pct"],"sector":None,"as_of_month":month})
        try:
            # Delete old snapshot data (negative family_ids), then insert fresh
            print("  Clearing old snapshot data...")
            supabase_delete("holdings", "family_id=lt.0", sb_url, sb_key)
            supabase_delete("schemes", "family_id=lt.0", sb_url, sb_key)
            print("  Inserting fresh data...")
            s = supabase_insert("schemes", scheme_rows, sb_url, sb_key)
            h = supabase_insert("holdings", holdings_rows, sb_url, sb_key)
            print(f"  ✅ Seeded: {s} schemes, {h} holdings")
        except Exception as e:
            print(f"  ⚠️ Supabase failed: {e}")

    print("\n✅ Done!")


if __name__ == "__main__":
    main()
