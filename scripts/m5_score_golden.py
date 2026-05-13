"""Compute the 3 new M5 scores for the 25 golden tickers using frozen inputs.

Outputs a JSON+CSV report so the M5 final-report can show per-ticker values.
This is a one-shot diagnostic, not part of the test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from src.analysis.scoring_engine import (  # noqa: E402
    earnings_quality_score,
    moat_score,
    risk_score_real,
)
from tests.conftest import (  # noqa: E402
    available_golden_tickers,
    load_input_row,
)


def main() -> int:
    tickers = available_golden_tickers()
    rows = []
    for t in tickers:
        row = load_input_row(t)
        # Decode JSON-NaN sentinels deeply (lists of floats)
        rows.append({**row, "Ticker": t})
    df = pd.DataFrame(rows).set_index("Ticker")

    # Compute the three new scores. price_history_map is None → row-only Risk_Score_v2.
    eq = earnings_quality_score(df)
    moat = moat_score(df)
    # risk_score_real also reads Altman_Z if present; we compute it lazily.
    if "Altman_Z" not in df.columns:
        from src.analysis.scoring_engine import altman_z_score

        df["Altman_Z"] = df.apply(altman_z_score, axis=1)
    risk = risk_score_real(df, price_history_map=None)

    out = pd.DataFrame(
        {
            "EarningsQuality_Score": eq,
            "Moat_Score": moat,
            "Risk_Score_v2": risk,
        }
    )
    print(out.to_string())
    out.to_csv(PROJECT_ROOT / "data" / "m5_golden_scores.csv")
    out.to_json(
        PROJECT_ROOT / "data" / "m5_golden_scores.json",
        orient="index",
        indent=2,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
