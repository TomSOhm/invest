"""
Invest Solo — Interactive HTML Dashboard Generator
Creates a self-contained HTML file with all charts and data.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime

import numpy as np
import pandas as pd

from src.analysis.scoring_engine import score_universe
from src.data.sample_universe import get_universe_dataframe
from src.strategy.screener import (
    generate_screening_summary,
    screen_dividend_income,
    screen_global_best,
    screen_pea_quality,
    screen_pea_value,
)


def score_to_color(score, alpha=1.0):
    """Convert 0-100 score to red-yellow-green color."""
    if pd.isna(score):
        return f"rgba(180,180,180,{alpha})"
    s = max(0, min(100, score))
    if s < 50:
        r = 220
        g = int(80 + s * 3.4)
        b = 60
    else:
        r = int(220 - (s - 50) * 3.6)
        g = 200
        b = 60
    return f"rgba({r},{g},{b},{alpha})"


def signal_badge(signal):
    colors = {"Strong Buy": "#059669", "Buy": "#10b981", "Hold": "#f59e0b", "Sell": "#ef4444", "Strong Sell": "#991b1b"}
    c = colors.get(signal, "#6b7280")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">{signal}</span>'


def pea_badge(is_pea, is_pme=False):
    if is_pme:
        return '<span style="background:#7c3aed;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">PME</span>'
    if is_pea:
        return '<span style="background:#2563eb;color:#fff;padding:1px 6px;border-radius:8px;font-size:10px">PEA</span>'
    return ""


def generate_dashboard(scored_df: pd.DataFrame, output_path: str):
    """Generate the full interactive HTML dashboard."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Strategy screens
    pea_val = screen_pea_value(scored_df)
    pea_qual = screen_pea_quality(scored_df)
    div_inc = screen_dividend_income(scored_df)
    glob_best = screen_global_best(scored_df)

    # Build table rows for main scoreboard
    table_rows = ""
    for _i, (ticker, row) in enumerate(scored_df.iterrows()):
        cs = row.get("Composite_Score", 0)
        bg = score_to_color(cs, 0.12)
        bar_w = max(2, cs)

        # Score breakdown mini-bars
        def mini_bar(val, label):
            c = score_to_color(val, 0.9)
            w = max(2, val)
            return f'<div style="display:flex;align-items:center;gap:4px"><div style="width:{w}px;height:6px;background:{c};border-radius:3px"></div><span style="font-size:10px;color:#888">{val:.0f}</span></div>'

        row.get("Graham_Number", np.nan)
        mos = row.get("Graham_MoS", np.nan)
        mos_str = f"{mos:+.0f}%" if pd.notna(mos) else "—"
        mos_color = "#059669" if pd.notna(mos) and mos > 0 else "#ef4444" if pd.notna(mos) else "#999"

        table_rows += f"""
        <tr style="background:{bg}" class="data-row" data-sector="{row.get("Sector", "")}" data-country="{row.get("Country", "")}" data-signal="{row.get("Signal", "")}">
            <td style="font-weight:700;font-family:monospace">{ticker}</td>
            <td>{row.get("Name", "")[:28]}</td>
            <td><span style="font-size:11px">{row.get("Sector", "")[:18]}</span></td>
            <td>{row.get("Country", "")}</td>
            <td style="text-align:right">€{row.get("Price", 0):,.2f}</td>
            <td style="text-align:center">
                <div style="display:flex;align-items:center;gap:4px">
                    <div style="width:{bar_w}px;height:14px;background:{score_to_color(cs, 0.85)};border-radius:4px"></div>
                    <strong>{cs:.1f}</strong>
                </div>
            </td>
            <td style="text-align:center">{signal_badge(row.get("Signal", ""))}</td>
            <td style="text-align:center">{mini_bar(row.get("Valuation_Score", 0), "V")}</td>
            <td style="text-align:center">{mini_bar(row.get("Health_Score", 0), "H")}</td>
            <td style="text-align:center">{mini_bar(row.get("Profitability_Score", 0), "P")}</td>
            <td style="text-align:right">{row.get("PE", 0):.1f}</td>
            <td style="text-align:right">{row.get("ROE", 0) * 100:.1f}%</td>
            <td style="text-align:right">{row.get("DivYield", 0) * 100:.1f}%</td>
            <td style="text-align:center;font-weight:600">{row.get("Piotroski_F", 0)}/9</td>
            <td style="text-align:right">{row.get("Altman_Z", 0):.2f}</td>
            <td style="text-align:right;color:{mos_color};font-weight:600">{mos_str}</td>
            <td style="text-align:center">{pea_badge(row.get("PEA", False), row.get("PEA_PME", False))}</td>
        </tr>"""

    # Build heatmap data for category scores
    heatmap_data = []
    categories = [
        "Valuation_Score",
        "Health_Score",
        "Profitability_Score",
        "Growth_Score",
        "Shareholder_Score",
        "Risk_Score",
    ]
    cat_labels = ["Valuation", "Health", "Profitability", "Growth", "Shareholder", "Risk"]
    for _, row in scored_df.head(20).iterrows():
        cells = []
        for cat in categories:
            v = row.get(cat, 50)
            cells.append({"value": round(v, 1), "color": score_to_color(v, 0.8)})
        heatmap_data.append({"name": row.get("Name", "")[:22], "cells": cells})

    heatmap_rows = ""
    for item in heatmap_data:
        cells_html = ""
        for cell in item["cells"]:
            cells_html += f'<td style="background:{cell["color"]};text-align:center;font-weight:600;font-size:12px;padding:6px">{cell["value"]:.0f}</td>'
        heatmap_rows += (
            f'<tr><td style="font-size:12px;padding:4px 8px;white-space:nowrap">{item["name"]}</td>{cells_html}</tr>'
        )

    # Sector distribution
    sector_counts = scored_df["Sector"].value_counts()
    sector_bars = ""
    max_count = sector_counts.max()
    colors_palette = [
        "#3b82f6",
        "#ef4444",
        "#10b981",
        "#f59e0b",
        "#8b5cf6",
        "#ec4899",
        "#14b8a6",
        "#f97316",
        "#6366f1",
        "#84cc16",
    ]
    for i, (sector, count) in enumerate(sector_counts.items()):
        w = int(count / max_count * 100)
        c = colors_palette[i % len(colors_palette)]
        sector_bars += f"""<div style="display:flex;align-items:center;gap:8px;margin:4px 0">
            <span style="width:140px;font-size:12px;text-align:right">{sector}</span>
            <div style="width:{w}%;height:18px;background:{c};border-radius:4px;min-width:20px"></div>
            <span style="font-size:12px;font-weight:600">{count}</span>
        </div>"""

    # Signal distribution
    signal_counts = scored_df["Signal"].value_counts()
    signal_bars_html = ""
    signal_colors = {
        "Strong Buy": "#059669",
        "Buy": "#10b981",
        "Hold": "#f59e0b",
        "Sell": "#ef4444",
        "Strong Sell": "#991b1b",
    }
    for sig in ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]:
        cnt = signal_counts.get(sig, 0)
        w = int(cnt / len(scored_df) * 100) if len(scored_df) > 0 else 0
        c = signal_colors.get(sig, "#999")
        signal_bars_html += f"""<div style="display:flex;align-items:center;gap:8px;margin:3px 0">
            <span style="width:80px;font-size:12px;text-align:right">{sig}</span>
            <div style="width:{w}%;height:16px;background:{c};border-radius:3px;min-width:4px"></div>
            <span style="font-size:12px;font-weight:600">{cnt}</span>
        </div>"""

    # Strategy cards
    strats = [
        ("🎯 PEA Value", pea_val, "#2563eb"),
        ("🚀 PEA Quality Growth", pea_qual, "#7c3aed"),
        ("💰 Dividend Income", div_inc, "#059669"),
        ("🌍 Global Best", glob_best, "#f59e0b"),
    ]
    strategy_cards = ""
    for name, df_strat, color in strats:
        summary = generate_screening_summary(df_strat)
        top3 = ""
        for _, r in df_strat.head(3).iterrows():
            top3 += f'<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.1)"><span>{r.get("Name", "")[:20]}</span><span style="font-weight:700">{r.get("Composite_Score", 0):.0f}</span></div>'
        strategy_cards += f"""
        <div style="background:linear-gradient(135deg,{color}22,{color}08);border:1px solid {color}44;border-radius:12px;padding:16px;min-width:220px">
            <div style="font-weight:700;font-size:15px;margin-bottom:8px">{name}</div>
            <div style="font-size:28px;font-weight:800;color:{color}">{summary.get("count", 0)}</div>
            <div style="font-size:11px;color:#888;margin-bottom:8px">stocks passed | avg score {summary.get("avg_composite", "—")}</div>
            <div style="font-size:12px">{top3 if top3 else '<span style="color:#888">No matches</span>'}</div>
        </div>"""

    # Top 5 picks detail cards
    top5_cards = ""
    for _, row in scored_df.head(5).iterrows():
        cs = row.get("Composite_Score", 0)
        mos = row.get("Graham_MoS", np.nan)
        mos_str = f"{mos:+.1f}%" if pd.notna(mos) else "—"
        top5_cards += f"""
        <div style="background:#1a1a2e;border:1px solid #333;border-radius:12px;padding:16px;min-width:200px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-weight:700;font-size:16px">{row.get("Name", "")[:22]}</span>
                {signal_badge(row.get("Signal", ""))}
            </div>
            <div style="font-size:11px;color:#888;margin:4px 0">{row.get("Sector", "")} · {row.get("Country", "")}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px;font-size:12px">
                <div>Score <strong style="color:{score_to_color(cs)}">{cs:.0f}</strong></div>
                <div>P/E <strong>{row.get("PE", 0):.1f}</strong></div>
                <div>ROE <strong>{row.get("ROE", 0) * 100:.1f}%</strong></div>
                <div>Div <strong>{row.get("DivYield", 0) * 100:.1f}%</strong></div>
                <div>F-Score <strong>{row.get("Piotroski_F", 0)}/9</strong></div>
                <div>Graham MoS <strong style="color:{"#10b981" if pd.notna(mos) and mos > 0 else "#ef4444"}">{mos_str}</strong></div>
            </div>
        </div>"""

    # Score distribution histogram (CSS-only)
    scores = scored_df["Composite_Score"].dropna().values
    bins = np.histogram(scores, bins=[0, 20, 30, 40, 50, 55, 60, 65, 70, 75, 80, 100])
    max_bin = max(bins[0]) if max(bins[0]) > 0 else 1
    hist_bars = ""
    bin_labels = ["0-20", "20-30", "30-40", "40-50", "50-55", "55-60", "60-65", "65-70", "70-75", "75-80", "80+"]
    for i, count in enumerate(bins[0]):
        h = int(count / max_bin * 120)
        mid = (bins[1][i] + bins[1][i + 1]) / 2
        c = score_to_color(mid, 0.85)
        hist_bars += f"""<div style="display:flex;flex-direction:column;align-items:center;gap:2px">
            <span style="font-size:10px;font-weight:600">{count}</span>
            <div style="width:28px;height:{h}px;background:{c};border-radius:4px 4px 0 0"></div>
            <span style="font-size:9px;color:#888">{bin_labels[i]}</span>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invest Solo — Dashboard {now}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600;700;800&display=swap');
  :root {{
    --bg: #0f0f1a; --surface: #1a1a2e; --border: #2a2a3e;
    --text: #e4e4f0; --muted: #888; --accent: #3b82f6;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; padding: 20px; }}
  h1 {{ font-size: 28px; font-weight: 800; background: linear-gradient(135deg, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  h2 {{ font-size: 18px; font-weight: 700; margin: 24px 0 12px; color: #c4c4dd; }}
  h3 {{ font-size: 14px; font-weight: 600; color: #999; margin-bottom: 8px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid var(--border); margin-bottom: 20px; }}
  .stats {{ display: flex; gap: 24px; }}
  .stat {{ text-align: center; }}
  .stat-value {{ font-size: 24px; font-weight: 800; color: var(--accent); }}
  .stat-label {{ font-size: 11px; color: var(--muted); }}
  .strategies {{ display: flex; gap: 12px; overflow-x: auto; padding: 4px 0; }}
  .top5 {{ display: flex; gap: 12px; overflow-x: auto; padding: 4px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: var(--surface); padding: 8px 6px; text-align: left; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; position: sticky; top: 0; z-index: 10; }}
  td {{ padding: 6px; border-bottom: 1px solid var(--border); }}
  tr:hover {{ background: rgba(59,130,246,0.08) !important; }}
  .table-container {{ max-height: 600px; overflow-y: auto; border-radius: 8px; border: 1px solid var(--border); }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }}
  .heatmap {{ border-collapse: collapse; width: 100%; }}
  .heatmap th {{ font-size: 10px; padding: 4px 6px; }}
  .heatmap td {{ padding: 4px 6px; border: 1px solid var(--border); }}
  .filters {{ display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }}
  .filter-btn {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 4px 12px; border-radius: 16px; cursor: pointer; font-size: 11px; transition: all 0.2s; }}
  .filter-btn:hover, .filter-btn.active {{ background: var(--accent); border-color: var(--accent); }}
  .hist {{ display: flex; align-items: flex-end; gap: 4px; height: 160px; padding: 8px 0; }}
  input[type=text] {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; border-radius: 8px; font-size: 12px; width: 200px; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>📊 Invest Solo</h1>
    <div style="font-size:12px;color:var(--muted);margin-top:4px">Quantitative Fundamental Analysis · {now} · {len(scored_df)} companies</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-value">{len(scored_df)}</div><div class="stat-label">Universe</div></div>
    <div class="stat"><div class="stat-value">{len(scored_df[scored_df["Signal"].isin(["Buy", "Strong Buy"])])}</div><div class="stat-label">Buy Signals</div></div>
    <div class="stat"><div class="stat-value">{scored_df["Composite_Score"].mean():.0f}</div><div class="stat-label">Avg Score</div></div>
    <div class="stat"><div class="stat-value">{scored_df[scored_df["PEA"]].shape[0]}</div><div class="stat-label">PEA Eligible</div></div>
  </div>
</div>

<h2>🏆 Strategy Screens</h2>
<div class="strategies">{strategy_cards}</div>

<h2>⭐ Top 5 Picks</h2>
<div class="top5">{top5_cards}</div>

<div class="grid-2" style="margin-top:20px">
  <div class="card">
    <h3>Score Distribution</h3>
    <div class="hist">{hist_bars}</div>
  </div>
  <div class="card">
    <h3>Signal Breakdown</h3>
    <div style="padding:8px 0">{signal_bars_html}</div>
  </div>
</div>

<div class="grid-2" style="margin-top:16px">
  <div class="card">
    <h3>Sector Distribution</h3>
    {sector_bars}
  </div>
  <div class="card">
    <h3>Score Heatmap (Top 20)</h3>
    <div style="overflow-x:auto">
    <table class="heatmap">
      <tr><th></th>{"".join(f"<th>{l}</th>" for l in cat_labels)}</tr>
      {heatmap_rows}
    </table>
    </div>
  </div>
</div>

<h2>📋 Full Scoreboard</h2>
<div style="margin-bottom:8px">
  <input type="text" id="search" placeholder="Search ticker or name..." oninput="filterTable()">
  <div class="filters" style="margin-top:8px">
    <button class="filter-btn active" onclick="filterSignal('all',this)">All</button>
    <button class="filter-btn" onclick="filterSignal('Strong Buy',this)">Strong Buy</button>
    <button class="filter-btn" onclick="filterSignal('Buy',this)">Buy</button>
    <button class="filter-btn" onclick="filterSignal('Hold',this)">Hold</button>
    <button class="filter-btn" onclick="filterSignal('Sell',this)">Sell</button>
  </div>
</div>
<div class="table-container">
<table id="scoreboard">
  <thead>
  <tr>
    <th>Ticker</th><th>Name</th><th>Sector</th><th>🌍</th><th>Price</th>
    <th>Score</th><th>Signal</th><th>Valuation</th><th>Health</th><th>Profit</th>
    <th>P/E</th><th>ROE</th><th>Div%</th><th>F-Score</th><th>Z-Score</th><th>Graham MoS</th><th>PEA</th>
  </tr>
  </thead>
  <tbody>{table_rows}</tbody>
</table>
</div>

<div style="margin-top:24px;padding:16px;background:var(--surface);border-radius:12px;border:1px solid var(--border)">
  <h3>📐 Methodology Quick Reference</h3>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-size:11px;color:#aaa;margin-top:8px">
    <div><strong>Composite Score</strong>: Valuation 25% + Health 20% + Profitability 20% + Growth 15% + Shareholder 10% + Risk 10%</div>
    <div><strong>Piotroski F-Score</strong>: 9-point financial strength indicator (8-9 strong, &lt;5 weak)</div>
    <div><strong>Graham MoS</strong>: Margin of Safety = (Graham Number / Price - 1) × 100. Positive = undervalued</div>
    <div><strong>Altman Z-Score</strong>: &gt;2.99 safe, 1.81-2.99 grey zone, &lt;1.81 distress</div>
    <div><strong>PEA</strong>: EU/EEA HQ companies eligible for French tax-advantaged wrapper</div>
    <div><strong>Signals</strong>: Strong Buy ≥80, Buy ≥65, Hold 40-65, Sell &lt;40, Strong Sell &lt;25</div>
  </div>
</div>

<div style="text-align:center;margin-top:16px;font-size:11px;color:#555">
  Invest Solo v0.2.0 · Generated {now} · Data for illustration · Not financial advice
</div>

<script>
function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  document.querySelectorAll('.data-row').forEach(r => {{
    const text = r.textContent.toLowerCase();
    r.style.display = text.includes(q) ? '' : 'none';
  }});
}}
function filterSignal(signal, btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.data-row').forEach(r => {{
    if (signal === 'all') {{ r.style.display = ''; }}
    else {{ r.style.display = r.dataset.signal === signal ? '' : 'none'; }}
  }});
}}
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Dashboard saved to {output_path}")
    return output_path


if __name__ == "__main__":
    from pathlib import Path

    df = get_universe_dataframe()
    scored = score_universe(df)
    out_path = Path(__file__).resolve().parents[2] / "data" / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    generate_dashboard(scored, str(out_path))
