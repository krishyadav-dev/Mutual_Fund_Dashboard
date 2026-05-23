"""
calculate.py — Metrics Calculation Engine
==========================================
Mutual Fund Analysis Dashboard — Stage 3
------------------------------------------
Reads all clean CSV files and produces two output files:

    data/output/fund_metrics.csv     ← Main fact table for Power BI (one row per fund)
    data/output/rolling_returns.csv  ← Rolling 1Y returns over time (for line charts)

Every number that appears in the Power BI dashboard is born here.
No data is fetched from the internet in this file — it only reads
from data/cleaned/ and writes to data/output/.

Run this file directly:
    python calculate.py

Or it will be called automatically by run_pipeline.py
"""

import os
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR  = os.path.join(BASE_DIR, "data", "cleaned")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "output")

# RBI 91-day T-Bill rate — update this periodically
# Current rate as of May 2026: ~7.1%
RISK_FREE_RATE_ANNUAL = 0.071

# Number of trading days in a year (used to annualise daily figures)
TRADING_DAYS = 252

# Minimum number of NAV data points needed to calculate a metric
# 252 = 1 year, 756 = 3 years, 1260 = 5 years
MIN_DAYS_1Y = 240
MIN_DAYS_3Y = 700
MIN_DAYS_5Y = 1200

# Maps each fund sub_category to the most appropriate benchmark
# from benchmark_data_clean.csv
CATEGORY_BENCHMARK_MAP = {
    # Equity
    "Large Cap Fund":                       "Nifty 50",
    "Large & Mid Cap Fund":                 "Nifty 500",
    "Mid Cap Fund":                         "Nifty Midcap 150",
    "Small Cap Fund":                       "Nifty Smallcap 250",
    "Multi Cap Fund":                       "Nifty 500",
    "Flexi Cap Fund":                       "Nifty 500",
    "ELSS":                                 "Nifty 500",
    "Focused Fund":                         "Nifty 500",
    "Dividend Yield Fund":                  "Nifty 50",
    "Value Fund":                           "Nifty 500",
    "Value Fund/Contra Fund":               "Nifty 500",
    "Contra Fund":                          "Nifty 500",
    "Sectoral / Thematic Fund":             "Nifty 500",
    "Sectoral/Thematic Funds":              "Nifty 500",
    # Hybrid
    "Aggressive Hybrid Fund":               "Nifty 50",
    "Balanced Hybrid Fund":                 "Nifty 50",
    "Conservative Hybrid Fund":             "India 10Y Bond",
    "Dynamic Asset Allocation":             "Nifty 50",
    "Balanced Advantage Fund":              "Nifty 50",
    "Multi Asset Allocation":               "Nifty 50",
    "Multi Asset Allocation Fund":          "Nifty 50",
    "Arbitrage Fund":                       "Nifty 50",
    "Equity Savings Fund":                  "Nifty 50",
    # Index / ETF
    "Index Fund - Nifty 50":               "Nifty 50",
    "Index Fund - Nifty Next 50":          "Nifty Next 50",
    "Index Fund - Nifty Midcap":           "Nifty Midcap 150",
    "Index Fund - Sensex":                 "BSE Sensex",
    "Index Funds":                         "Nifty 50",
    # Debt
    "Overnight Fund":                       "India 10Y Bond",
    "Liquid Fund":                          "India 10Y Bond",
    "Ultra Short Duration Fund":            "India 10Y Bond",
    "Low Duration Fund":                    "India 10Y Bond",
    "Money Market Fund":                    "India 10Y Bond",
    "Short Duration Fund":                  "India 10Y Bond",
    "Medium Duration Fund":                 "India 10Y Bond",
    "Medium to Long Duration Fund":         "India 10Y Bond",
    "Long Duration Fund":                   "India 10Y Bond",
    "Dynamic Bond Fund":                    "India 10Y Bond",
    "Corporate Bond Fund":                  "India 10Y Bond",
    "Credit Risk Fund":                     "India 10Y Bond",
    "Banking & PSU Fund":                   "India 10Y Bond",
    "Banking and PSU Fund":                 "India 10Y Bond",
    "Gilt Fund":                            "India 10Y Bond",
    "Gilt Fund with 10 year constant duration": "India 10Y Bond",
    "Floater Fund":                         "India 10Y Bond",
    # Solution Oriented
    "Retirement Fund":                      "Nifty 50",
    "Children's Fund":                      "Nifty 50",
    "Childrens Fund":                       "Nifty 50",
}

