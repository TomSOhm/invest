"""
Invest Solo — Static Chart Generator (matplotlib)
Generates publication-quality analysis charts.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as mticker
from datetime import datetime

from src.data.sample_universe import get_universe_dataframe
from src.analysis.scoring_engine import score_universe
from src.strategy.screener import screen_pea_value

# Dark theme
plt.rcParams.update({
    'figure.facecolor': '#0f0f1a', 'axes.facecolor': '#1a1a2e',
    'text.color': '#e4e4f0', 'axes.labelcolor': '#c4c4dd',
    'xtick.color': '#888', 'ytick.color': '#888',
    'axes.edgecolor': '#333', 'grid.color': '#2a2a3e',
    'font.family': 'sans-serif', 'font.size': 10,
})

RYG_CMAP = LinearSegmentedColormap.from_list('ryg', ['#ef4444', '#f59e0b', '#10b981'], N=256)


def chart_composite_scores(scored_df, output_path):
    """Horizontal bar chart of composite scores."""
    top20 = scored_df.head(20).sort_values("Composite_Score")
    fig, ax = plt.subplots(figsize=(12, 8))
    
    colors = [RYG_CMAP(s / 100) for s in top20["Composite_Score"]]
    bars = ax.barh(range(len(top20)), top20["Composite_Score"], color=colors, height=0.7, edgecolor='none')
    
    ax.set_yticks(range(len(top20)))
    ax.set_yticklabels([f'{n[:22]}' for n in top20["Name"]], fontsize=9)
    ax.set_xlabel("Composite Score (0-100)", fontsize=11)
    ax.set_title("📊 Top 20 Companies by Composite Score", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlim(0, 100)
    ax.grid(axis='x', alpha=0.3)
    
    for i, (bar, score) in enumerate(zip(bars, top20["Composite_Score"])):
        signal = top20.iloc[i].get("Signal", "")
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                f'{score:.0f} ({signal})', va='center', fontsize=8, color='#ccc')
    
    # Threshold lines
    for thresh, label, color in [(65, 'Buy', '#10b981'), (40, 'Hold', '#f59e0b')]:
        ax.axvline(x=thresh, color=color, linestyle='--', alpha=0.5, linewidth=1)
        ax.text(thresh + 0.5, len(top20) - 0.5, label, color=color, fontsize=8, alpha=0.7)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Chart saved: {output_path}")


def chart_pe_vs_roe(scored_df, output_path):
    """Scatter plot: P/E vs ROE with score coloring."""
    df = scored_df[(scored_df["PE"] > 0) & (scored_df["PE"] < 50) & (scored_df["ROE"] > -0.1)].copy()
    fig, ax = plt.subplots(figsize=(12, 8))
    
    sc = ax.scatter(df["PE"], df["ROE"] * 100, c=df["Composite_Score"],
                    cmap=RYG_CMAP, s=df["MarketCap"] / 1e9 * 2 + 30,
                    alpha=0.85, edgecolors='#555', linewidth=0.5, vmin=30, vmax=80)
    
    for ticker, row in df.iterrows():
        ax.annotate(ticker.replace('.PA','').replace('.DE','').replace('.MI','').replace('.AS','').replace('.MC',''),
                    (row["PE"], row["ROE"] * 100),
                    fontsize=7, color='#ccc', textcoords="offset points", xytext=(5, 5))
    
    # Quadrant lines
    ax.axvline(x=15, color='#3b82f6', linestyle='--', alpha=0.4, linewidth=1)
    ax.axhline(y=10, color='#3b82f6', linestyle='--', alpha=0.4, linewidth=1)
    ax.text(2, 38, 'VALUE\nHIGH QUALITY', fontsize=9, color='#10b981', alpha=0.5, fontweight='bold')
    ax.text(30, 38, 'EXPENSIVE\nHIGH QUALITY', fontsize=9, color='#f59e0b', alpha=0.5, fontweight='bold')
    ax.text(2, 2, 'CHEAP\nLOW QUALITY', fontsize=9, color='#ef4444', alpha=0.5, fontweight='bold')
    
    ax.set_xlabel("P/E Ratio (lower = cheaper)", fontsize=11)
    ax.set_ylabel("ROE % (higher = more profitable)", fontsize=11)
    ax.set_title("📈 Valuation vs Profitability Matrix", fontsize=14, fontweight='bold', pad=15)
    ax.grid(alpha=0.2)
    
    cbar = plt.colorbar(sc, ax=ax, shrink=0.8)
    cbar.set_label("Composite Score", fontsize=10)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Chart saved: {output_path}")


def chart_score_radar(scored_df, output_path, n=5):
    """Radar chart comparing top N companies across all categories."""
    categories = ["Valuation_Score", "Health_Score", "Profitability_Score",
                   "Growth_Score", "Shareholder_Score", "Risk_Score"]
    labels = ["Valuation", "Health", "Profitability", "Growth", "Shareholder", "Risk"]
    
    top_n = scored_df.head(n)
    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    ax.set_facecolor('#1a1a2e')
    
    colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6']
    for i, (ticker, row) in enumerate(top_n.iterrows()):
        values = [row.get(cat, 50) for cat in categories]
        values += values[:1]
        name = row.get("Name", ticker)[:20]
        ax.plot(angles, values, 'o-', linewidth=2, label=f'{name} ({row.get("Composite_Score",0):.0f})',
                color=colors[i % len(colors)], markersize=4)
        ax.fill(angles, values, alpha=0.08, color=colors[i % len(colors)])
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80])
    ax.set_yticklabels(['20', '40', '60', '80'], fontsize=8, color='#666')
    ax.set_title("🎯 Top 5 Companies — Score Radar", fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9, framealpha=0.5)
    ax.grid(color='#333', alpha=0.5)
    
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Chart saved: {output_path}")


def chart_dividend_vs_value(scored_df, output_path):
    """Scatter: Dividend yield vs P/E with market cap sizing."""
    df = scored_df[(scored_df["PE"] > 0) & (scored_df["DivYield"] > 0)].copy()
    fig, ax = plt.subplots(figsize=(12, 8))
    
    sc = ax.scatter(df["PE"], df["DivYield"] * 100, c=df["Composite_Score"],
                    cmap=RYG_CMAP, s=df["MarketCap"] / 1e9 * 1.5 + 20,
                    alpha=0.85, edgecolors='#555', linewidth=0.5, vmin=30, vmax=80)
    
    for ticker, row in df.iterrows():
        ax.annotate(ticker.split('.')[0], (row["PE"], row["DivYield"] * 100),
                    fontsize=7, color='#ccc', textcoords="offset points", xytext=(5, 3))
    
    # Highlight zone: low P/E + high dividend
    ax.axvspan(0, 15, alpha=0.05, color='#10b981')
    ax.axhspan(3.5, 10, alpha=0.05, color='#3b82f6')
    ax.text(2, 7.5, 'INCOME\nSWEET SPOT', fontsize=10, color='#10b981', alpha=0.4, fontweight='bold')
    
    ax.set_xlabel("P/E Ratio", fontsize=11)
    ax.set_ylabel("Dividend Yield %", fontsize=11)
    ax.set_title("💰 Dividend Yield vs Valuation", fontsize=14, fontweight='bold', pad=15)
    ax.grid(alpha=0.2)
    cbar = plt.colorbar(sc, ax=ax, shrink=0.8)
    cbar.set_label("Composite Score", fontsize=10)
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Chart saved: {output_path}")


def chart_sector_heatmap(scored_df, output_path):
    """Sector-level average scores heatmap."""
    cats = ["Composite_Score", "Valuation_Score", "Health_Score", "Profitability_Score", "Growth_Score"]
    cat_labels = ["Composite", "Valuation", "Health", "Profitability", "Growth"]
    
    sector_avg = scored_df.groupby("Sector")[cats].mean()
    sector_avg = sector_avg.sort_values("Composite_Score", ascending=True)
    
    fig, ax = plt.subplots(figsize=(12, max(5, len(sector_avg) * 0.6)))
    
    data = sector_avg.values
    im = ax.imshow(data, aspect='auto', cmap=RYG_CMAP, vmin=30, vmax=80)
    
    ax.set_xticks(range(len(cat_labels)))
    ax.set_xticklabels(cat_labels, fontsize=10)
    ax.set_yticks(range(len(sector_avg)))
    ax.set_yticklabels(sector_avg.index, fontsize=10)
    
    for i in range(len(sector_avg)):
        for j in range(len(cats)):
            val = data[i, j]
            color = '#000' if val > 60 else '#fff'
            ax.text(j, i, f'{val:.0f}', ha='center', va='center', fontsize=10, fontweight='bold', color=color)
    
    ax.set_title("🏭 Sector Score Heatmap", fontsize=14, fontweight='bold', pad=15)
    plt.colorbar(im, ax=ax, shrink=0.6, label="Score")
    
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✅ Chart saved: {output_path}")


def generate_all_charts(scored_df, output_dir):
    """Generate all analysis charts."""
    os.makedirs(output_dir, exist_ok=True)
    chart_composite_scores(scored_df, os.path.join(output_dir, "01_composite_scores.png"))
    chart_pe_vs_roe(scored_df, os.path.join(output_dir, "02_pe_vs_roe.png"))
    chart_score_radar(scored_df, os.path.join(output_dir, "03_radar_top5.png"))
    chart_dividend_vs_value(scored_df, os.path.join(output_dir, "04_dividend_vs_value.png"))
    chart_sector_heatmap(scored_df, os.path.join(output_dir, "05_sector_heatmap.png"))
    print(f"\n✅ All 5 charts generated in {output_dir}")


if __name__ == "__main__":
    df = get_universe_dataframe()
    scored = score_universe(df)
    generate_all_charts(scored, "/home/claude/invest/charts")
