"""
clean.py — Data Cleaning Layer
===============================
Mutual Fund Analysis Dashboard — Stage 2
-----------------------------------------
Reads all raw CSV files from data/raw/, cleans and standardises the datasets
(handling date parsing, whitespace trimming, null conversions, and anomaly checks),
and writes the cleaned CSVs to data/cleaned/.

This script bridges the gap between raw data collection and final metric calculation.
No external APIs or databases are hit — it only reads from data/raw/ and writes to data/cleaned/.

Run this file directly:
    python clean.py

Or it will be called automatically by run_pipeline.py
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime

# --- Set display options for comfortable inspection ---
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', 60)
pd.set_option('display.float_format', '{:.4f}'.format)

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR  = os.path.join(BASE_DIR, "data", "raw")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "cleaned")

# -----------------------------------------------------------------------------
# UTILITY HELPERS
# -----------------------------------------------------------------------------

def ensure_output_dir():
    """Create the output directory if it doesn't already exist."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"  [OK] Output folder ready: {OUTPUT_DIR}/")

def check_file_exists(filename):
    """Checks if a file exists in the raw data folder."""
    path = os.path.join(INPUT_DIR, filename)
    return os.path.exists(path)

# -----------------------------------------------------------------------------
# MODULE CLEANING FUNCTIONS
# -----------------------------------------------------------------------------

