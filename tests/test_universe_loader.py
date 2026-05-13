"""Tests for the PEA universe loader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.data import universe_loader


def _write_csv(path: Path, tickers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": tickers}).to_csv(path, index=False)


class TestLoadStaticTickers:
    def test_returns_tickers_from_csv(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        _write_csv(csv, ["MC.PA", "TTE.PA", "AI.PA"])
        out = universe_loader._load_static_tickers(csv)
        assert out == ["MC.PA", "TTE.PA", "AI.PA"]

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        csv = tmp_path / "missing.csv"
        out = universe_loader._load_static_tickers(csv)
        assert out == []

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        _write_csv(csv, [" MC.PA ", "TTE.PA"])
        out = universe_loader._load_static_tickers(csv)
        assert out == ["MC.PA", "TTE.PA"]


class TestNormaliseSymbol:
    def test_passes_suffixed(self) -> None:
        assert universe_loader._normalise_symbol("MC.PA") == "MC.PA"

    def test_uppercases(self) -> None:
        assert universe_loader._normalise_symbol("mc.pa") == "MC.PA"

    def test_drops_bare_symbols(self) -> None:
        # ETF holdings come back as bare symbols (no exchange suffix); drop
        # them so fetch_batch doesn't fail trying to resolve "MC".
        assert universe_loader._normalise_symbol("MC") is None

    def test_drops_placeholder(self) -> None:
        assert universe_loader._normalise_symbol("-") is None
        assert universe_loader._normalise_symbol("N/A") is None
        assert universe_loader._normalise_symbol("") is None


class TestLoadPeaUniverse:
    def test_static_only_when_yfinance_disabled(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        _write_csv(csv, ["MC.PA", "TTE.PA"])
        out = universe_loader.load_pea_universe(use_yfinance=False, static_path=csv, persist_path=None)
        assert out == ["MC.PA", "TTE.PA"]

    def test_dedupe_union(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        _write_csv(csv, ["MC.PA", "TTE.PA"])

        # Mock yfinance to return one duplicate + one new (suffixed) symbol
        # plus a bare symbol that should be dropped.
        with patch.object(
            universe_loader,
            "_load_etf_holdings",
            return_value=["MC.PA", "AI.PA", "BARE_SYMBOL_NO_DOT"],
        ):
            out = universe_loader.load_pea_universe(use_yfinance=True, static_path=csv, persist_path=None)
        assert out == ["MC.PA", "TTE.PA", "AI.PA"]
        assert "BARE_SYMBOL_NO_DOT" not in out

    def test_yfinance_failure_falls_back_to_static(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        _write_csv(csv, ["MC.PA"])
        with patch.object(
            universe_loader,
            "_load_etf_holdings",
            side_effect=RuntimeError("yfinance down"),
        ):
            # _load_etf_holdings is wrapped internally; if a test fixture
            # makes the helper raise, load_pea_universe should still return
            # the static list. (The current implementation wraps each ETF
            # in try/except internally.)
            try:
                out = universe_loader.load_pea_universe(use_yfinance=True, static_path=csv, persist_path=None)
            except RuntimeError:
                pytest.fail("load_pea_universe should not propagate yfinance failures")
        assert out == ["MC.PA"]

    def test_persists_resolved_csv(self, tmp_path: Path) -> None:
        csv = tmp_path / "static.csv"
        persist = tmp_path / "resolved.csv"
        _write_csv(csv, ["MC.PA", "TTE.PA"])
        universe_loader.load_pea_universe(use_yfinance=False, static_path=csv, persist_path=persist)
        assert persist.exists()
        loaded = pd.read_csv(persist)
        assert list(loaded["ticker"]) == ["MC.PA", "TTE.PA"]
