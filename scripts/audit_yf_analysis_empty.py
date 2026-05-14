"""Probe None / empty-DataFrame behavior on tickers unlikely to have full analyst coverage."""
import yfinance as yf
import pandas as pd

for sym in ["ZZZZZ", "MC.PA", "VOW3.DE"]:
    print(f"\n########## {sym} ##########")
    tk = yf.Ticker(sym)
    for attr in ["recommendations", "recommendations_summary", "upgrades_downgrades",
                 "eps_revisions", "eps_trend", "earnings_history", "growth_estimates"]:
        try:
            val = getattr(tk, attr)
        except Exception as e:
            print(f"{attr}: ERROR {type(e).__name__}: {str(e)[:120]}")
            continue
        if val is None:
            print(f"{attr}: None")
        elif isinstance(val, pd.DataFrame):
            print(f"{attr}: DataFrame empty={val.empty} shape={val.shape} cols={list(val.columns)}")
        else:
            print(f"{attr}: {type(val).__name__} = {repr(val)[:120]}")
