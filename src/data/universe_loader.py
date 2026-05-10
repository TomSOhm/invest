"""Universe loader for the screener.

Strategy: union of yfinance ETF holdings (auto-grow) + a committed static
fallback CSV. Falls back gracefully when yfinance is rate-limited or the
holdings API returns nothing. The static CSV is the source of truth when
the network is unavailable.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pandas as pd
from loguru import logger

# ETFs that track major European indices, used as a proxy for index
# components. yfinance exposes their top holdings via Ticker.funds_data;
# the holdings symbols come back un-suffixed (e.g. "MC" not "MC.PA"),
# which is why the static CSV remains the load-bearing source.
_INDEX_PROXY_ETFS: tuple[str, ...] = (
    "CAC.PA",     # Lyxor CAC 40
    "MEUD.PA",    # Lyxor Stoxx Europe 600
    "EXSI.DE",    # iShares Stoxx Europe 50
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STATIC_CSV = _PROJECT_ROOT / "data" / "universes" / "universe_pea_static.csv"
_RESOLVED_CSV = _PROJECT_ROOT / "data" / "cache" / "universe_pea_resolved.csv"


def _load_static_tickers(path: Path = _STATIC_CSV) -> List[str]:
    """Return tickers from the committed static CSV. Empty list if missing."""
    if not path.exists():
        logger.warning(f"Static universe CSV missing at {path}; returning []")
        return []
    df = pd.read_csv(path)
    if "ticker" not in df.columns:
        logger.error(f"Static universe CSV at {path} has no 'ticker' column")
        return []
    return df["ticker"].dropna().astype(str).str.strip().tolist()


def _load_etf_holdings(etf_symbols: Iterable[str] = _INDEX_PROXY_ETFS) -> List[str]:
    """Try each ETF, collect non-empty top_holdings symbols.

    yfinance's ``Ticker.funds_data.top_holdings`` returns at most ~10 rows
    and may raise or return None when the network is down or the ETF has
    no holdings exposed. Each ETF lookup is independently try/excepted so
    one failure doesn't kill the others.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; skipping ETF-holdings probe")
        return []

    out: List[str] = []
    for symbol in etf_symbols:
        try:
            tk = yf.Ticker(symbol)
            holdings = getattr(getattr(tk, "funds_data", None), "top_holdings", None)
            if holdings is None or holdings.empty:
                logger.debug(f"ETF {symbol}: no holdings data")
                continue
            # Holdings index is the symbol; values include name + weight.
            symbols = list(holdings.index.astype(str))
            out.extend(symbols)
            logger.info(f"ETF {symbol}: {len(symbols)} holdings discovered")
        except Exception as exc:
            logger.warning(f"ETF {symbol} holdings probe failed: {exc}")
    return out


def _normalise_symbol(sym: str) -> Optional[str]:
    """Best-effort symbol cleanup. Returns None for clearly-bad symbols.

    yfinance ETF holdings often return un-suffixed Euronext symbols (e.g.
    'MC' for LVMH instead of 'MC.PA'). Without an exchange suffix yfinance
    cannot resolve them at fetch time, so we drop bare symbols rather than
    feed them into ``fetch_batch`` and watch them all fail.
    """
    if not sym:
        return None
    sym = sym.strip().upper()
    # Drop empty / placeholder rows
    if sym in {"-", "N/A", "NAN"}:
        return None
    # Reject bare US-style symbols (no exchange dot suffix). Static CSV
    # provides the suffixed forms; ETF holdings without suffix are unsafe.
    if "." not in sym:
        return None
    return sym


def load_pea_universe(
    *,
    use_yfinance: bool = True,
    static_path: Path = _STATIC_CSV,
    persist_path: Optional[Path] = _RESOLVED_CSV,
) -> List[str]:
    """Return the deduplicated PEA ticker list.

    Combines yfinance ETF holdings (best effort) with the static CSV.
    Persists the resolved list to ``persist_path`` for inspection.

    Parameters
    ----------
    use_yfinance:
        When False, skip the ETF holdings probe entirely and rely solely on
        the static CSV. Useful in tests and offline environments.
    static_path:
        Path to the static fallback CSV. Tests can override.
    persist_path:
        Where to write the resolved list. Pass ``None`` to skip persistence.
    """
    static_syms = _load_static_tickers(static_path)
    yf_syms: List[str] = []
    if use_yfinance:
        try:
            yf_syms = _load_etf_holdings()
        except Exception as exc:
            logger.warning(f"yfinance ETF probe raised — using static only: {exc}")
            yf_syms = []

    seen: set[str] = set()
    out: List[str] = []
    for sym in [*static_syms, *yf_syms]:
        norm = _normalise_symbol(sym)
        if norm is None or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)

    if not out:
        logger.error(
            "Universe loader produced empty list — static CSV missing AND "
            "yfinance holdings unavailable."
        )

    if persist_path is not None and out:
        try:
            persist_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"ticker": out}).to_csv(persist_path, index=False)
        except Exception as exc:
            logger.warning(f"Universe persist failed at {persist_path}: {exc}")

    logger.info(
        f"PEA universe loaded: {len(out)} tickers "
        f"(static={len(static_syms)}, yfinance={len(yf_syms)})"
    )
    return out
