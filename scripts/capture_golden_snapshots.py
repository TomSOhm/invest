"""Capture or refresh golden-file regression fixtures for the scoring engine.

Run modes:
    python -m scripts.capture_golden_snapshots --all
        Fetch live data for every ticker in tests/golden/tickers.txt, write a
        frozen input row to tests/golden/inputs/{TICKER}.json, then run the
        current scoring engine on that frozen row and write the result to
        tests/golden/snapshots/{TICKER}.json.

    python -m scripts.capture_golden_snapshots --tickers MC.PA AAPL
        Same but only for the listed tickers.

    python -m scripts.capture_golden_snapshots --rescore-only
        Skip live fetch; re-run scoring on the existing frozen inputs and
        rewrite the snapshots. Use this after a deliberate scoring change
        when you want to refresh the expected outputs.

The script is intentionally tolerant: a ticker that fails to fetch is logged
and skipped, never aborting the run. JSON encoding handles NaN/Inf safely.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from backend.app.services.cache_service import CacheService  # noqa: E402
from backend.app.services.data_fetcher import DataFetcher  # noqa: E402
from src.analysis.scoring_engine import (  # noqa: E402
    altman_z_score,
    compute_composite_score,
    data_completeness,
    generate_signal,
    graham_number,
    piotroski_f_score,
)
from functools import lru_cache

GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden"
INPUTS_DIR = GOLDEN_DIR / "inputs"
SNAPSHOTS_DIR = GOLDEN_DIR / "snapshots"
TICKERS_FILE = GOLDEN_DIR / "tickers.txt"


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(ticker: str) -> str:
    """Filesystem-safe filename. Escapes path separators and Windows DOS reserved names.

    `CON.DE` (Continental AG) collides with the Windows CON device on git+Windows;
    we prefix an underscore so the on-disk name is `_CON.DE.json`.
    """
    cleaned = ticker.replace("/", "_").replace("\\", "_").replace(":", "_")
    head = cleaned.split(".", 1)[0].upper()
    if head in _WINDOWS_RESERVED:
        return "_" + cleaned
    return cleaned


def load_tickers() -> List[str]:
    return [
        line.strip()
        for line in TICKERS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _encode_floats(obj: Any) -> Any:
    """Turn NaN/Inf into JSON-safe sentinel strings, preserving everything else."""
    if isinstance(obj, dict):
        return {k: _encode_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode_floats(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        if math.isnan(f):
            return "NaN"
        if math.isinf(f):
            return "Infinity" if f > 0 else "-Infinity"
        return f
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def _decode_floats(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _decode_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decode_floats(v) for v in obj]
    if isinstance(obj, str) and obj in ("NaN", "Infinity", "-Infinity"):
        return {"NaN": math.nan, "Infinity": math.inf, "-Infinity": -math.inf}[obj]
    return obj


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_encode_floats(data), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch_input(fetcher: DataFetcher, ticker: str) -> Dict[str, Any] | None:
    """Fetch live data for one ticker; return the row dict or None on hard failure."""
    try:
        row = fetcher.fetch_single(ticker)
    except Exception as exc:  # noqa: BLE001
        print(f"[fetch fail] {ticker}: {exc}", file=sys.stderr)
        return None
    if not row.get("Name"):
        print(f"[fetch empty] {ticker}: no Name", file=sys.stderr)
        return None
    return row


@lru_cache(maxsize=1)
def _golden_peer_universe() -> pd.DataFrame:
    """Load every frozen input under tests/golden/inputs/ as the peer DataFrame.

    The cached DataFrame is re-used for every ``score_row`` call so M3
    sector-relative ranking is computed against the same 25-ticker
    universe every time (deterministic snapshots). Index is the ticker
    symbol parsed from the filename.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    if not INPUTS_DIR.exists():
        return pd.DataFrame()
    for path in sorted(INPUTS_DIR.glob("*.json")):
        ticker = path.stem
        if ticker.startswith("_"):
            # Reverse the Windows-DOS-reserved-name escaping (e.g. `_CON.DE`
            # was saved for `CON.DE`). The leading underscore is dropped.
            ticker = ticker[1:]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        rows[ticker] = _decode_floats(data)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame.from_dict(rows, orient="index")


