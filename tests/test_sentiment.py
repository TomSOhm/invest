"""Tests for src/analysis/sentiment.py (M9, opt-in).

These tests skip when the heavy `transformers` dependency is not installed,
matching the spec for M9.  When transformers IS installed they monkeypatch
the FinBERT pipeline singleton to a deterministic dummy classifier so we
don't have to download model weights in CI.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

# Whole-module skip if transformers is missing (sentiment is opt-in).
pytest.importorskip("transformers")

from src.analysis import sentiment  # noqa: E402  (after importorskip)


class _DummyPipeline:
    """Deterministic stand-in for HuggingFace's text-classification pipeline.

    Returns the label requested in the test fixture for each headline based
    on a keyword in the title:
        contains "good" / "beat"  -> positive
        contains "bad" / "miss"   -> negative
        else                      -> neutral
    """

    def __call__(self, texts):
        results = []
        for t in texts:
            tl = t.lower()
            if any(kw in tl for kw in ("good", "beat", "surge", "rally", "record")):
                label = "positive"
            elif any(kw in tl for kw in ("bad", "miss", "drop", "plunge", "fall")):
                label = "negative"
            else:
                label = "neutral"
            results.append(
                [
                    {"label": label, "score": 0.9},
                ]
            )
        return results


@pytest.fixture(autouse=True)
def _patch_pipeline(monkeypatch):
    """Replace the lazy-loaded FinBERT singleton with a dummy."""
    sentiment.reset_pipeline_cache()
    monkeypatch.setattr(sentiment, "_load_pipeline", lambda: _DummyPipeline())
    yield
    sentiment.reset_pipeline_cache()


# ---------------------------------------------------------------------------
# sentiment_score
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(tz=UTC)


def test_sentiment_score_all_positive_high():
    """5 positive headlines, 0 negative -> score should be 100 (>70)."""
    headlines = [
        {"title": "Apple beats earnings expectations", "publishedAt": _now()},
        {"title": "Strong rally in tech good for AAPL", "publishedAt": _now()},
        {"title": "Record quarter, AAPL surge", "publishedAt": _now()},
        {"title": "Beat consensus estimates", "publishedAt": _now()},
        {"title": "Good guidance from CEO", "publishedAt": _now()},
    ]
    score = sentiment.sentiment_score(headlines, window_days=30)
    assert score is not None
    assert score > 70


def test_sentiment_score_all_negative_low():
    headlines = [
        {"title": "Apple miss earnings", "publishedAt": _now()},
        {"title": "Bad quarter for AAPL", "publishedAt": _now()},
        {"title": "Stock plunge after results", "publishedAt": _now()},
        {"title": "Miss consensus, drop sharply", "publishedAt": _now()},
    ]
    score = sentiment.sentiment_score(headlines, window_days=30)
    assert score is not None
    assert score < 30


def test_sentiment_score_empty_returns_nan():
    """Empty list short-circuits without loading the model."""
    assert math.isnan(sentiment.sentiment_score([], window_days=30))
    assert math.isnan(sentiment.sentiment_score(None, window_days=30))


def test_sentiment_score_too_few_headlines():
    """Fewer than 3 valid headlines -> NaN."""
    headlines = [
        {"title": "Apple good day", "publishedAt": _now()},
        {"title": "Apple good news", "publishedAt": _now()},
    ]
    assert math.isnan(sentiment.sentiment_score(headlines, window_days=30))


def test_sentiment_score_mixed_returns_around_50():
    """3 positive + 3 negative -> share = 0.5 -> score ~50."""
    headlines = [
        {"title": "good news", "publishedAt": _now()},
        {"title": "good news 2", "publishedAt": _now()},
        {"title": "good news 3", "publishedAt": _now()},
        {"title": "bad news", "publishedAt": _now()},
        {"title": "bad news 2", "publishedAt": _now()},
        {"title": "bad news 3", "publishedAt": _now()},
    ]
    score = sentiment.sentiment_score(headlines, window_days=30)
    assert math.isclose(score, 50.0, rel_tol=1e-2)


# ---------------------------------------------------------------------------
# sentiment_signals_df
# ---------------------------------------------------------------------------


def test_sentiment_signals_df_basic():
    news_map = {
        "AAPL": [{"title": f"good thing {i}", "publishedAt": _now()} for i in range(5)],
        "MSFT": [{"title": f"bad thing {i}", "publishedAt": _now()} for i in range(5)],
    }
    out = sentiment.sentiment_signals_df(news_map)
    assert "Sentiment_30d" in out.columns
    assert "Sentiment_Trend" in out.columns
    assert out.loc["AAPL", "Sentiment_30d"] > 70
    assert out.loc["MSFT", "Sentiment_30d"] < 30


def test_sentiment_signals_df_empty_input():
    out = sentiment.sentiment_signals_df({})
    assert out.empty
    assert "Sentiment_30d" in out.columns
