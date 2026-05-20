"""
run_pipeline.py — Master Pipeline Runner
=========================================
Mutual Fund Analysis Dashboard — Stage Controller
---------------------------------------------------
This is the single script you run to refresh the entire dashboard data.
It calls collect.py → clean.py → calculate.py in order, handles errors
gracefully, writes a log file for every run, and sends a summary report
to the terminal so you always know what happened.

Usage:
    python run_pipeline.py                 ← full pipeline
    python run_pipeline.py --stage collect ← run one stage only
    python run_pipeline.py --stage clean
    python run_pipeline.py --stage calculate
    python run_pipeline.py --dry-run       ← check setup without running

This file is also what Windows Task Scheduler calls on its daily schedule.
"""

import os
import sys
import time
import logging
import argparse
import traceback
import subprocess
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Anchor all paths to where this script lives — same pattern as calculate.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR  = os.path.join(BASE_DIR, "logs")

# The three pipeline stages in execution order
STAGES = {
    "collect":   os.path.join(BASE_DIR, "collect.py"),
    "clean":     os.path.join(BASE_DIR, "clean.py"),
    "calculate": os.path.join(BASE_DIR, "calculate.py"),
}

# Output files each stage is expected to produce
# Pipeline checks these exist after each stage runs
EXPECTED_OUTPUTS = {
    "collect": [
        os.path.join(BASE_DIR, "data", "raw", "all_schemes.csv"),
        os.path.join(BASE_DIR, "data", "raw", "nav_history_raw.csv"),
        os.path.join(BASE_DIR, "data", "raw", "scheme_metadata.csv"),
        os.path.join(BASE_DIR, "data", "raw", "benchmark_data.csv"),
    ],
    "clean": [
        os.path.join(BASE_DIR, "data", "cleaned", "nav_history_clean.csv"),
        os.path.join(BASE_DIR, "data", "cleaned", "scheme_metadata_clean.csv"),
        os.path.join(BASE_DIR, "data", "cleaned", "benchmark_data_clean.csv"),
    ],
    "calculate": [
        os.path.join(BASE_DIR, "data", "output", "fund_metrics.csv"),
        os.path.join(BASE_DIR, "data", "output", "rolling_returns.csv"),
    ],
}

# How many times to retry a failed stage before giving up
MAX_RETRIES = 2

