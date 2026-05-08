"""
Invest Solo -- Coverage Report Script
Fetches a sample of tickers through HybridDataFetcher and prints a per-field
source breakdown, then updates coverage_matrix.md with the results table.

Usage:
    python -m scripts.coverage_report --tickers MC.PA OR.PA AIR.PA SAP.DE ASML.AS AAPL MSFT JPM BRK-B NVDA
    python -m scripts.coverage_report --tickers AAPL MSFT    # quick test
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from backend.app.services.cache_service import CacheService
from backend.app.services.market_data.fmp_fetcher import FMPDataFetcher
from backend.app.services.market_data.hybrid_fetcher import HybridDataFetcher
from backend.app.services.market_data.yfinance_fetcher import YFinanceDataFetcher
from backend.app.config import settings

COVERAGE_MATRIX_PATH = (
    _PROJECT_ROOT
    / "backend"
    / "app"
    / "services"
    / "market_data"
    / "coverage_matrix.md"
)

DEFAULT_TICKERS = [
    "MC.PA", "OR.PA", "AIR.PA", "SAP.DE", "ASML.AS",  # PEA
    "AAPL", "MSFT", "JPM", "BRK-B", "NVDA",            # US
]


def _is_finite(val: Any) -> bool:
    try:
        return math.isfinite(float(val))
    except (TypeError, ValueError):
        return False


def run_coverage(tickers: List[str], bust_cache: bool = False) -> None:
    cache = CacheService()
    fmp_token = os.getenv("FMP_TOKEN", "")
    fmp = FMPDataFetcher(token=fmp_token, cache=cache,
                         enabled=bool(fmp_token))
    yf = YFinanceDataFetcher(cache=cache)
    hybrid = HybridDataFetcher(fmp=fmp, yf=yf, cache=cache)

    from backend.app.services.data_fetcher import SCORING_COLUMNS

    # Columns to display in the coverage table
    display_cols = [
        c for c in SCORING_COLUMNS
        if c not in ("Name", "Sector", "Industry", "Country", "Exchange", "PEA", "PEA_PME")
    ]

    print(f"\n{'='*70}")
    print("Invest Solo -- Hybrid Data Coverage Report")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"FMP enabled: {bool(fmp_token)}")
    print(f"{'='*70}\n")

    all_results: List[Dict[str, Any]] = []

    for ticker in tickers:
        if bust_cache:
            cache.invalidate(f"hybrid:{ticker}")
        print(f"  Fetching {ticker}...")
        try:
            row = hybrid.fetch_single(ticker)
            all_results.append(row)
        except Exception as exc:
            print(f"    ERROR: {exc}")
            all_results.append({"Ticker": ticker, "field_sources": {}, "data_completeness": 0.0})

    # Print per-ticker completeness summary
    print(f"\n{'Ticker':<12} {'Completeness':>13} {'FMP fields':>11} {'yfinance fields':>16} {'missing':>8}")
    print("-" * 65)
    for row in all_results:
        ticker = row.get("Ticker", "?")
        dc = row.get("data_completeness", 0.0)
        sources = row.get("field_sources", {})
        n_fmp = sum(1 for s in sources.values() if s == "fmp")
        n_yf = sum(1 for s in sources.values() if s == "yfinance")
        n_miss = sum(1 for s in sources.values() if s == "missing")
        print(f"{ticker:<12} {dc:>12.1%} {n_fmp:>11} {n_yf:>16} {n_miss:>8}")

    # Build per-field source breakdown table
    print(f"\n\n{'Field':<22}", end="")
    for row in all_results:
        ticker = row.get("Ticker", "?")
        print(f"{ticker:>12}", end="")
    print()
    print("-" * (22 + 12 * len(all_results)))

    for col in display_cols:
        print(f"{col:<22}", end="")
        for row in all_results:
            sources = row.get("field_sources", {})
            src = sources.get(col, "?")
            val = row.get(col)
            if src == "fmp":
                indicator = "F"
            elif src == "yfinance":
                indicator = "Y"
            elif src == "missing":
                indicator = "-"
            else:
                indicator = "?"
            # Show value as well for quick sanity
            try:
                disp = f"{indicator}:{float(val):.2g}" if _is_finite(val) else f"{indicator}:NaN"
            except (TypeError, ValueError):
                disp = f"{indicator}:{val}"
            print(f"{disp:>12}", end="")
        print()

    # Legend
    print("\nLegend: F=FMP, Y=yfinance, -=missing")

    # Dump to coverage_matrix.md
    _update_coverage_matrix(tickers, all_results, display_cols)
    print(f"\nCoverage matrix updated: {COVERAGE_MATRIX_PATH}")


def _update_coverage_matrix(
    tickers: List[str],
    results: List[Dict[str, Any]],
    display_cols: List[str],
) -> None:
    """Append the per-ticker coverage table into coverage_matrix.md."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build markdown table
    header = "| Field | " + " | ".join(tickers) + " |"
    sep = "|---|" + "|".join(["---"] * len(tickers)) + "|"
    rows_md = []
    for col in display_cols:
        cells = []
        for row in results:
            sources = row.get("field_sources", {})
            src = sources.get(col, "?")
            val = row.get(col)
            if src == "fmp":
                indicator = "FMP"
            elif src == "yfinance":
                indicator = "yf"
            else:
                indicator = "-"
            cells.append(indicator)
        rows_md.append("| " + col + " | " + " | ".join(cells) + " |")

    table_md = "\n".join([header, sep] + rows_md)
    report_section = (
        f"\n<!-- COVERAGE_REPORT_LAST_RUN: {now} -->\n\n"
        f"### Per-Ticker Coverage (Last Run: {now})\n\n"
        f"Tickers: {', '.join(tickers)}\n\n"
        f"Legend: `FMP` = supplied by FMP, `yf` = supplied by yfinance, `-` = missing\n\n"
        f"{table_md}\n"
    )

    if not COVERAGE_MATRIX_PATH.exists():
        COVERAGE_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
        COVERAGE_MATRIX_PATH.write_text(report_section, encoding="utf-8")
        return

    content = COVERAGE_MATRIX_PATH.read_text(encoding="utf-8")
    placeholder = "<!-- COVERAGE_REPORT_PLACEHOLDER -->"
    # Remove any previous auto-generated section
    if "<!-- COVERAGE_REPORT_LAST_RUN" in content:
        import re
        content = re.sub(
            r"\n<!-- COVERAGE_REPORT_LAST_RUN.*",
            "",
            content,
            flags=re.DOTALL,
        )
    if placeholder in content:
        content = content.replace(placeholder, placeholder + report_section)
    else:
        content += report_section

    COVERAGE_MATRIX_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run coverage report for HybridDataFetcher"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=DEFAULT_TICKERS,
        help="List of ticker symbols to fetch",
    )
    parser.add_argument(
        "--bust-cache",
        action="store_true",
        help="Invalidate hybrid cache for each ticker before fetching",
    )
    args = parser.parse_args()
    run_coverage(args.tickers, bust_cache=args.bust_cache)


if __name__ == "__main__":
    main()
