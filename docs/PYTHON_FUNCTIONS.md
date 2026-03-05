# Changements et Explications Clés

---

#### `get_pme_tickers_from_source()` (À FAIRE PAR VOUS)

This is a fundamental function that you need to develop. I've included an `example_list` so that the script works.

I've added comments on how you could read a CSV file (`ma_liste_pme_tickers.csv`) that you would have prepared. This is often the simplest approach to start.

Obtaining a truly comprehensive and automatically updated list of tickers for SMEs in a specific market (e.g., Euronext Growth Paris) may require:

*   Finding a page on the Euronext website (or another exchange) that lists these companies and writing a web scraper (with `requests` and `BeautifulSoup`). This is advanced and subject to website changes.
*   Using a paid financial API (EOD Historical Data, FinancialModelingPrep, AlphaVantage Premium, etc.) that offers "screener" functionalities to filter by market, capitalization, etc.

---

#### New Thresholds

*   `SEUIL_DETTE_NETTE_EBE_MAX`
*   `SEUIL_GEARING_MAX`
*   `SEUIL_VOLUME_MOYEN_MIN_VALEUR`

---

#### `expliquer_metriques()`

Updated with the new metrics.

---

#### `get_company_data()`

*   Retrieves `totalDebt`, `totalCash`, `ebitda` from `ticker.info`.
*   Retrieves `Total Stockholder Equity` from `ticker.balance_sheet` for more precise gearing. `balance_sheet` may sometimes take longer to load or not be available for all SMEs.

    *   I've added a simple fallback if `balance_sheet` fails.
*   Calculates `Dette Nette/EBE` and `Gearing`.
*   Retrieves `averageVolume` (or `averageDailyVolume10Day`) and the price to calculate `Vol. Moyen Val. (k)`.
*   Improved error handling: displays a less verbose error message if a company fails to load.
*   `time.sleep(0.1)` has been added in the main loop to avoid overloading Yahoo Finance servers when retrieving data for many companies.

---

## Main Screening

*   New criteria are added to the `df_prometteuses_strict` filter.
*   I've added `P/E > 0` to ensure the company is profitable (a negative P/E indicates losses).
*   I've added `Gearing > 0` (negative gearing is rare and often due to negative equity, a sign of serious difficulties).
*   I've added a lower bound for `Dette Nette/EBE` to avoid cases where `EBE` is very small and negative, which can result in a very high positive ratio and skew comparisons.

---

## Plotly Visualizations

*   New metrics are added to the `hover_data` of existing charts.
*   A new scatter plot, `Dette Nette/EBE` vs. `Gearing`, is added to visualize the indebtedness of promising companies.
*   The Plotly table has been updated to include the new relevant columns and improve formatting.
*   Axis ranges of some charts (e.g., P/E) are adjusted for better readability.

---

## Next Steps for You

1.  **Obtain your list of tickers:** This is the most important step. Explore the websites of Euronext (or the exchange you're interested in) for SME compartments (Growth, Access, etc.). You may need to copy-paste the tickers into a CSV file initially.
2.  **Adapt `get_pme_tickers_from_source()`:** If you have a CSV, uncomment and adapt the `source_type == "csv_file"` section.
3.  **Adjust Thresholds:** The thresholds are crucial and depend on your risk tolerance and strategy. The provided ones are starting points.
4.  **Test with a Larger List:** Once you have a good list of tickers, run the script. Be patient; retrieving data for hundreds of companies can take time.
5.  **Analyze Results:** The charts and tables will help you identify standout companies. Remember that this is a quantitative starting point; qualitative analysis is always necessary before investing.

This script is now much more powerful. The key to its large-scale utility lies in your ability to efficiently populate the `LISTE_TICKERS_PME`.

---

## Citation

[BlamerX/Stock-Price-Prediction-W](https://github.com/BlamerX/Stock-Price-Prediction-W)