"""
Invest Solo -- News Sentiment Signals (M9, opt-in)

Loads a FinBERT classifier from Hugging Face on first use and applies it to
news headlines.  Sentiment is OPT-IN: the heavy ``transformers`` + ``torch``
dependencies live in ``backend/requirements-ml.txt`` and are NOT pulled by
the main install.  When transformers is absent every public function returns
NaN so the rest of the engine continues to work.

Caching
-------
The HuggingFace pipeline is cached as a module-level singleton (lazy-loaded);
tests that monkeypatch the singleton don't pay model-load cost on each call.

Public API
----------
- ``sentiment_score(headlines, window_days=30) -> float``
- ``sentiment_signals_df(news_map) -> pd.DataFrame``
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Lazy classifier singleton
# ---------------------------------------------------------------------------

_PIPELINE: Any | None = None
_PIPELINE_LOAD_FAILED: bool = False
_FINBERT_MODEL_CANDIDATES = (
    "ProsusAI/finbert",
    "yiyanghkust/finbert-tone",
)


def _load_pipeline() -> Any | None:
    """Try to load a FinBERT classification pipeline.

    Returns the pipeline instance or None if transformers/torch are missing
    or both candidate models fail to download. Caches the negative result so
    we don't retry network calls on every call.
    """
    global _PIPELINE, _PIPELINE_LOAD_FAILED
    if _PIPELINE is not None:
        return _PIPELINE
    if _PIPELINE_LOAD_FAILED:
        return None

    try:
        from transformers import pipeline  # type: ignore
    except ImportError:
        logger.warning(
            "transformers not installed -- sentiment scoring disabled. "
            "Install via: pip install -r backend/requirements-ml.txt"
        )
        _PIPELINE_LOAD_FAILED = True
        return None

    last_exc: Exception | None = None
    for model_name in _FINBERT_MODEL_CANDIDATES:
        try:
            _PIPELINE = pipeline("text-classification", model=model_name, top_k=None)
            logger.info(f"Loaded FinBERT pipeline: {model_name}")
            return _PIPELINE
        except Exception as exc:
            last_exc = exc
            logger.debug(f"Failed to load {model_name}: {exc}")
            continue

    logger.warning(f"All FinBERT candidates failed to load (last error: {last_exc})")
    _PIPELINE_LOAD_FAILED = True
    return None


def reset_pipeline_cache() -> None:
    """Reset the cached pipeline (test hook)."""
    global _PIPELINE, _PIPELINE_LOAD_FAILED
    _PIPELINE = None
    _PIPELINE_LOAD_FAILED = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> datetime | None:
    """Parse a variety of date representations into a tz-aware UTC datetime.

    Accepts ISO strings, datetime objects, and Unix timestamps (yfinance).
    Returns None on failure.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    # yfinance providerPublishTime is an int (epoch seconds)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            dt = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.isna(dt):
                return None
            return dt.to_pydatetime()
        except Exception:
            return None
    return None


def _filter_within_window(headlines: list[dict[str, Any]], window_days: int) -> list[dict[str, Any]]:
    """Return only headlines whose published date is within ``window_days``."""
    cutoff = datetime.now(tz=UTC) - timedelta(days=window_days)
    out: list[dict[str, Any]] = []
    for item in headlines:
        # Tolerate both 'publishedAt' (M2 fetcher shape) and 'published_date' (spec).
        published = item.get("publishedAt") or item.get("published_date") or item.get("published")
        dt = _parse_date(published)
        if dt is None or dt >= cutoff:
            # Keep items with unparseable dates; missing dates are common from news APIs
            # and excluding them would cause sparse universes to score NaN.
            out.append(item)
    return out