DEFAULT_BENCHMARK = "Nifty 50"


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output folder ready: {OUTPUT_DIR}/")


def load_clean_files():
    """
    Loads all clean CSV files into DataFrames.
    Returns a dictionary keyed by a short name for each file.
    """
    print("\n[Loading clean files...]")

    files = {
        "nav_history":       "nav_history_clean.csv",
        "nav_snapshots":     "nav_snapshots_clean.csv",
        "scheme_metadata":   "scheme_metadata_clean.csv",
        "scheme_profiles":   "scheme_profiles_clean.csv",
        "benchmarks":        "benchmark_data_clean.csv",
        "category_ref":      "category_reference_clean.csv",
        "aum_monthly":       "aum_amfi_monthly_clean.csv",
        "aum_and_ter":       "aum_and_ter_clean.csv",
    }

    loaded = {}
    for key, filename in files.items():
        path = os.path.join(CLEAN_DIR, filename)
        if not os.path.exists(path):
            print(f"  ✗ Not found: {filename} — skipping")
            loaded[key] = pd.DataFrame()
            continue
        df = pd.read_csv(path)
        # Parse date columns automatically
        for col in df.columns:
            if "date" in col.lower():
                df[col] = pd.to_datetime(df[col], errors="coerce")
        loaded[key] = df
        print(f"  ✓ {filename:<40} {df.shape}")

    return loaded


# ─────────────────────────────────────────────────────────────────────────────
# CORE METRICS — calculated from the full NAV series
# ─────────────────────────────────────────────────────────────────────────────

def calc_cagr(nav_series, years):
    """
    Compounded Annual Growth Rate over a given number of years.

    Formula: (End NAV / Start NAV) ^ (1 / years) - 1

    Args:
        nav_series : pandas Series of NAV values, sorted oldest first
        years      : lookback period in years (1, 3, or 5)

    Returns:
        CAGR as a percentage (e.g. 14.5 means 14.5%), or None if
        insufficient history exists.
    """
    days_needed = int(years * TRADING_DAYS)
    if len(nav_series) < days_needed:
        return None

    end_nav   = nav_series.iloc[-1]
    start_nav = nav_series.iloc[-days_needed]

    if start_nav <= 0:
        return None

    cagr = ((end_nav / start_nav) ** (1 / years) - 1) * 100
    return round(cagr, 4)


def calc_volatility(daily_returns):
    """
    Annualised standard deviation of daily returns.
    Measures the total risk (both upside and downside swings).

    Returns: Volatility as a percentage.
    """
    if len(daily_returns) < MIN_DAYS_1Y:
        return None
    vol = daily_returns.std() * np.sqrt(TRADING_DAYS) * 100
    return round(vol, 4)


def calc_sharpe_ratio(daily_returns):
    """
    Sharpe Ratio: (Annualised Return - Risk-Free Rate) / Annualised Volatility

    Measures return earned per unit of TOTAL risk.
    Above 1.0 is considered good. Above 2.0 is excellent.

    Returns: Sharpe Ratio (dimensionless), or None.
    """
    if len(daily_returns) < MIN_DAYS_1Y:
        return None

    annual_return = daily_returns.mean() * TRADING_DAYS
    annual_vol    = daily_returns.std()  * np.sqrt(TRADING_DAYS)

    if annual_vol == 0:
        return None

    sharpe = (annual_return - RISK_FREE_RATE_ANNUAL) / annual_vol
    return round(sharpe, 4)