def clean_all_schemes():
    """
    Cleans all_schemes.csv.
    - Trims whitespace from scheme_name.
    - Ensures scheme_code is integer.
    - Warns/reports duplicate scheme_codes.
    """
    filename = "all_schemes.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[1] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 1a. Trim whitespace
    df['scheme_name'] = df['scheme_name'].str.strip()

    # 1b. Ensure scheme_code is int
    df['scheme_code'] = df['scheme_code'].astype(int)

    # 1c. Check duplicates
    dups = df.duplicated(subset=['scheme_code']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate scheme_codes in all_schemes.csv")
    else:
        print("  [OK] No duplicate scheme_codes found.")

    out_path = os.path.join(OUTPUT_DIR, "all_schemes_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_amfi_master():
    """
    Cleans amfi_master.csv.
    - Replaces '-' placeholders in ISIN columns with NaN.
    - Converts nav_date from string to datetime.
    - Trims whitespace from string columns.
    - Verifies unique scheme_codes.
    """
    filename = "amfi_master.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[2] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 2a. Replace '-' string placeholder with NaN in ISIN columns
    df['isin_growth'] = df['isin_growth'].replace('-', np.nan)
    df['isin_idcw']   = df['isin_idcw'].replace('-', np.nan)

    # 2b. Convert nav_date from string to datetime
    df['nav_date'] = pd.to_datetime(df['nav_date'], errors='coerce')
    failed_dates = df['nav_date'].isnull().sum()
    if failed_dates > 0:
        print(f"  [WARN] {failed_dates} nav_date cells failed to parse into datetimes")

    # 2c. Trim whitespace from all string columns
    str_cols = ['isin_growth', 'isin_idcw', 'scheme_name', 'amc_name', 'broad_category']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            # Restore NaN values that became 'nan' string
            df[col] = df[col].replace('nan', np.nan)

    # 2d. Check duplicate scheme_codes
    dups = df.duplicated(subset=['scheme_code']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate scheme_codes in amfi_master.csv")
    else:
        print("  [OK] No duplicate scheme_codes found.")

    out_path = os.path.join(OUTPUT_DIR, "amfi_master_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_aum_monthly():
    """
    Cleans aum_amfi_monthly.csv.
    - Reads with correct headers (skipping metadata title rows).
    - Renames columns to short, clear standard names.
    - Drops category group label and footnotes rows (non-numeric rows).
    - Standardises numeric columns.
    - Trims whitespace from strings.
    """
    filename = "aum_amfi_monthly.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[3] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)

    # 3a. Read correctly skipping the title rows (skipping index 0 and 1)
    df = pd.read_csv(path, skiprows=[0, 1], header=0)
    shape_before = df.shape

    # 3b. Rename columns to clean, short names
    df.columns = [
        'sr_no', 'scheme_name', 'num_schemes', 'num_folios',
        'funds_mobilized_cr', 'repurchase_redemption_cr', 'net_inflow_outflow_cr',
        'aum_cr', 'avg_aum_cr', 'segregated_portfolios', 'segregated_aum_cr'
    ]

    # 3c. Drop group label and footnote rows
    # We identify these where all primary numeric columns are null/blank
    numeric_cols = ['num_schemes', 'funds_mobilized_cr', 'aum_cr']
    mask_empty = df[numeric_cols].isnull().all(axis=1)
    df = df[~mask_empty].reset_index(drop=True)

    # 3d. Convert numeric columns
    cols_to_numeric = [
        'num_schemes', 'num_folios', 'funds_mobilized_cr',
        'repurchase_redemption_cr', 'net_inflow_outflow_cr',
        'aum_cr', 'avg_aum_cr', 'segregated_portfolios', 'segregated_aum_cr'
    ]
    for col in cols_to_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 3e. Trim whitespace in string columns
    df['scheme_name'] = df['scheme_name'].str.strip()
    df['sr_no']       = df['sr_no'].astype(str).str.strip()

    out_path = os.path.join(OUTPUT_DIR, "aum_amfi_monthly_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_benchmark_data():
    """
    Cleans benchmark_data.csv.
    - Converts date column to datetime.
    - Sorts by date ascending.
    - Ensures all index columns are numeric (float).
    - Checks for duplicate dates.
    """
    filename = "benchmark_data.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[4] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 4a. Convert date column to datetime
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    failed = df['date'].isnull().sum()
    if failed > 0:
        print(f"  [WARN] {failed} dates failed to parse in benchmark_data.csv")

    # 4b. Sort by date ascending
    df = df.sort_values('date').reset_index(drop=True)

    # 4c. Verify unique dates
    dups = df.duplicated(subset=['date']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate dates in benchmark_data.csv")

    # 4d. Ensure all index columns are float
    index_cols = ['Nifty 50', 'Nifty 500', 'Nifty Midcap 150', 'Nifty Smallcap 250',
                  'Nifty Next 50', 'BSE Sensex', 'Nifty Bank', 'India 10Y Bond']
    for col in index_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    out_path = os.path.join(OUTPUT_DIR, "benchmark_data_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_category_reference():
    """
    Cleans category_reference.csv.
    - Trims whitespace from all string columns.
    - Verifies uniqueness of sub_category (Primary Key).
    """
    filename = "category_reference.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[5] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 5a. Trim whitespace on string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].str.strip()

    # 5b. Verify sub_category is unique
    dups = df.duplicated(subset=['sub_category']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate sub_categories in category_reference.csv")
    else:
        print("  [OK] sub_category uniqueness confirmed.")

    out_path = os.path.join(OUTPUT_DIR, "category_reference_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_nav_history():
    """
    Cleans nav_history_raw.csv.
    - Converts date to datetime.
    - Sorts by scheme_code and date ascending.
    - Trims whitespace in fund_name.
    - Checks for invalid NAV values (<= 0).
    - Verifies composite key uniqueness (scheme_code + date).
    """
    filename = "nav_history_raw.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[6] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 6a. Convert date to datetime
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    failed = df['date'].isnull().sum()
    if failed > 0:
        print(f"  [WARN] {failed} dates failed to parse in nav_history_raw.csv")

    # 6b. Trim whitespace in fund_name
    df['fund_name'] = df['fund_name'].str.strip()

    # 6c. Sort by scheme_code then date
    df = df.sort_values(['scheme_code', 'date']).reset_index(drop=True)

    # 6d. Check invalid NAV values (<= 0)
    invalid_nav = df[df['nav'] <= 0]
    if len(invalid_nav) > 0:
        print(f"  [WARN] Found {len(invalid_nav)} rows with NAV <= 0!")
        print(invalid_nav.head(5))
    else:
        print("  [OK] All NAV values are positive.")

    # 6e. Verify composite key uniqueness (scheme_code + date)
    dups = df.duplicated(subset=['scheme_code', 'date']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate (scheme_code, date) pairs in nav_history!")
    else:
        print("  [OK] Composite key (scheme_code, date) uniqueness confirmed.")

    out_path = os.path.join(OUTPUT_DIR, "nav_history_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_nav_snapshots():
    """
    Cleans nav_snapshots.csv.
    - Trims fund_name whitespace.
    - Validates nav_today is positive.
    - Verifies uniqueness of scheme_code.
    """
    filename = "nav_snapshots.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[7] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 7a. Trim fund_name whitespace
    df['fund_name'] = df['fund_name'].str.strip()

    # 7b. Validate nav_today is positive
    invalid = (df['nav_today'] <= 0).sum()
    if invalid > 0:
        print(f"  [WARN] Found {invalid} rows where nav_today is negative or zero!")
    else:
        print("  [OK] All today's NAVs are positive.")

    # 7c. Check duplicate scheme_codes
    dups = df.duplicated(subset=['scheme_code']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate scheme_codes in nav_snapshots.csv")
    else:
        print("  [OK] scheme_code uniqueness confirmed.")

    out_path = os.path.join(OUTPUT_DIR, "nav_snapshots_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_scheme_metadata():
    """
    Cleans scheme_metadata.csv.
    - Identifies and flags incomplete metadata rows using boolean flag `metadata_complete`.
    - Trims whitespace on string columns.
    - Verifies unique scheme_codes.
    """
    filename = "scheme_metadata.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[8] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 8a. Flag incomplete metadata rows (rows with any null values)
    df['metadata_complete'] = ~df.isnull().any(axis=1)
    incomplete_count = (~df['metadata_complete']).sum()
    if incomplete_count > 0:
        print(f"  [WARN] {incomplete_count} rows have incomplete metadata (flagged in metadata_complete).")

    # 8b. Trim whitespace on string columns
    str_cols = ['scheme_name', 'fund_house', 'scheme_type', 'broad_category', 'sub_category', 'full_category']
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace('nan', np.nan)

    # 8c. Check duplicate scheme_codes
    dups = df.duplicated(subset=['scheme_code']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate scheme_codes in scheme_metadata.csv")
    else:
        print("  [OK] scheme_code uniqueness confirmed.")

    out_path = os.path.join(OUTPUT_DIR, "scheme_metadata_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_scheme_profiles():
    """
    Cleans scheme_profiles.csv.
    - Converts inception_date and latest_nav_date to datetime.
    - Logical validation (52w high >= 52w low).
    - Age and trade days validation (> 0).
    - Trims fund_name whitespace.
    """
    filename = "scheme_profiles.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[9] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 9a. Convert date columns to datetime
    df['inception_date']    = pd.to_datetime(df['inception_date'], errors='coerce')
    df['latest_nav_date']   = pd.to_datetime(df['latest_nav_date'], errors='coerce')

    # 9b. Logical validation: 52w high >= 52w low
    invalid_range = df[df['nav_52w_high'] < df['nav_52w_low']]
    if len(invalid_range) > 0:
        print(f"  [WARN] Found {len(invalid_range)} rows where 52w_high < 52w_low!")
        print(invalid_range[['scheme_code', 'fund_name', 'nav_52w_high', 'nav_52w_low']].head(5))

    # 9c. Age and trade days validation
    invalid_age = (df['fund_age_years'] <= 0).sum()
    invalid_days = (df['total_nav_days'] <= 0).sum()
    if invalid_age > 0:
        print(f"  [WARN] Found {invalid_age} rows with fund_age_years <= 0")
    if invalid_days > 0:
        print(f"  [WARN] Found {invalid_days} rows with total_nav_days <= 0")

    # 9d. Trim fund_name whitespace
    df['fund_name'] = df['fund_name'].str.strip()

    out_path = os.path.join(OUTPUT_DIR, "scheme_profiles_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df


def clean_aum_and_ter():
    """
    Cleans aum_and_ter.csv.
    - Standardises scheme_code to integer.
    - Trim whitespace on strings.
    - Parses and ensures float/numeric fields for aum_cr, expense_ratio_pct, morningstar_stars, latest_nav.
    - Standardises latest_nav_date to datetime.
    - Flags rows with nav_available and aum_ter_available flags.
    - Verifies uniqueness of scheme_code.
    """
    filename = "aum_and_ter.csv"
    if not check_file_exists(filename):
        print(f"  [MISSING] Raw file not found: {filename} — skipping")
        return pd.DataFrame()

    print(f"\n[10] Cleaning {filename}...")
    path = os.path.join(INPUT_DIR, filename)
    df = pd.read_csv(path)
    shape_before = df.shape

    # 10a. Trim whitespace
    df['fund_name'] = df['fund_name'].str.strip()
    df['source']    = df['source'].str.strip()

    # 10b. Ensure scheme_code is int
    df['scheme_code'] = df['scheme_code'].astype(int)

    # 10c. Convert date column
    df['latest_nav_date'] = pd.to_datetime(df['latest_nav_date'], errors='coerce')

    # 10d. Ensure numeric columns
    numeric_cols = ['aum_cr', 'expense_ratio_pct', 'morningstar_stars', 'latest_nav']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 10e. Add flag columns
    df['nav_available']     = ~df['latest_nav'].isnull()
    df['aum_ter_available'] = ~df['aum_cr'].isnull() & ~df['expense_ratio_pct'].isnull()

    # 10f. Check duplicate scheme_codes
    dups = df.duplicated(subset=['scheme_code']).sum()
    if dups > 0:
        print(f"  [WARN] Found {dups} duplicate scheme_codes in aum_and_ter.csv")
    else:
        print("  [OK] scheme_code uniqueness confirmed.")

    out_path = os.path.join(OUTPUT_DIR, "aum_and_ter_clean.csv")
    df.to_csv(out_path, index=False)
    print(f"  [OK] Cleaned: {shape_before} -> {df.shape} saved to {out_path}")
    return df

# -----------------------------------------------------------------------------
# CROSS-FILE INTEGRITY DIAGNOSTIC
# -----------------------------------------------------------------------------

def run_cross_file_diagnostics(cleaned_dfs):
    """
    Runs integrity diagnostic reports across files.
    This exactly mirrors the validation cells in the notebook.
    """
    print("\n" + "=" * 60)
    print("  CROSS-FILE INTEGRITY DIAGNOSTICS")
    print("=" * 60)

    # Make sure we have the required cleaned dfs loaded
    schemes_df = cleaned_dfs.get('all_schemes')
    amfi_df    = cleaned_dfs.get('amfi_master')
    nav_df     = cleaned_dfs.get('nav_history')
    snap_df    = cleaned_dfs.get('nav_snapshots')
    meta_df    = cleaned_dfs.get('scheme_metadata')
    prof_df    = cleaned_dfs.get('scheme_profiles')
    aum_ter_df = cleaned_dfs.get('aum_and_ter')

    codes = {}
    if schemes_df is not None and not schemes_df.empty:
        codes['all_schemes'] = set(schemes_df['scheme_code'])
    if amfi_df is not None and not amfi_df.empty:
        codes['amfi_master'] = set(amfi_df['scheme_code'])
    if nav_df is not None and not nav_df.empty:
        codes['nav_history_raw'] = set(nav_df['scheme_code'])
    if snap_df is not None and not snap_df.empty:
        codes['nav_snapshots'] = set(snap_df['scheme_code'])
    if meta_df is not None and not meta_df.empty:
        codes['scheme_metadata'] = set(meta_df['scheme_code'])
    if prof_df is not None and not prof_df.empty:
        codes['scheme_profiles'] = set(prof_df['scheme_code'])
    if aum_ter_df is not None and not aum_ter_df.empty:
        codes['aum_and_ter'] = set(aum_ter_df['scheme_code'])

    print("Scheme code counts per file:")
    for name, s in codes.items():
        print(f"  - {name:<18}: {len(s):,} unique codes")

    # Orphan checks
    if 'nav_history_raw' in codes and 'all_schemes' in codes:
        orphans = codes['nav_history_raw'] - codes['all_schemes']
        print(f"\n  Orphan codes in NAV History (not present in all_schemes master): {len(orphans)}")
        if orphans:
            print(f"    Orphan codes list: {sorted(list(orphans))}")
        else:
            print("    [OK] Integrity Check Passed: No orphan codes in NAV history.")

    if 'scheme_metadata' in codes and 'nav_history_raw' in codes:
        overlap = codes['scheme_metadata'] & codes['nav_history_raw']
        print(f"  scheme_metadata coverage in NAV history: {len(overlap)} / {len(codes['scheme_metadata'])}")


# -----------------------------------------------------------------------------
# MASTER RUNNER
# -----------------------------------------------------------------------------

def run_all():
    """
    Runs the full data cleaning pipeline in the correct sequence.
    Saves all cleaned CSV files directly to data/cleaned/.
    """
    print("=" * 60)
    print("  MUTUAL FUND DASHBOARD - DATA CLEANING STAGE")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    ensure_output_dir()

    cleaned_dfs = {}
    cleaned_dfs['all_schemes']      = clean_all_schemes()
    cleaned_dfs['amfi_master']      = clean_amfi_master()
    cleaned_dfs['aum_monthly']      = clean_aum_monthly()
    cleaned_dfs['benchmark_data']   = clean_benchmark_data()
    cleaned_dfs['category_ref']      = clean_category_reference()
    cleaned_dfs['nav_history']      = clean_nav_history()
    cleaned_dfs['nav_snapshots']    = clean_nav_snapshots()
    cleaned_dfs['scheme_metadata']  = clean_scheme_metadata()
    cleaned_dfs['scheme_profiles']  = clean_scheme_profiles()
    cleaned_dfs['aum_and_ter']      = clean_aum_and_ter()

    # Run integrity diagnostic reports across the cleaned dfs
    run_cross_file_diagnostics(cleaned_dfs)

    print("\n" + "=" * 60)
    print("  CLEANING COMPLETE")
    print(f"  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  All files saved to: {OUTPUT_DIR}/")
    print("=" * 60)


if __name__ == "__main__":
    run_all()
