"""
collect.py — Data Collection Layer
===================================
Mutual Fund Analysis Dashboard
--------------------------------
Stage 1 of the pipeline. Its only job is to fetch raw data
from external sources and save it to the data/raw/ folder. No calculations
happen here — just fetching and saving.

Sources used:
  - mfapi.in         : Free Indian MF API (NAV history + scheme metadata)
  - AMFI NAVAll.txt  : Official AMFI file (ISIN codes, categories, live NAV)
  - yfinance         : Yahoo Finance (benchmark index data)

Run this file directly:
  python collect.py

Or call individual functions from run_pipeline.py
"""

import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — edit these to control what gets collected
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "raw")   # All raw files land here
NAV_YEARS    = 7                                        # How many years of NAV history to keep
API_DELAY    = 0.5                                      # Seconds to wait between API calls (be polite)
API_BASE_URL = "https://api.mfapi.in/mf"

# Benchmark indices — these are Yahoo Finance tickers
# Used later in calculate.py for Beta, Alpha, and category comparisons
BENCHMARKS = {
    "Nifty 50":           "^NSEI",
    "Nifty 500":          "^CRSLDX",
    "Nifty Midcap 150":   "NIFTYMIDCAP150.NS",
    "Nifty Smallcap 250": "HDFCSML250.NS",
    "Nifty Next 50":      "^NSMIDCP",
    "BSE Sensex":         "^BSESN",
    "Nifty Bank":         "^NSEBANK",
    "India 10Y Bond":     "^IRX",        # Proxy for debt fund benchmark
}