def calc_sortino_ratio(daily_returns):
    """
    Sortino Ratio: (Annualised Return - Risk-Free Rate) / Downside Deviation

    Like Sharpe but only penalises DOWNSIDE volatility.
    More appropriate for equity funds where upside swings are desirable.

    Returns: Sortino Ratio (dimensionless), or None.
    """
    if len(daily_returns) < MIN_DAYS_1Y:
        return None

    annual_return   = daily_returns.mean() * TRADING_DAYS
    downside_returns = daily_returns[daily_returns < 0]

    if len(downside_returns) == 0:
        return None

    downside_dev = downside_returns.std() * np.sqrt(TRADING_DAYS)

    if downside_dev == 0:
        return None

    sortino = (annual_return - RISK_FREE_RATE_ANNUAL) / downside_dev
    return round(sortino, 4)


def calc_max_drawdown(nav_series):
    """
    Maximum Drawdown: the worst peak-to-trough decline in NAV.

    Formula: min((NAV - Rolling Peak) / Rolling Peak)

    Example: A fund whose NAV fell from 100 to 60 has a max drawdown of -40%.
    This is always a negative number. Closer to 0 is better.

    Returns: Max drawdown as a percentage (e.g. -32.5 means -32.5%).
    """
    if len(nav_series) < 10:
        return None

    rolling_peak = nav_series.cummax()
    drawdown     = (nav_series - rolling_peak) / rolling_peak
    return round(drawdown.min() * 100, 4)


def calc_beta_alpha(fund_daily_returns, benchmark_daily_returns):
    """
    Beta: how much the fund moves relative to its benchmark.
        Beta = 1.0  → moves exactly with the market
        Beta > 1.0  → more volatile than the market (aggressive)
        Beta < 1.0  → less volatile than the market (defensive)

    Alpha: excess return above what Beta alone would predict.
        Positive alpha → fund manager is adding value
        Negative alpha → fund manager is destroying value

    Returns: (beta, alpha_pct) tuple, or (None, None).
    """
    # Align both series on the same dates
    aligned = pd.concat([fund_daily_returns, benchmark_daily_returns], axis=1, sort=False).dropna()
    aligned.columns = ["fund", "bench"]

    if len(aligned) < MIN_DAYS_1Y:
        return None, None

    cov_matrix = np.cov(aligned["fund"], aligned["bench"])
    bench_var  = cov_matrix[1][1]

    if bench_var == 0:
        return None, None

    beta  = cov_matrix[0][1] / bench_var
    # Annualise alpha: Jensen's Alpha = Rp - [Rf + Beta * (Rm - Rf)]
    rp    = aligned["fund"].mean()  * TRADING_DAYS          # Fund annual return
    rm    = aligned["bench"].mean() * TRADING_DAYS          # Benchmark annual return
    alpha = (rp - (RISK_FREE_RATE_ANNUAL + beta * (rm - RISK_FREE_RATE_ANNUAL))) * 100

    return round(beta, 4), round(alpha, 4)


def calc_tracking_error(fund_daily_returns, benchmark_daily_returns):
    """
    Tracking Error: standard deviation of (fund return - benchmark return).

    Primarily used for index funds to measure how closely they replicate
    their benchmark. Lower is better for passive funds.

    Returns: Annualised tracking error as a percentage.
    """
    aligned = pd.concat([fund_daily_returns, benchmark_daily_returns], axis=1, sort=False).dropna()
    aligned.columns = ["fund", "bench"]

    if len(aligned) < MIN_DAYS_1Y:
        return None

    diff = aligned["fund"] - aligned["bench"]
    te   = diff.std() * np.sqrt(TRADING_DAYS) * 100
    return round(te, 4)


def calc_calmar_ratio(cagr_3y, max_drawdown):
    """
    Calmar Ratio: CAGR / |Max Drawdown|

    Measures how much return the fund generates per unit of drawdown risk.
    Higher is better. Above 1.0 is generally good.

    Returns: Calmar ratio (dimensionless), or None.
    """
    if cagr_3y is None or max_drawdown is None or max_drawdown == 0:
        return None
    calmar = cagr_3y / abs(max_drawdown)
    return round(calmar, 4)


def calc_return_per_cost(cagr_3y, expense_ratio_pct):
    """
    Return Per Cost (Efficiency Score): How much CAGR the investor gets per 1% of expense paid.

    Formula: cagr_3y / expense_ratio_pct

    Returns: Return per cost score (dimensionless), or None.
    """
    if cagr_3y is None or expense_ratio_pct is None or expense_ratio_pct <= 0:
        return None
    return round(cagr_3y / expense_ratio_pct, 4)