# Seconds to wait between retries
RETRY_DELAY = 30


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP
# Writes to both the terminal (so you can watch live) and a log file
# (so you can check what happened after a scheduled overnight run)
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging():
    """
    Creates a log file named with today's date and timestamp.
    Every run gets its own file — old logs are never overwritten.

    Log files land in: logs/pipeline_YYYYMMDD_HHMMSS.log
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file    = os.path.join(LOG_DIR, f"pipeline_{timestamp}.log")

    # Root logger — captures everything
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Format: [2026-05-20 14:32:01] INFO  — message
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-8s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler 1: write to log file (DEBUG level — captures everything)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    # Handler 2: print to terminal (INFO level — only important messages)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger, log_file


# ─────────────────────────────────────────────────────────────────────────────
# PREFLIGHT CHECKS
# Verifies everything is in place before the pipeline starts running.
# Catches common mistakes early rather than letting them fail halfway through.
# ─────────────────────────────────────────────────────────────────────────────

def run_preflight_checks(logger):
    """
    Checks that all required files and folders exist before running.

    Checks performed:
        ✓ All three stage scripts (collect.py, clean.py, calculate.py) exist
        ✓ data/raw/, data/cleaned/, data/output/ directories exist (creates if not)
        ✓ Python environment has the required packages installed
        ✓ Internet connectivity (pings mfapi.in)

    Returns True if all checks pass, False if any critical check fails.
    """
    logger.info("Running preflight checks...")
    all_passed = True

    # ── Check 1: Stage scripts exist ─────────────────────────────────────
    for stage, path in STAGES.items():
        if os.path.exists(path):
            logger.info(f"  [OK] {stage}.py found")
        else:
            logger.error(f"  [FAIL] {stage}.py NOT FOUND at: {path}")
            all_passed = False

    # ── Check 2: Create required directories ─────────────────────────────
    required_dirs = [
        os.path.join(BASE_DIR, "data", "raw"),
        os.path.join(BASE_DIR, "data", "cleaned"),
        os.path.join(BASE_DIR, "data", "output"),
        LOG_DIR,
    ]
    for d in required_dirs:
        os.makedirs(d, exist_ok=True)
        logger.info(f"  [OK] Directory ready: {d}")

    # ── Check 3: Required packages installed ─────────────────────────────
    required_packages = {
        "requests":  "requests",
        "pandas":    "pandas",
        "numpy":     "numpy",
        "yfinance":  "yfinance",
        "openpyxl":  "openpyxl",
        "xlrd":      "xlrd",
    }

    missing_packages = []
    for import_name, pip_name in required_packages.items():
        try:
            __import__(import_name)
            logger.info(f"  [OK] Package available: {import_name}")
        except ImportError:
            logger.error(f"  [FAIL] Package missing: {pip_name}  ->  pip install {pip_name}")
            missing_packages.append(pip_name)

    if missing_packages:
        logger.error(f"  Install missing packages: pip install {' '.join(missing_packages)}")
        all_passed = False

    # ── Check 4: Internet connectivity ───────────────────────────────────
    try:
        import requests
        resp = requests.get("https://api.mfapi.in/mf", timeout=10)
        if resp.status_code == 200:
            logger.info("  [OK] Internet connectivity confirmed (mfapi.in reachable)")
        else:
            logger.warning(f"  [WARN] mfapi.in returned status {resp.status_code} - data fetch may be incomplete")
    except Exception as e:
        logger.warning(f"  [WARN] Cannot reach mfapi.in: {e}")
        logger.warning("    Pipeline will attempt to run but data collection may fail")

    if all_passed:
        logger.info("Preflight checks passed [OK]")
    else:
        logger.error("Preflight checks FAILED - fix the errors above before running")

    return all_passed


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT VERIFICATION
# After each stage runs, confirm it actually produced the expected files.
# A stage can exit with code 0 (success) but still fail to write output.
# ─────────────────────────────────────────────────────────────────────────────

def verify_stage_outputs(stage_name, logger):
    """
    Checks that a stage produced all its expected output files.
    Also logs the file size so you can spot suspiciously small files
    (e.g. a 1KB nav_history_raw.csv means something went wrong in collect).

    Returns True if all expected files exist and are non-empty.
    """
    expected = EXPECTED_OUTPUTS.get(stage_name, [])
    if not expected:
        return True

    all_present = True
    logger.info(f"  Verifying {stage_name} outputs...")

    for filepath in expected:
        if os.path.exists(filepath):
            size_kb = os.path.getsize(filepath) / 1024
            if size_kb < 0.1:
                logger.warning(f"    ⚠ {os.path.basename(filepath)} exists but is nearly empty ({size_kb:.1f} KB)")
            else:
                logger.info(f"    [OK] {os.path.basename(filepath)} ({size_kb:.1f} KB)")
        else:
            logger.error(f"    [FAIL] Expected output missing: {os.path.basename(filepath)}")
            all_present = False

    return all_present


# ─────────────────────────────────────────────────────────────────────────────
# STAGE RUNNER
# Runs a single .py script as a subprocess, captures its output into the
# log file, and retries automatically if it fails.
# ─────────────────────────────────────────────────────────────────────────────

def run_stage(stage_name, logger, retries=MAX_RETRIES):
    """
    Executes one pipeline stage script and streams its output to the log.

    Args:
        stage_name : "collect", "clean", or "calculate"
        logger     : the shared logger instance
        retries    : how many times to retry on failure

    Returns:
        (success: bool, duration_seconds: float)
    """
    script_path = STAGES[stage_name]
    python_exe  = sys.executable     # Uses the same Python/conda env as this script

    logger.info(f"{'-' * 50}")
    logger.info(f"STARTING: {stage_name.upper()}")
    logger.info(f"Script  : {script_path}")
    logger.info(f"Python  : {python_exe}")
    logger.info(f"{'-' * 50}")

    start_time = time.time()

    for attempt in range(1, retries + 2):    # +2 because range is exclusive and attempt 1 = first try
        if attempt > 1:
            logger.warning(f"Retry {attempt - 1}/{retries} for {stage_name} "
                           f"(waiting {RETRY_DELAY}s)...")
            time.sleep(RETRY_DELAY)

        try:
            # Force UTF-8 encoding for subprocess standard streams to prevent CP1252/Unicode crashes on Windows
            sub_env = dict(os.environ)
            sub_env["PYTHONIOENCODING"] = "utf-8"

            # Run the script as a subprocess
            # stdout=PIPE captures all print() output from the script
            # stderr=STDOUT merges error output into the same stream
            process = subprocess.Popen(
                [python_exe, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,            # Line-buffered so output appears in real time
                cwd=BASE_DIR,         # Run from project root — important for relative paths
                env=sub_env,
            )

            # Stream the script's output line by line into the log
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    logger.debug(f"  [{stage_name}] {line}")
                    # Also print to terminal so you can watch progress live
                    print(f"  {line}")

            process.wait()
            duration = time.time() - start_time

            if process.returncode == 0:
                logger.info(f"COMPLETED: {stage_name.upper()} in {duration:.1f}s [OK]")

                # Verify outputs exist even on a clean exit code
                outputs_ok = verify_stage_outputs(stage_name, logger)
                if not outputs_ok:
                    logger.error(f"{stage_name} exited cleanly but output files are missing")
                    if attempt <= retries:
                        continue      # Retry
                    return False, duration

                return True, duration

            else:
                logger.error(f"FAILED: {stage_name.upper()} exited with code {process.returncode} "
                             f"(attempt {attempt})")
                if attempt > retries:
                    logger.error(f"All {retries} retries exhausted for {stage_name}. Stopping pipeline.")
                    return False, duration

        except FileNotFoundError:
            logger.error(f"Cannot find script: {script_path}")
            return False, 0

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Unexpected error in {stage_name}: {e}")
            logger.debug(traceback.format_exc())
            if attempt > retries:
                return False, duration

    return False, time.time() - start_time


# ─────────────────────────────────────────────────────────────────────────────
# RUN SUMMARY
# Prints a clean summary table at the end of every run so you can see
# at a glance what happened — especially useful for scheduled runs
# where you check the log the next morning.
# ─────────────────────────────────────────────────────────────────────────────

def print_run_summary(results, total_duration, log_file, logger):
    """
    Prints a clean summary of the pipeline run.

    Args:
        results        : list of (stage_name, success, duration) tuples
        total_duration : total wall-clock seconds the pipeline took
        log_file       : path to the log file for this run
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("  PIPELINE RUN SUMMARY")
    logger.info("=" * 60)

    all_passed = True
    for stage_name, success, duration in results:
        status = "PASSED" if success else "FAILED"
        if not success:
            all_passed = False
        logger.info(f"  {stage_name:<12} {status}   ({duration:.1f}s)")

    logger.info("-" * 60)

    minutes = int(total_duration // 60)
    seconds = int(total_duration % 60)
    logger.info(f"  Total time    : {minutes}m {seconds}s")
    logger.info(f"  Finished at   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Log file      : {log_file}")

    if all_passed:
        logger.info("  Status        : ALL STAGES PASSED [OK]")
        logger.info("  Power BI      : Refresh your dataset to load the new data")
    else:
        failed = [r[0] for r in results if not r[1]]
        logger.error(f"  Status        : PIPELINE FAILED at stage(s): {', '.join(failed)}")
        logger.error("  Action needed : Check the log file for the error details")
        logger.error(f"  Log file      : {log_file}")

    logger.info("=" * 60)

    # Write a simple one-line status file that Power BI or Task Scheduler can check
    status_file = os.path.join(BASE_DIR, "last_run_status.txt")
    with open(status_file, "w") as f:
        status_str = "SUCCESS" if all_passed else "FAILED"
        f.write(f"{status_str} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"Duration: {minutes}m {seconds}s\n")
        for stage_name, success, duration in results:
            f.write(f"  {stage_name}: {'OK' if success else 'FAILED'} ({duration:.1f}s)\n")

    logger.info(f"  Status file   : {status_file}")


# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENT PARSER
# Lets you run a single stage from the command line without running all three
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Mutual Fund Dashboard — Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                   Run the full pipeline
  python run_pipeline.py --stage collect   Run collect.py only
  python run_pipeline.py --stage clean     Run clean.py only
  python run_pipeline.py --stage calculate Run calculate.py only
  python run_pipeline.py --dry-run         Check setup without running
        """
    )
    parser.add_argument(
        "--stage",
        choices=["collect", "clean", "calculate"],
        default=None,
        help="Run a single stage instead of the full pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run preflight checks only — does not execute any stage"
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Disable automatic retry on failure (useful for debugging)"
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    args   = parse_args()
    logger, log_file = setup_logging()
    retries = 0 if args.no_retry else MAX_RETRIES

    # ── Header ───────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("  MUTUAL FUND DASHBOARD — PIPELINE RUNNER")
    logger.info(f"  Started : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  Log     : {log_file}")
    if args.stage:
        logger.info(f"  Mode    : Single stage ({args.stage})")
    elif args.dry_run:
        logger.info("  Mode    : Dry run (preflight checks only)")
    else:
        logger.info("  Mode    : Full pipeline (collect → clean → calculate)")
    logger.info("=" * 60)

    # ── Preflight checks ─────────────────────────────────────────────────
    checks_passed = run_preflight_checks(logger)

    if args.dry_run:
        logger.info("Dry run complete. Exiting without running any stages.")
        sys.exit(0 if checks_passed else 1)

    if not checks_passed:
        logger.error("Preflight checks failed. Aborting pipeline.")
        logger.error(f"Fix the issues above and try again. Log: {log_file}")
        sys.exit(1)

    # ── Determine which stages to run ────────────────────────────────────
    if args.stage:
        stages_to_run = [args.stage]
    else:
        stages_to_run = list(STAGES.keys())    # collect → clean → calculate

    # ── Execute stages ───────────────────────────────────────────────────
    pipeline_start = time.time()
    results        = []

    for stage_name in stages_to_run:
        success, duration = run_stage(stage_name, logger, retries=retries)
        results.append((stage_name, success, duration))

        # If a stage fails, stop immediately — later stages depend on earlier ones
        if not success:
            logger.error(f"Pipeline stopped at stage: {stage_name}")
            logger.error("Subsequent stages were not run.")
            # Append skipped stages as not run
            remaining = stages_to_run[stages_to_run.index(stage_name) + 1:]
            for skipped in remaining:
                results.append((skipped, False, 0))
                logger.warning(f"  SKIPPED: {skipped} (dependency failed)")
            break

    # ── Summary ──────────────────────────────────────────────────────────
    total_duration = time.time() - pipeline_start
    print_run_summary(results, total_duration, log_file, logger)

    # Exit with code 1 if any stage failed — Task Scheduler uses this to detect failure
    all_passed = all(r[1] for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()