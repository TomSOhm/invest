"""
Invest Solo — Main Analysis Pipeline
Runs the full screening, scoring, and report generation.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime

from src.data.sample_universe import get_universe_dataframe
from src.analysis.scoring_engine import score_universe
from src.strategy.screener import (
    screen_pea_value, screen_pea_quality, screen_dividend_income,
    screen_global_best, generate_screening_summary
)


def run_pipeline():
    """Execute the full analysis pipeline."""
    print("=" * 60)
    print("📊 INVEST SOLO — Daily Analysis Pipeline")
    print(f"   Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Load Universe
    print("\n[1/4] Loading universe...")
    df = get_universe_dataframe()
    print(f"   → {len(df)} companies loaded")

    # 2. Score Everything
    print("\n[2/4] Computing composite scores...")
    scored = score_universe(df)
    print(f"   → Scores computed: {scored['Composite_Score'].min():.1f} - {scored['Composite_Score'].max():.1f}")

    # 3. Run Screens
    print("\n[3/4] Running screening strategies...")
    strategies = {
        "PEA Value": screen_pea_value(scored),
        "PEA Quality Growth": screen_pea_quality(scored),
        "Dividend Income": screen_dividend_income(scored),
        "Global Best": screen_global_best(scored),
    }

    for name, result in strategies.items():
        summary = generate_screening_summary(result)
        print(f"\n   📋 {name}: {summary['count']} stocks passed")
        if result.empty:
            continue
        print(f"      Avg Score: {summary.get('avg_composite', 'N/A')}")
        print(f"      Avg P/E: {summary.get('avg_pe', 'N/A')}")
        print(f"      Signals: {summary.get('signals', {})}")

    # 4. Display Top Picks
    print("\n[4/4] Top Picks Summary")
    print("=" * 60)

    display_cols = [
        "Name", "Sector", "Country", "Price", "Composite_Score", "Signal",
        "PE", "ROE", "DivYield", "Piotroski_F", "Altman_Z", "Graham_Number", "Graham_MoS"
    ]

    for name, result in strategies.items():
        if result.empty:
            continue
        print(f"\n🏆 {name} — Top 10:")
        top = result.head(10)
        cols = [c for c in display_cols if c in top.columns]
        print(top[cols].to_string())

    return scored, strategies


if __name__ == "__main__":
    scored_df, strats = run_pipeline()