def calc_true_net_return(cagr_3y, expense_ratio_pct):
    """
    True Net Return: What the investor actually keeps after costs.

    Formula: cagr_3y - expense_ratio_pct

    Returns: Net return percentage, or None.
    """
    if cagr_3y is None or expense_ratio_pct is None:
        return None
    return round(cagr_3y - expense_ratio_pct, 4)


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT RETURNS — fast period returns from nav_snapshots_clean.csv
# These complement the full NAV series calculations above.
# ─────────────────────────────────────────────────────────────────────────────

def calc_snapshot_returns(snapshots_df):
    """
    Calculates period returns from the pre-built NAV snapshot table.
    Much faster than recalculating from full NAV history.

    Snapshot columns used:
        nav_today, nav_1m_ago, nav_3m_ago, nav_6m_ago,
        nav_1y_ago, nav_3y_ago, nav_5y_ago

    Returns a DataFrame with one row per fund and these new columns:
        return_1m_pct    : 1-month absolute return
        return_3m_pct    : 3-month absolute return
        return_6m_pct    : 6-month absolute return
        return_1y_pct    : 1-year absolute return
        cagr_3y_snap     : 3-year CAGR from snapshots (cross-check)
        cagr_5y_snap     : 5-year CAGR from snapshots (cross-check)
    """
    df = snapshots_df.copy()

    def pct_change(today, past):
        if pd.isna(today) or pd.isna(past) or past == 0:
            return None
        return round((today - past) / past * 100, 4)

    def cagr_snap(today, past, years):
        if pd.isna(today) or pd.isna(past) or past == 0:
            return None
        return round(((today / past) ** (1 / years) - 1) * 100, 4)

    df["return_1m_pct"]  = df.apply(lambda r: pct_change(r["nav_today"], r["nav_1m_ago"]),  axis=1)
    df["return_3m_pct"]  = df.apply(lambda r: pct_change(r["nav_today"], r["nav_3m_ago"]),  axis=1)
    df["return_6m_pct"]  = df.apply(lambda r: pct_change(r["nav_today"], r["nav_6m_ago"]),  axis=1)
    df["return_1y_pct"]  = df.apply(lambda r: pct_change(r["nav_today"], r["nav_1y_ago"]),  axis=1)
    df["cagr_3y_snap"]   = df.apply(lambda r: cagr_snap(r["nav_today"], r["nav_3y_ago"], 3), axis=1)
    df["cagr_5y_snap"]   = df.apply(lambda r: cagr_snap(r["nav_today"], r["nav_5y_ago"], 5), axis=1)

    return df[["scheme_code", "return_1m_pct", "return_3m_pct",
               "return_6m_pct", "return_1y_pct", "cagr_3y_snap", "cagr_5y_snap"]]


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE SCORE — ranks funds within their category
# ─────────────────────────────────────────────────────────────────────────────

def calc_composite_score(df):
    """
    Builds a single 0–100 composite score for each fund.
    Used to produce the "Top Performers" view in Power BI.

    Weights (must sum to 1.0):
        35% Sharpe Ratio      — risk-adjusted return quality
        30% CAGR 3Y           — medium-term return
        20% Max Drawdown      — downside protection (inverted: lower loss = higher score)
        15% Volatility        — stability (inverted: lower = higher score)

    Scoring method: Min-Max normalisation per metric, scaled 0–100.
    All normalisations are done WITHIN the full fund universe so scores
    are relative to peers, not absolute.
    """

    def minmax(series, invert=False):
        """Normalise a series to 0–100. Invert=True when lower raw value = better score."""
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series([50.0] * len(series), index=series.index)
        norm = (series - mn) / (mx - mn) * 100
        return (100 - norm) if invert else norm

    metrics = df[["scheme_code", "sharpe_ratio", "cagr_3y", "max_drawdown_pct", "volatility_pct"]].copy()
    metrics = metrics.dropna(subset=["sharpe_ratio", "cagr_3y", "max_drawdown_pct", "volatility_pct"])

    metrics["sharpe_norm"]    = minmax(metrics["sharpe_ratio"],    invert=False)
    metrics["cagr_norm"]      = minmax(metrics["cagr_3y"],         invert=False)
    metrics["drawdown_norm"]  = minmax(metrics["max_drawdown_pct"],invert=True)  # less negative = better
    metrics["vol_norm"]       = minmax(metrics["volatility_pct"],  invert=True)  # lower = better

    metrics["composite_score"] = (
        0.35 * metrics["sharpe_norm"]   +
        0.30 * metrics["cagr_norm"]     +
        0.20 * metrics["drawdown_norm"] +
        0.15 * metrics["vol_norm"]
    ).round(2)

    # Rank within entire universe (1 = best)
    metrics["universe_rank"] = metrics["composite_score"].rank(ascending=False, method="min").astype(int)

    return df.merge(
        metrics[["scheme_code", "composite_score", "universe_rank"]],
        on="scheme_code", how="left"
    )