def _score_headlines(headlines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run FinBERT over each headline title; return list of {label, score, ts}.

    Empty list on classifier failure.
    """
    pipe = _load_pipeline()
    if pipe is None:
        return []

    texts = [(item.get("title") or item.get("text") or "").strip() for item in headlines]
    keep_idx = [i for i, t in enumerate(texts) if t]
    if not keep_idx:
        return []

    try:
        outputs = pipe([texts[i] for i in keep_idx])
    except Exception as exc:
        logger.warning(f"FinBERT inference failed: {exc}")
        return []

    results: list[dict[str, Any]] = []
    for idx, out in zip(keep_idx, outputs, strict=False):
        # `top_k=None` returns a list-of-dicts per input; pick the argmax label.
        if isinstance(out, list) and out:
            best = max(out, key=lambda d: d.get("score", 0.0))
        elif isinstance(out, dict):
            best = out
        else:
            continue
        label = str(best.get("label", "")).lower()
        score = float(best.get("score", 0.0))
        published = headlines[idx].get("publishedAt") or headlines[idx].get("published_date")
        ts = _parse_date(published)
        results.append({"label": label, "score": score, "ts": ts})
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sentiment_score(headlines: list[dict[str, Any]], window_days: int = 30) -> float:
    """Score 0-100 from FinBERT classification of recent headlines.

    Aggregation
    -----------
        positive_share = positives / (positives + negatives)
        score = positive_share * 100   (linear 0..100)

    Returns NaN if:
        - headlines is empty / None
        - fewer than 3 valid headlines remain after the window filter
        - the FinBERT pipeline cannot be loaded
    """
    if not headlines:
        return float("nan")

    filtered = _filter_within_window(headlines, window_days)
    if len(filtered) < 3:
        return float("nan")

    scored = _score_headlines(filtered)
    if not scored:
        return float("nan")

    pos = sum(1 for s in scored if s["label"].startswith("pos"))
    neg = sum(1 for s in scored if s["label"].startswith("neg"))
    total = pos + neg
    if total == 0:
        return 50.0  # all neutral -> neutral score
    return float(round(100.0 * pos / total, 2))


def _sentiment_trend(scored: list[dict[str, Any]], window_days: int = 30) -> float:
    """Slope of 7-day rolling positive-share over the window.

    Builds a daily series of positive-share, takes a 7-day rolling mean, then
    fits a least-squares line to the last ``window_days`` rolling values.
    Returns the slope (points/day). NaN if the series is too short.
    """
    if not scored:
        return float("nan")
    df = pd.DataFrame(scored)
    df = df.dropna(subset=["ts"])
    if df.empty:
        return float("nan")
    df["date"] = pd.to_datetime(df["ts"]).dt.tz_convert("UTC").dt.normalize()
    df["is_pos"] = df["label"].str.startswith("pos").astype(int)
    df["is_neg"] = df["label"].str.startswith("neg").astype(int)
    daily = df.groupby("date").agg(pos=("is_pos", "sum"), neg=("is_neg", "sum"))
    daily["share"] = daily["pos"] / (daily["pos"] + daily["neg"]).replace(0, np.nan)
    daily = daily.dropna(subset=["share"])
    if len(daily) < 4:
        return float("nan")
    rolling = daily["share"].rolling(window=7, min_periods=2).mean().dropna()
    if len(rolling) < 4:
        return float("nan")
    y = rolling.tail(window_days).values
    x = np.arange(len(y), dtype=float)
    if len(y) < 2:
        return float("nan")
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def sentiment_signals_df(news_map: dict[str, list[dict[str, Any]]]) -> pd.DataFrame:
    """Compute sentiment signal block for a universe.

    Returns a DataFrame indexed by ticker with columns:
        Sentiment_30d   : 0-100 share of positives (NaN if <3 headlines)
        Sentiment_Trend : slope of 7-day rolling positive-share
    """
    rows = []
    for ticker, headlines in news_map.items():
        score = sentiment_score(headlines, window_days=30)
        trend = float("nan")
        if np.isfinite(score) and headlines:
            scored = _score_headlines(_filter_within_window(headlines, 30))
            trend = _sentiment_trend(scored, window_days=30)
        rows.append(
            {
                "Ticker": ticker,
                "Sentiment_30d": score,
                "Sentiment_Trend": trend,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Sentiment_30d", "Sentiment_Trend"])
    return pd.DataFrame(rows).set_index("Ticker")