def score_row(row: Dict[str, Any], ticker: str | None = None) -> Dict[str, Any]:
    """Run the current scoring engine on a frozen input row → snapshot dict.

    The peer universe used for sector-relative ranking is loaded lazily
    from every JSON under ``tests/golden/inputs/``. ``ticker`` (if
    supplied) names this row inside the peer DataFrame so the lookup
    after ``score_dataframe`` finds the right row; otherwise it defaults
    to "_TARGET_" and the row is appended fresh.
    """
    series = pd.Series(_decode_floats(row))
    peers = _golden_peer_universe()

    # If the caller passed a ticker that already lives in the peer universe,
    # use that index. Otherwise tag the row "_TARGET_" and append it.
    if ticker and ticker in peers.index:
        series.name = ticker
        peers_for_score = peers
    else:
        series.name = "_TARGET_"
        peers_for_score = (
            pd.concat([peers, pd.DataFrame([series.to_dict()], index=[series.name])])
            if not peers.empty
            else pd.DataFrame([series.to_dict()], index=[series.name])
        )

    breakdown = compute_composite_score(series, peers=peers_for_score)
    composite = breakdown["composite"]
    az = altman_z_score(series)
    gn = graham_number(series)
    price = series.get("Price")
    graham_mos = (
        round((gn / price - 1) * 100, 1)
        if (gn is not None and not (isinstance(gn, float) and math.isnan(gn)) and price and not (isinstance(price, float) and math.isnan(price)) and price > 0)
        else float("nan")
    )
    return {
        "Composite_Score": round(composite, 1),
        "Valuation_Score": round(breakdown["valuation"], 1),
        "Health_Score": round(breakdown["financial_health"], 1),
        "Profitability_Score": round(breakdown["profitability"], 1),
        "Growth_Score": round(breakdown["growth"], 1),
        "Shareholder_Score": round(breakdown["shareholder_return"], 1),
        "Risk_Score": round(breakdown["risk"], 1),
        "Signal": generate_signal(composite),
        "Piotroski_F": int(piotroski_f_score(series)),
        "Altman_Z": (round(float(az), 2) if not (isinstance(az, float) and math.isnan(az)) else float("nan")),
        "Graham_Number": (round(float(gn), 2) if not (isinstance(gn, float) and math.isnan(gn)) else float("nan")),
        "Graham_MoS": graham_mos,
        # M1: audit-trail field, kept in golden snapshots so changes are tracked.
        # Not yet in the public API schema (M10 promotes it).
        "data_completeness": data_completeness(series),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="capture every ticker in tickers.txt")
    parser.add_argument("--tickers", nargs="+", help="capture only these tickers")
    parser.add_argument("--rescore-only", action="store_true", help="skip fetch; re-run scoring on existing inputs")
    args = parser.parse_args(argv)

    INPUTS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.tickers:
        tickers = args.tickers
    else:
        tickers = load_tickers()

    if args.rescore_only:
        n_ok = 0
        n_skip = 0
        for ticker in tickers:
            in_path = INPUTS_DIR / f"{safe_filename(ticker)}.json"
            if not in_path.exists():
                print(f"[skip] {ticker}: no frozen input")
                n_skip += 1
                continue
            row = json.loads(in_path.read_text(encoding="utf-8"))
            snap = score_row(row, ticker=ticker)
            write_json(SNAPSHOTS_DIR / f"{safe_filename(ticker)}.json", snap)
            print(f"[rescored] {ticker} -> score={snap['Composite_Score']} signal={snap['Signal']}")
            n_ok += 1
        print(f"\nDone. rescored={n_ok} skipped={n_skip}")
        return 0

    fetcher = DataFetcher(cache=CacheService())
    n_ok = 0
    n_fail = 0
    for ticker in tickers:
        row = fetch_input(fetcher, ticker)
        if row is None:
            n_fail += 1
            continue
        # Drop the Ticker key (encoded in the filename) and the hybrid-fetcher
        # audit metadata (`data_completeness`, `field_sources`) which are
        # provenance details not part of the scoring contract. Persisting them
        # would cause column collisions when ``score_universe`` joins the
        # input back with its own computed ``data_completeness`` column.
        _META_KEYS = {"Ticker", "data_completeness", "field_sources"}
        row_to_save = {k: v for k, v in row.items() if k not in _META_KEYS}
        write_json(INPUTS_DIR / f"{safe_filename(ticker)}.json", row_to_save)
        # Bust the lru_cache so the freshly-written input shows up in the
        # peer universe used to score subsequent tickers in this run.
        _golden_peer_universe.cache_clear()
        snap = score_row(row_to_save, ticker=ticker)
        write_json(SNAPSHOTS_DIR / f"{safe_filename(ticker)}.json", snap)
        print(f"[captured] {ticker} -> score={snap['Composite_Score']} signal={snap['Signal']}")
        n_ok += 1
        time.sleep(0.5)

    print(f"\nDone. captured={n_ok} failed={n_fail}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