# ─────────────────────────────────────────────────────────────────────────────
# ROLLING RETURNS — for the NAV trend line chart in Power BI
# ─────────────────────────────────────────────────────────────────────────────

def calc_rolling_returns(nav_history_df, window=252):
    """
    Calculates rolling 1-year returns for every fund over its full NAV history.
    This produces a time-series table used in Power BI line charts to show
    how consistent each fund's returns have been over time.

    Args:
        nav_history_df : the full nav_history_clean DataFrame
        window         : rolling window in trading days (252 = 1 year)

    Returns a long-format DataFrame:
        date | scheme_code | fund_name | rolling_1y_return_pct

    Saved to: data/output/rolling_returns.csv
    """
    print("\n  Calculating rolling 1Y returns...")

    results = []

    for (code, name), group in nav_history_df.groupby(["scheme_code", "fund_name"]):
        group = group.sort_values("date").copy()
        group["rolling_1y_return_pct"] = (
            group["nav"].pct_change(periods=window) * 100
        ).round(4)
        group["scheme_code"] = code
        group["fund_name"]   = name
        results.append(group[["date", "scheme_code", "fund_name", "rolling_1y_return_pct"]])

    combined = pd.concat(results, ignore_index=True).dropna(subset=["rolling_1y_return_pct"])

    out_path = os.path.join(OUTPUT_DIR, "rolling_returns.csv")
    combined.to_csv(out_path, index=False)
    print(f"  Saved {len(combined):,} rows → {out_path}")
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CALCULATION RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_all_calculations():
    """
    Master function. Runs every metric calculation for every fund and
    assembles the final fund_metrics.csv fact table.

    Output columns (fund_metrics.csv):
    ─────────────────────────────────
    Identity:
        scheme_code, fund_name, fund_house, broad_category, sub_category
        scheme_type, full_category, benchmark_used

    Return metrics:
        cagr_1y, cagr_3y, cagr_5y        (from full NAV series)
        cagr_3y_snap, cagr_5y_snap       (cross-check from snapshots)
        return_1m_pct, return_3m_pct,
        return_6m_pct, return_1y_pct     (from snapshots)

    Risk metrics:
        volatility_pct                   (annualised std dev of daily returns)
        max_drawdown_pct                 (worst peak-to-trough decline)
        beta                             (vs category benchmark)
        alpha_pct                        (annualised Jensen's alpha)
        tracking_error_pct              (vs category benchmark)

    Risk-adjusted return metrics:
        sharpe_ratio
        sortino_ratio
        calmar_ratio

    Composite score:
        composite_score                  (0–100, weighted blend)
        universe_rank                    (1 = best in full universe)

    Profile fields (merged from scheme_profiles):
        inception_date, fund_age_years
        latest_nav, nav_52w_high, nav_52w_low, nav_52w_change_pct
        total_nav_days
    """

    print("=" * 60)
    print("  MUTUAL FUND DASHBOARD — METRICS CALCULATION")
    print("=" * 60)

    ensure_output_dir()
    data = load_clean_files()

    nav_df       = data["nav_history"]
    snap_df      = data["nav_snapshots"]
    meta_df      = data["scheme_metadata"]
    profiles_df  = data["scheme_profiles"]
    bench_df     = data["benchmarks"]
    aum_ter_df   = data["aum_and_ter"]

    # Prepare benchmark data — index by date for fast lookup
    bench_df = bench_df.set_index("date")

    # Get list of funds to process
    funds = nav_df[["scheme_code", "fund_name"]].drop_duplicates()
    print(f"\n  Funds to process: {len(funds)}")

    # ── Step 1: Calculate per-fund metrics from full NAV series ──────────
    print("\n[Step 1] Calculating core metrics from NAV history...")

    all_metrics = []

    for _, row in funds.iterrows():
        code = row["scheme_code"]
        name = row["fund_name"]

        # Get this fund's NAV history, sorted oldest → newest
        fund_nav = (
            nav_df[nav_df["scheme_code"] == code]
            .sort_values("date")
            .set_index("date")["nav"]
        )

        # Daily returns (percentage change day-over-day)
        daily_returns = fund_nav.pct_change().dropna()

        # Look up which sub_category this fund belongs to
        meta_row   = meta_df[meta_df["scheme_code"] == code]
        sub_cat    = meta_row["sub_category"].iloc[0] if not meta_row.empty else ""
        bench_name = CATEGORY_BENCHMARK_MAP.get(sub_cat, DEFAULT_BENCHMARK)

        # Get benchmark daily returns aligned to this fund's date range
        bench_series = bench_df[bench_name].dropna() if bench_name in bench_df.columns else pd.Series()
        bench_returns = bench_series.pct_change().dropna()

        # ── Calculate all metrics ─────────────────────────────────────────
        cagr_1y = calc_cagr(fund_nav, 1)
        cagr_3y = calc_cagr(fund_nav, 3)
        cagr_5y = calc_cagr(fund_nav, 5)
        vol     = calc_volatility(daily_returns)
        sharpe  = calc_sharpe_ratio(daily_returns)
        sortino = calc_sortino_ratio(daily_returns)
        mdd     = calc_max_drawdown(fund_nav)
        calmar  = calc_calmar_ratio(cagr_3y, mdd)
        beta, alpha = calc_beta_alpha(daily_returns, bench_returns)
        te      = calc_tracking_error(daily_returns, bench_returns)

        # Lookup expense ratio
        if aum_ter_df is not None and not aum_ter_df.empty and "scheme_code" in aum_ter_df.columns:
            aum_ter_row = aum_ter_df[aum_ter_df["scheme_code"] == code]
            expense_ratio_pct = aum_ter_row["expense_ratio_pct"].iloc[0] if not aum_ter_row.empty else None
            if pd.isna(expense_ratio_pct):
                expense_ratio_pct = None
        else:
            expense_ratio_pct = None

        return_per_cost = calc_return_per_cost(cagr_3y, expense_ratio_pct)
        true_net_return = calc_true_net_return(cagr_3y, expense_ratio_pct)

        all_metrics.append({
            "scheme_code":          code,
            "fund_name":            name,
            "benchmark_used":       bench_name,
            "cagr_1y":              cagr_1y,
            "cagr_3y":              cagr_3y,
            "cagr_5y":              cagr_5y,
            "volatility_pct":       vol,
            "sharpe_ratio":         sharpe,
            "sortino_ratio":        sortino,
            "max_drawdown_pct":     mdd,
            "calmar_ratio":         calmar,
            "beta":                 beta,
            "alpha_pct":            alpha,
            "tracking_error_pct":   te,
            "expense_ratio_pct":    expense_ratio_pct,
            "return_per_cost":      return_per_cost,
            "true_net_return":      true_net_return,
        })

        print(f"  ✓ {name:<50} Sharpe: {sharpe}  CAGR 3Y: {cagr_3y}%")

    metrics_df = pd.DataFrame(all_metrics)

    # ── Step 2: Add snapshot-based returns ───────────────────────────────
    print("\n[Step 2] Calculating snapshot period returns...")
    snap_returns = calc_snapshot_returns(snap_df)
    metrics_df   = metrics_df.merge(snap_returns, on="scheme_code", how="left")

    # ── Step 3: Merge scheme metadata ────────────────────────────────────
    print("\n[Step 3] Merging scheme metadata...")
    meta_cols = ["scheme_code", "fund_house", "broad_category",
                 "sub_category", "scheme_type", "full_category"]
    meta_slim = meta_df[[c for c in meta_cols if c in meta_df.columns]]
    metrics_df = metrics_df.merge(meta_slim, on="scheme_code", how="left")

    # ── Step 4: Merge scheme profiles ────────────────────────────────────
    print("\n[Step 4] Merging scheme profiles...")
    profile_cols = ["scheme_code", "inception_date", "fund_age_years",
                    "latest_nav", "nav_52w_high", "nav_52w_low",
                    "nav_52w_change_pct", "total_nav_days"]
    profile_slim = profiles_df[[c for c in profile_cols if c in profiles_df.columns]]
    metrics_df   = metrics_df.merge(profile_slim, on="scheme_code", how="left")

    # ── Step 5: Add composite score and universe rank ─────────────────────
    print("\n[Step 5] Calculating composite scores and universe rank...")
    metrics_df = calc_composite_score(metrics_df)

    # ── Step 6: Add category rank (rank within sub_category peers) ────────
    print("\n[Step 6] Calculating within-category peer rank...")
    metrics_df["category_rank"] = (
        metrics_df.groupby("sub_category")["composite_score"]
        .rank(ascending=False, method="min")
        .astype("Int64")      # Int64 supports NaN, int does not
    )

    # ── Step 7: Rolling returns (separate file for line charts) ──────────
    print("\n[Step 7] Generating rolling returns table...")
    calc_rolling_returns(nav_df)

    # ── Step 8: Column ordering and final save ───────────────────────────
    print("\n[Step 8] Saving fund_metrics.csv...")

    # Define clean column order for Power BI
    col_order = [
        # Identity
        "scheme_code", "fund_name", "fund_house",
        "broad_category", "sub_category", "full_category",
        "scheme_type", "benchmark_used",
        # Profile
        "inception_date", "fund_age_years", "total_nav_days",
        "latest_nav", "nav_52w_high", "nav_52w_low", "nav_52w_change_pct",
        # Returns (from NAV series)
        "cagr_1y", "cagr_3y", "cagr_5y",
        # Returns (from snapshots)
        "return_1m_pct", "return_3m_pct", "return_6m_pct",
        "return_1y_pct", "cagr_3y_snap", "cagr_5y_snap",
        # Risk
        "volatility_pct", "max_drawdown_pct", "beta", "tracking_error_pct",
        # Risk-adjusted
        "sharpe_ratio", "sortino_ratio", "calmar_ratio", "alpha_pct",
        "expense_ratio_pct", "return_per_cost", "true_net_return",
        # Composite
        "composite_score", "universe_rank", "category_rank",
    ]

    # Keep only columns that exist (guards against optional fields being absent)
    col_order  = [c for c in col_order if c in metrics_df.columns]
    metrics_df = metrics_df[col_order]

    out_path = os.path.join(OUTPUT_DIR, "fund_metrics.csv")
    metrics_df.to_csv(out_path, index=False)

    # ── Summary report ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  CALCULATION COMPLETE")
    print("=" * 60)
    print(f"\n  Funds processed      : {len(metrics_df)}")
    print(f"  Metrics per fund     : {len(metrics_df.columns)}")
    print(f"  Sharpe range         : {metrics_df['sharpe_ratio'].min():.3f} → {metrics_df['sharpe_ratio'].max():.3f}")
    print(f"  CAGR 3Y range        : {metrics_df['cagr_3y'].min():.2f}% → {metrics_df['cagr_3y'].max():.2f}%")
    print(f"  Max Drawdown range   : {metrics_df['max_drawdown_pct'].min():.2f}% → {metrics_df['max_drawdown_pct'].max():.2f}%")
    print(f"\n  Output files:")
    print(f"    → data/output/fund_metrics.csv")
    print(f"    → data/output/rolling_returns.csv")
    print("=" * 60)

    return metrics_df


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run_all_calculations()
    print(f"\nPreview of fund_metrics.csv:")
    print(result[["fund_name", "cagr_3y", "sharpe_ratio", "max_drawdown_pct",
                  "expense_ratio_pct", "return_per_cost", "true_net_return",
                  "composite_score", "universe_rank"]].to_string())