# A focused list of well-known funds to start with.
# scheme_code : AMFI scheme code (get the full list from get_all_schemes())
SAMPLE_FUNDS = {
    # Large Cap
    120465: "Axis Large Cap Fund - Direct Plan - Growth",         # was "Axis Bluechip" (120503 → not found)
    118825: "Mirae Asset Large Cap Fund - Direct Plan - Growth",  # code updated: 119598 → 118825
    # (HDFC Top 100 not present in file; replaced with HDFC Nifty 50 Index below)

    # Flexi Cap
    122639: "Parag Parikh Flexi Cap Fund - Direct Plan - Growth", # code updated: 125354 → 122639
    118275: "CANARA ROBECO FLEXICAP FUND - DIRECT PLAN - GROWTH OPTION",  # code updated: 120594 → 118275

    # Mid Cap
    120505: "Axis Midcap Fund - Direct Plan - Growth",            # code confirmed ✓
    119775: "Kotak Midcap Fund - Direct Plan - Growth",           # code confirmed ✓ (was mislabeled as "Kotak Emerging Equity")

    # Small Cap
    125497: "SBI Small Cap Fund - Direct Plan - Growth",          # code confirmed ✓
    118777: "Nippon India Small Cap Fund - Direct Plan Growth",   # code updated: 125497 → 118777

    # Index Funds
    120716: "UTI Nifty 50 Index Fund - Growth Option - Direct",   # code confirmed ✓
    119063: "HDFC Nifty 50 Index Fund - Direct Plan",             # code updated: 120841 → 119063 (renamed in file)

    # Hybrid
    133035: "Kotak Aggressive Hybrid Fund - Direct Plan - Growth", # code updated: 119775 → 133035 (was duplicate key!)
    120251: "ICICI Prudential Equity & Debt Fund - Direct Plan - Growth",  # code updated: 120838 → 120251

    # Debt
    119016: "HDFC Short Term Debt Fund - Growth Option - Direct Plan",  # code updated: 119260 → 119016
    120692: "ICICI Prudential Corporate Bond Fund - Direct Plan - Growth",  # code updated: 120828 → 120692
}


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_output_dir():
    """Create the output directory if it doesn't already exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output folder ready: {OUTPUT_DIR}/")

def safe_get(url, retries=3, delay=2):
    """
    GET request with automatic retry on failure, adding browser headers
    to avoid being blocked by anti-bot systems.
    """
    # 1. Add headers to masquerade as a standard Google Chrome browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    for attempt in range(retries):
        try:
            # 2. Pass the headers and slightly increase the timeout
            response = requests.get(url, headers=headers, timeout=10)

            # 3. Special handling for 404: Don't retry if the fund just doesn't exist
            if response.status_code == 404:
                print(f"  Attempt {attempt + 1} failed: 404 Not Found (Fund not in database)")
                return None

            response.raise_for_status()
            return response

        except requests.RequestException as e:
            # Attempt to grab the status code if a response object exists
            status_code = response.status_code if 'response' in locals() and response is not None else "Network/Timeout"

            print(f"  Attempt {attempt + 1} failed: {e} (Status: {status_code})")

            if attempt < retries - 1:
                # 4. Progressive Backoff: Wait longer after each failure (2s, then 4s)
                time.sleep(delay * (attempt + 1))

    print(f"  Could not fetch: {url}")
    return None

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 1 — Full Scheme List
# Gets every active mutual fund scheme registered with AMFI.
# This is your master lookup table. You pick scheme codes from here.
# ─────────────────────────────────────────────────────────────────────────────

def get_all_schemes():
    """
    Fetches the complete list of all mutual fund schemes from mfapi.in.

    Returns a DataFrame with columns:
        schemeCode | schemeName

    Saved to: data/raw/all_schemes.csv
    """
    print("\n[1] Fetching full scheme list from mfapi.in...")

    response = safe_get(API_BASE_URL)
    if response is None:
        print("  Failed to fetch scheme list.")
        return pd.DataFrame()

    schemes = response.json()
    df = pd.DataFrame(schemes)

    df = df.rename(columns={
        "schemeCode":          "scheme_code",
        "schemeName":          "scheme_name",
        "isinGrowth":          "isin_growth",
        "isinDivReinvestment": "isin_div_reinvestment",
    })

    df["scheme_code"] = df["scheme_code"].astype(int)

    out_path = os.path.join(OUTPUT_DIR, "all_schemes.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df):,} schemes → {out_path}")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 2 — Scheme Metadata
# The /mf/{code} endpoint returns a 'meta' block alongside NAV history.
# That meta block contains the AMC name, category, and scheme type.
# ─────────────────────────────────────────────────────────────────────────────

def get_scheme_metadata(scheme_code):
    """
    Fetches the metadata block for a single scheme from mfapi.in.

    The meta block contains:
        fund_house       : AMC name (e.g. "Axis Mutual Fund")
        scheme_type      : "Open Ended Schemes" / "Close Ended Schemes"
        scheme_category  : Full SEBI category (e.g. "Equity Scheme - Large Cap Fund")
        scheme_code      : Numeric code
        scheme_name      : Full scheme name

    Returns a dict, or None if the request fails.
    """
    url = f"{API_BASE_URL}/{scheme_code}"
    response = safe_get(url)
    if response is None:
        return None

    data = response.json()
    meta = data.get("meta", {})

    # Split the scheme_category into broad_category + sub_category
    # Example: "Equity Scheme - Large Cap Fund"
    #          → broad = "Equity Scheme"  |  sub = "Large Cap Fund"
    full_category = meta.get("scheme_category", "")
    if " - " in full_category:
        parts = full_category.split(" - ", 1)
        broad_category = parts[0].strip()
        sub_category   = parts[1].strip()
    else:
        broad_category = full_category
        sub_category   = ""

    return {
        "scheme_code":      scheme_code,
        "scheme_name":      meta.get("scheme_name", ""),
        "fund_house":       meta.get("fund_house", ""),
        "scheme_type":      meta.get("scheme_type", ""),
        "broad_category":   broad_category,
        "sub_category":     sub_category,
        "full_category":    full_category,
    }


def get_metadata_for_all(fund_dict=SAMPLE_FUNDS):
    """
    Loops through a dictionary of {scheme_code: name} and fetches
    metadata for each. Builds a single metadata table.

    Saved to: data/raw/scheme_metadata.csv
    """
    print("\n[2] Fetching scheme metadata...")

    records = []
    for code, name in fund_dict.items():
        meta = get_scheme_metadata(code)
        if meta:
            records.append(meta)
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ Failed: {code}")
        time.sleep(API_DELAY)

    df = pd.DataFrame(records)
    out_path = os.path.join(OUTPUT_DIR, "scheme_metadata.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} schemes → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 3 — NAV History
# The full day-by-day price history for each fund.
# This is the core data that all return metrics are calculated from.
# ─────────────────────────────────────────────────────────────────────────────

def get_nav_history(scheme_code):
    """
    Fetches the complete NAV history for a single scheme from mfapi.in.

    Returns a DataFrame with columns:
        date | nav | scheme_code

    NAVs are sorted oldest → newest.
    Only the last NAV_YEARS years of data are kept.
    """
    url = f"{API_BASE_URL}/{scheme_code}"
    response = safe_get(url)
    if response is None:
        return pd.DataFrame()

    data = response.json()
    nav_records = data.get("data", [])

    if not nav_records:
        return pd.DataFrame()

    df = pd.DataFrame(nav_records)
    df.columns = ["date", "nav"]
    df["date"]        = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"]         = pd.to_numeric(df["nav"], errors="coerce")
    df["scheme_code"] = scheme_code
    df = df.sort_values("date").reset_index(drop=True)

    # Keep only the last NAV_YEARS years
    cutoff = datetime.today() - timedelta(days=NAV_YEARS * 365)
    df = df[df["date"] >= cutoff]

    return df


def get_nav_history_for_all(fund_dict=SAMPLE_FUNDS):
    """
    Fetches NAV history for every fund in fund_dict.
    Combines them all into one long table (one row per fund per day).

    Saved to: data/raw/nav_history_raw.csv
    """
    print("\n[3] Fetching NAV history...")

    all_nav = []
    for code, name in fund_dict.items():
        print(f"  Fetching: {name}...")
        nav_df = get_nav_history(code)
        if not nav_df.empty:
            nav_df["fund_name"] = name
            all_nav.append(nav_df)
        time.sleep(API_DELAY)

    combined = pd.concat(all_nav, ignore_index=True)
    out_path = os.path.join(OUTPUT_DIR, "nav_history_raw.csv")
    combined.to_csv(out_path, index=False)
    print(f"  Saved {len(combined):,} rows → {out_path}")
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 4 — Scheme Profile (Derived Features from NAV History)
# Things we can calculate from the NAV series itself —
# inception date, fund age, latest NAV, 52-week high/low.
# These do not require an extra API call — they come from the history.
# ─────────────────────────────────────────────────────────────────────────────

def get_scheme_profile(scheme_code, fund_name=""):
    """
    Derives additional features from a fund's NAV history.

    Features extracted:
        inception_date   : Date of the very first NAV on record
        fund_age_years   : How old the fund is (years since inception)
        latest_nav       : Most recent NAV value
        latest_nav_date  : Date of that NAV
        nav_52w_high     : Highest NAV in the last 52 weeks
        nav_52w_low      : Lowest NAV in the last 52 weeks
        nav_52w_change   : % change from 52-week low to current NAV
        total_nav_days   : Number of trading days on record

    Returns a dict.
    """
    nav_df = get_nav_history(scheme_code)
    if nav_df.empty:
        return None

    nav_df = nav_df.sort_values("date")
    today  = datetime.today()
    cutoff_52w = today - timedelta(weeks=52)
    nav_52w = nav_df[nav_df["date"] >= cutoff_52w]

    latest_nav    = nav_df["nav"].iloc[-1]
    nav_52w_low   = nav_52w["nav"].min()
    nav_52w_high  = nav_52w["nav"].max()
    inception_date = nav_df["date"].iloc[0]
    fund_age_years = (today - inception_date).days / 365.25

    return {
        "scheme_code":      scheme_code,
        "fund_name":        fund_name,
        "inception_date":   inception_date.date(),
        "fund_age_years":   round(fund_age_years, 1),
        "latest_nav":       round(latest_nav, 4),
        "latest_nav_date":  nav_df["date"].iloc[-1].date(),
        "nav_52w_high":     round(nav_52w_high, 4),
        "nav_52w_low":      round(nav_52w_low, 4),
        "nav_52w_change_pct": round((latest_nav - nav_52w_low) / nav_52w_low * 100, 2),
        "total_nav_days":   len(nav_df),
    }


def get_scheme_profiles_for_all(fund_dict=SAMPLE_FUNDS):
    """
    Builds the full scheme profile table for all funds.

    Saved to: data/raw/scheme_profiles.csv
    """
    print("\n[4] Building scheme profiles (NAV-derived features)...")

    profiles = []
    for code, name in fund_dict.items():
        print(f"  Profiling: {name}...")
        profile = get_scheme_profile(code, name)
        if profile:
            profiles.append(profile)
        time.sleep(API_DELAY)

    df = pd.DataFrame(profiles)
    out_path = os.path.join(OUTPUT_DIR, "scheme_profiles.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} scheme profiles → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 5 — AMFI Master Data (ISIN codes + Live NAV + Category)
# AMFI publishes a flat text file daily with every fund's current NAV.
# It also contains ISIN codes, which are the universal fund identifiers
# used on stock exchanges and in most third-party platforms.
# ─────────────────────────────────────────────────────────────────────────────

def get_amfi_master_data():
    """
    Downloads and parses the AMFI NAVAll.txt file.
    This is the official end-of-day NAV file published by AMFI every evening.

    Extracts:
        scheme_code      : AMFI numeric code
        isin_growth      : ISIN for the Growth option
        isin_idcw        : ISIN for the IDCW (dividend) option
        scheme_name      : Full scheme name
        nav              : Today's NAV
        nav_date         : Date of that NAV
        broad_category   : Top-level category parsed from section headers
        amc_name         : AMC name parsed from section headers

    Saved to: data/raw/amfi_master.csv
    """
    print("\n[5] Downloading AMFI NAVAll.txt...")

    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    response = safe_get(url)
    if response is None:
        print("  Failed to download AMFI master file.")
        return pd.DataFrame()

    lines = response.text.splitlines()
    records = []
    current_amc      = ""
    current_category = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Lines with semicolons are fund data rows
        if ";" in line:
            parts = line.split(";")
            if len(parts) < 6:
                continue
            # Check if this looks like a header row (non-numeric scheme code)
            if not parts[0].strip().isdigit():
                continue

            try:
                records.append({
                    "scheme_code":    int(parts[0].strip()),
                    "isin_growth":    parts[1].strip(),
                    "isin_idcw":      parts[2].strip(),
                    "scheme_name":    parts[3].strip(),
                    "nav":            float(parts[4].strip()) if parts[4].strip() not in ["", "N.A."] else None,
                    "nav_date":       parts[5].strip(),
                    "amc_name":       current_amc,
                    "broad_category": current_category,
                })
            except (ValueError, IndexError):
                continue

        # Lines without semicolons are section headers (AMC or category names)
        else:
            # Heuristic: if it contains "Mutual Fund" it is an AMC name
            if "Mutual Fund" in line or "AMC" in line or "Asset Management" in line:
                current_amc = line
            else:
                current_category = line

    df = pd.DataFrame(records)
    if not df.empty:
        df["nav_date"] = pd.to_datetime(df["nav_date"], format="%d-%b-%Y", errors="coerce")

    out_path = os.path.join(OUTPUT_DIR, "amfi_master.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df):,} schemes → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 6 — Benchmark Index Data
# Needed to calculate Beta, Alpha, and to compare fund returns
# against the market index. Fetched from Yahoo Finance via yfinance.
# ─────────────────────────────────────────────────────────────────────────────

def get_benchmark_data(years=NAV_YEARS):
    """
    Downloads historical price data for all benchmark indices
    defined in the BENCHMARKS dictionary at the top of this file.

    Returns a wide DataFrame where each column is one benchmark index.
    Dates are the index.

    Saved to: data/raw/benchmark_data.csv
    """
    print("\n[6] Fetching benchmark index data from Yahoo Finance...")

    start_date = (datetime.today() - timedelta(days=years * 365)).strftime("%Y-%m-%d")
    end_date   = datetime.today().strftime("%Y-%m-%d")

    all_benchmarks = {}

    for name, ticker in BENCHMARKS.items():
        print(f"  Fetching: {name} ({ticker})...")
        try:
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=True,      # Adjusts for splits and dividends
            )
            if data.empty:
                print(f"    No data returned for {ticker}")
                continue

            all_benchmarks[name] = data["Close"].squeeze()

        except Exception as e:
            print(f"    Error fetching {ticker}: {e}")
        time.sleep(0.3)

    df = pd.DataFrame(all_benchmarks)
    df.index.name = "date"
    df = df.sort_index()

    out_path = os.path.join(OUTPUT_DIR, "benchmark_data.csv")
    df.to_csv(out_path)
    print(f"  Saved benchmark data ({len(df)} days, {len(df.columns)} indices) → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 7 — Expense Ratio Data (from AMFI monthly TER disclosure)
# SEBI mandates that every AMC publish Total Expense Ratios monthly.
# AMFI aggregates this into a downloadable file.
# ─────────────────────────────────────────────────────────────────────────────
# TODO: Update get_aum_and_ter() to fetch per-scheme aum and ter from the amfi website, Problem:Website is written in JavaScript
#def get_aum_and_ter(fund_dict=SAMPLE_FUNDS):
    """
    Fetches AUM (₹ crore), expense ratio (%), Morningstar star rating,
    and latest NAV for each fund from mfdata.in.

    This single function replaces the two dead AMFI endpoints:
        ✗ amfiindia.com/modules/AumData   → 404
        ✗ amfiindia.com/modules/TerHtml   → 404
        ✓ mfdata.in/api/v1/schemes/{code} → works, free, no auth

    Saved to: data/raw/aum_and_ter.csv
    """
    print("\n[7] Fetching AUM + TER from mfdata.in...")

    records = []

    for code, name in fund_dict.items():

        # ── Primary: mfdata.in ────────────────────────────────────────────
        url      = f"https://mfdata.in/api/v1/schemes/{code}"
        response = safe_get(url)

        if response is not None:
            try:
                data = response.json().get("data", {})
                records.append({
                    "scheme_code":       code,
                    "fund_name":         name,
                    "aum_cr":            data.get("aum_cr"),
                    "expense_ratio_pct": data.get("expense_ratio"),
                    "morningstar_stars": data.get("morningstar"),
                    "latest_nav":        data.get("nav"),
                    "latest_nav_date":   data.get("nav_date"),
                    "source":            "mfdata.in",
                })
                print(f"  ✓ {name}  [mfdata.in]")
                time.sleep(API_DELAY)
                continue                  # ← skip fallback if primary worked
            except Exception as e:
                print(f"  Parse error from mfdata.in for {name}: {e}")

        # ── Fallback: mfapi.in ────────────────────────────────────────────
        # mfapi.in returns AUM inside the meta block of the scheme detail
        print(f"  → Falling back to mfapi.in for {name}...")
        url      = f"https://api.mfapi.in/mf/{code}"
        response = safe_get(url)

        if response is not None:
            try:
                data = response.json()
                meta = data.get("meta", {})
                records.append({
                    "scheme_code":       code,
                    "fund_name":         name,
                    "aum_cr":            None,   # mfapi.in does not carry AUM
                    "expense_ratio_pct": None,   # mfapi.in does not carry TER
                    "morningstar_stars": None,
                    "latest_nav":        data["data"][0]["nav"] if data.get("data") else None,
                    "latest_nav_date":   data["data"][0]["date"] if data.get("data") else None,
                    "source":            "mfapi.in (fallback — AUM/TER unavailable)",
                })
                print(f"  ✓ {name}  [mfapi.in fallback]")
            except Exception as e:
                print(f"  ✗ Both sources failed for {name}: {e}")
        else:
            print(f"  ✗ Both sources failed for {name}")

        time.sleep(API_DELAY)

    df = pd.DataFrame(records)
    out_path = os.path.join(OUTPUT_DIR, "aum_and_ter.csv")
    df.to_csv(out_path, index=False)
    print(f"\n  Saved {len(df)} records → {out_path}")

    # Warn if AUM data is missing for any fund
    missing = df["aum_cr"].isna().sum()
    if missing > 0:
        print(f"  ⚠ AUM missing for {missing} fund(s) — mfdata.in was unavailable for those.")
    return df

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 8 (REVISED) — AUM via AMFI monthly excel file
# Replaces both the dead AMFI AumData and TerHtml endpoints.
# Returns AUM, expense ratio, Morningstar rating, and current NAV
# for each scheme — all from one API call per fund.
# ─────────────────────────────────────────────────────────────────────────────

def get_aum_from_amfi_excel():
    """
    Downloads the AMFI Monthly report Excel file from portal.amfiindia.com.

    Correct URL pattern (confirmed May 2026):
        https://portal.amfiindia.com/spages/am{mon}{year}repo.xls
        e.g. amapr2026repo.xls, ammar2026repo.xls

    Note: AMFI publishes after month end. On May 17 2026, the latest
    available file is April 2026 — May 2026 does not exist yet.

    Saved to: data/raw/aum_amfi_monthly.csv
    """
    print("\n[8] Fetching AUM from AMFI Monthly Excel...")

    from datetime import datetime, timedelta
    from io import BytesIO

    BASE_URL = "https://portal.amfiindia.com/spages"

    # Month abbreviations exactly as AMFI uses them in filenames
    MONTH_MAP = {
        1: "jan", 2: "feb",  3: "mar", 4: "apr",
        5: "may", 6: "jun",  7: "jul", 8: "aug",
        9: "sep", 10: "oct", 11: "nov", 12: "dec"
    }

    # Try current month first, then walk back up to 3 months
    # (AMFI publishes ~7-10 days after month end so current month
    #  is often unavailable for the first week of a new month)
    today = datetime.today()

    for offset in range(4):
        target     = today.replace(day=1) - timedelta(days=30 * offset)
        mon_str    = MONTH_MAP[target.month]          # e.g. "apr"
        year_str   = target.strftime("%Y")            # e.g. "2026"
        filename   = f"am{mon_str}{year_str}repo.xls"
        url        = f"{BASE_URL}/{filename}"

        print(f"  Trying: {url}")
        response = safe_get(url)

        if response is not None and response.status_code == 200:
            print(f"  ✓ Found: {filename}")

            try:
                df = pd.read_excel(BytesIO(response.content), engine="xlrd")
            except Exception:
                # If xlrd not installed, save raw file and inform user
                raw_path = os.path.join(OUTPUT_DIR, filename)
                with open(raw_path, "wb") as f:
                    f.write(response.content)
                print(f"  Saved raw .xls → {raw_path}")
                print("  Run: pip install xlrd   then re-run this function")
                return pd.DataFrame()

            # Standardise column names
            df.columns = [
                str(c).strip().lower().replace(" ", "_") for c in df.columns
            ]

            print(f"  Columns: {df.columns.tolist()}")
            print(f"  Rows: {len(df)}")

            out_path = os.path.join(OUTPUT_DIR, "aum_amfi_monthly.csv")
            df.to_csv(out_path, index=False)
            print(f"  Saved → {out_path}")
            return df

        print(f"  ✗ Not found — trying previous month...")

    print("  Could not fetch any recent AMFI Monthly file.")
    print("  Download manually from: https://www.amfiindia.com/research-information/amfi-monthly")
    return pd.DataFrame()

# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 9 — Category Classification Table
# A clean lookup table of SEBI's fund categories.
# Used in Power BI for slicers and category-level comparisons.
# ─────────────────────────────────────────────────────────────────────────────

def build_category_reference():
    """
    Builds a static reference table of SEBI's official mutual fund categories.
    These are SEBI-mandated as of October 2017 (Circular SEBI/HO/IMD/DF3/CIR/P/2017/114).

    This table is used in Power BI to:
        - Drive the Category slicer
        - Group funds for peer comparison
        - Assign benchmark indices per category

    Saved to: data/raw/category_reference.csv
    """
    print("\n[9] Building SEBI category reference table...")

    categories = [
        # Broad | Sub-category | Typical benchmark | Risk level
        ("Equity Scheme",       "Large Cap Fund",               "Nifty 100",              "Moderately High"),
        ("Equity Scheme",       "Large & Mid Cap Fund",         "Nifty LargeMidcap 250",  "Moderately High"),
        ("Equity Scheme",       "Mid Cap Fund",                 "Nifty Midcap 150",       "High"),
        ("Equity Scheme",       "Small Cap Fund",               "Nifty Smallcap 250",     "Very High"),
        ("Equity Scheme",       "Multi Cap Fund",               "Nifty 500",              "High"),
        ("Equity Scheme",       "Flexi Cap Fund",               "Nifty 500",              "Moderately High"),
        ("Equity Scheme",       "ELSS",                         "Nifty 500",              "High"),
        ("Equity Scheme",       "Sectoral / Thematic Fund",     "Nifty 500",              "Very High"),
        ("Equity Scheme",       "Focused Fund",                 "Nifty 500",              "High"),
        ("Equity Scheme",       "Dividend Yield Fund",          "Nifty Dividend Opp 50",  "Moderately High"),
        ("Equity Scheme",       "Value Fund",                   "Nifty 500 Value 50",     "Moderately High"),
        ("Equity Scheme",       "Contra Fund",                  "Nifty 500",              "Moderately High"),
        ("Hybrid Scheme",       "Aggressive Hybrid Fund",       "Nifty 50 Hybrid 65:35",  "Moderately High"),
        ("Hybrid Scheme",       "Conservative Hybrid Fund",     "Nifty 50 Hybrid 25:75",  "Moderate"),
        ("Hybrid Scheme",       "Balanced Hybrid Fund",         "Nifty 50 Hybrid 50:50",  "Moderate"),
        ("Hybrid Scheme",       "Dynamic Asset Allocation",     "Nifty 50",               "Moderate"),
        ("Hybrid Scheme",       "Multi Asset Allocation",       "Nifty 50",               "Moderate"),
        ("Hybrid Scheme",       "Arbitrage Fund",               "Nifty 50 Arbitrage",     "Low"),
        ("Hybrid Scheme",       "Equity Savings Fund",          "Nifty Equity Savings",   "Low to Moderate"),
        ("Debt Scheme",         "Overnight Fund",               "CRISIL Overnight",       "Low"),
        ("Debt Scheme",         "Liquid Fund",                  "CRISIL Liquid",          "Low"),
        ("Debt Scheme",         "Ultra Short Duration Fund",    "CRISIL Ultra Short",     "Low to Moderate"),
        ("Debt Scheme",         "Low Duration Fund",            "CRISIL Low Duration",    "Low to Moderate"),
        ("Debt Scheme",         "Money Market Fund",            "CRISIL Money Market",    "Low to Moderate"),
        ("Debt Scheme",         "Short Duration Fund",          "CRISIL Short Term",      "Moderate"),
        ("Debt Scheme",         "Medium Duration Fund",         "CRISIL Medium Term",     "Moderate"),
        ("Debt Scheme",         "Medium to Long Duration Fund", "CRISIL Composite Bond",  "Moderate"),
        ("Debt Scheme",         "Long Duration Fund",           "CRISIL Long Term Gilt",  "Moderately High"),
        ("Debt Scheme",         "Dynamic Bond Fund",            "CRISIL Composite Bond",  "Moderate"),
        ("Debt Scheme",         "Corporate Bond Fund",          "CRISIL Corporate Bond",  "Moderate"),
        ("Debt Scheme",         "Credit Risk Fund",             "CRISIL Credit Risk",     "High"),
        ("Debt Scheme",         "Banking & PSU Fund",           "CRISIL Banking & PSU",   "Moderate"),
        ("Debt Scheme",         "Gilt Fund",                    "CRISIL Gilt",            "Moderate"),
        ("Debt Scheme",         "Floater Fund",                 "CRISIL Short Term",      "Low to Moderate"),
        ("Index / ETF Scheme",  "Index Fund - Nifty 50",        "Nifty 50",               "Moderately High"),
        ("Index / ETF Scheme",  "Index Fund - Nifty Next 50",   "Nifty Next 50",          "High"),
        ("Index / ETF Scheme",  "Index Fund - Nifty Midcap",    "Nifty Midcap 150",       "High"),
        ("Index / ETF Scheme",  "Index Fund - Sensex",          "BSE Sensex",             "Moderately High"),
        ("Index / ETF Scheme",  "Gold ETF",                     "Domestic Gold Price",    "Moderate"),
        ("Solution Oriented",   "Retirement Fund",              "Nifty 50",               "Varies"),
        ("Solution Oriented",   "Children's Fund",              "Nifty 50",               "Varies"),
    ]

    df = pd.DataFrame(categories, columns=[
        "broad_category", "sub_category", "benchmark_index", "risk_level"
    ])

    out_path = os.path.join(OUTPUT_DIR, "category_reference.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} categories → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# FUNCTION 10 — Rolling NAV Snapshot (for momentum analysis)
# Captures NAV values at fixed points in the past.
# Used in Power BI to show 1M / 3M / 6M / 1Y point-in-time returns
# without recalculating the full series every time.
# ─────────────────────────────────────────────────────────────────────────────

def get_nav_snapshots(fund_dict=SAMPLE_FUNDS):
    """
    For each fund, captures the NAV at fixed lookback points:
        today, 1 month ago, 3 months ago, 6 months ago, 1 year ago, 3 years ago

    These snapshots are used in Power BI to calculate period returns quickly
    without having to process the full NAV series in DAX.

    Saved to: data/raw/nav_snapshots.csv
    """
    print("\n[10] Capturing NAV snapshots at fixed dates...")

    today = datetime.today()
    lookbacks = {
        "nav_today":   today,
        "nav_1m_ago":  today - timedelta(days=30),
        "nav_3m_ago":  today - timedelta(days=91),
        "nav_6m_ago":  today - timedelta(days=182),
        "nav_1y_ago":  today - timedelta(days=365),
        "nav_3y_ago":  today - timedelta(days=1095),
        "nav_5y_ago":  today - timedelta(days=1825),
    }

    records = []

    for code, name in fund_dict.items():
        nav_df = get_nav_history(code)
        if nav_df.empty:
            continue

        nav_df = nav_df.sort_values("date").set_index("date")
        record = {"scheme_code": code, "fund_name": name}

        for label, target_date in lookbacks.items():
            # Get the closest available NAV on or before the target date
            past = nav_df[nav_df.index <= pd.Timestamp(target_date)]
            record[label] = round(past["nav"].iloc[-1], 4) if not past.empty else None

        records.append(record)
        print(f"  ✓ {name}")
        time.sleep(API_DELAY)

    df = pd.DataFrame(records)
    out_path = os.path.join(OUTPUT_DIR, "nav_snapshots.csv")
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} snapshot records → {out_path}")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MASTER RUNNER — calls all functions in the correct order
# ─────────────────────────────────────────────────────────────────────────────

def run_all():
    """
    Runs the full data collection pipeline in the correct sequence.
    Each function saves its own output file to data/raw/.
    """
    print("=" * 60)
    print("  MUTUAL FUND DASHBOARD — DATA COLLECTION")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    ensure_output_dir()

    get_all_schemes()              # → all_schemes.csv
    get_metadata_for_all()         # → scheme_metadata.csv
    get_nav_history_for_all()      # → nav_history_raw.csv
    get_scheme_profiles_for_all()  # → scheme_profiles.csv
    get_amfi_master_data()         # → amfi_master.csv
    get_benchmark_data()           # → benchmark_data.csv
    #get_aum_and_ter()              # → aum_and_ter.csv
    get_aum_from_amfi_excel()      # -> aum_amfi_monthly.csv
    build_category_reference()     # → category_reference.csv
    get_nav_snapshots()            # → nav_snapshots.csv

    print("\n" + "=" * 60)
    print("  COLLECTION COMPLETE")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  All files saved to: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    run_all()