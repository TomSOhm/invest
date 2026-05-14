import yfinance as yf
import pandas as pd

tk = yf.Ticker("AAPL")
for attr in [
    "recommendations",
    "recommendations_summary",
    "upgrades_downgrades",
    "eps_revisions",
    "eps_trend",
    "earnings_history",
    "growth_estimates",
]:
    print(f"\n=== {attr} ===")
    try:
        val = getattr(tk, attr)
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:300])
        continue
    print("type:", type(val).__name__)
    if isinstance(val, pd.DataFrame):
        print("empty:", val.empty)
        print("shape:", val.shape)
        print("index:", list(val.index)[:6])
        print("columns:", list(val.columns))
        print("head:\n", val.head(3))
    else:
        print("repr:", repr(val)[:500])
