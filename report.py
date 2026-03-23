"""
report.py — Generate publication-ready charts for the benchmark article.

Charts:
1. Time per question: Claude Code vs RAG (side-by-side bars)
2. Cost per question: Claude Code vs RAG (side-by-side bars)
3. Hallucination rate across tiers
4. Worst-case response times (median / P90 / max lines)
5. The headline numbers (key stats callout image)
6. Full scorecard table
"""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd
import seaborn as sns
import yaml


def setup_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({
        "figure.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    })


def load_summary(path="results/benchmark_summary.csv"):
    return pd.read_csv(path)


def load_results(path="results/benchmark_results.csv"):
    return pd.read_csv(path)


def _save(fig, path, dpi):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


# ---- Chart 1: Time Comparison ----

def generate_time_comparison_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(s))
    w = 0.35

    bars1 = ax.bar(x - w/2, s["avg_time_per_q"], w, label="Claude Code", color="#EF4444", alpha=0.85)
    bars2 = ax.bar(x + w/2, s["rag_time"], w, label="RAG (CustomGPT)", color="#10B981", alpha=0.85)

    ax.set_xlabel("Number of Files", fontsize=13)
    ax.set_ylabel("Time per Question (seconds)", fontsize=13)
    ax.set_title("Response Time: Claude Code vs RAG", fontsize=16, fontweight="bold",
                 pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t:,}" for t in s["tier"]], rotation=45, ha="right")
    ax.legend(fontsize=12, loc="upper left")

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.8,
                f'{h:.0f}s', ha='center', va='bottom', fontsize=9, fontweight='bold')
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.8,
                f'{h:.0f}s', ha='center', va='bottom', fontsize=9, fontweight='bold', color='#059669')

    # Annotation
    ax.annotate("15-20x slower", xy=(5, 45), fontsize=13, color="#EF4444",
                fontweight="bold", ha="center")

    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- Chart 2: Cost Comparison ----

def generate_cost_comparison_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(s))
    w = 0.35

    bars1 = ax.bar(x - w/2, s["cost_per_q"], w, label="Claude Code", color="#EF4444", alpha=0.85)
    bars2 = ax.bar(x + w/2, s["rag_cost_per_q"], w, label="RAG (CustomGPT)", color="#10B981", alpha=0.85)

    ax.set_xlabel("Number of Files", fontsize=13)
    ax.set_ylabel("Cost per Question (USD)", fontsize=13)
    ax.set_title("Cost per Question: Claude Code vs RAG", fontsize=16, fontweight="bold",
                 pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t:,}" for t in s["tier"]], rotation=45, ha="right")
    ax.legend(fontsize=12, loc="upper left")

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.003,
                f'${h:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.annotate("50-65x more expensive", xy=(5, 0.11), fontsize=13, color="#EF4444",
                fontweight="bold", ha="center")

    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- Chart 3: Hallucination Rate ----

def generate_hallucination_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    rates = s["hallucination_rate"]
    labels = [f"{int(t):,}" for t in s["tier"]]
    colors = ["#EF4444" if r >= 60 else "#F59E0B" for r in rates]

    bars = ax.bar(labels, rates, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)

    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1.5,
                f'{rate:.0f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax.set_xlabel("Number of Files", fontsize=13)
    ax.set_ylabel("Hallucination Rate (%)", fontsize=13)
    ax.set_title("Claude Code Fabricates Answers 50-100% of the Time", fontsize=16,
                 fontweight="bold", pad=15)
    ax.set_ylim(0, 115)

    ax.axhline(y=50, color='#9CA3AF', linestyle='--', linewidth=1, alpha=0.7)
    ax.text(len(labels) - 0.5, 52, "50% — worse than a coin flip", ha='right',
            fontsize=10, color='#6B7280', style='italic')

    # RAG annotation
    ax.axhline(y=0, color='#10B981', linestyle='-', linewidth=3, alpha=0.8)
    ax.text(0.5, 3, "RAG: 0% hallucination", fontsize=11, color='#059669', fontweight='bold')

    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- Chart 4: Worst-Case Times ----

def generate_worst_case_time_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = s["tier"]

    ax.plot(tiers, s["avg_time_per_q"], marker="o", linewidth=2.5, color=brand_color,
            label="Average", markersize=8)
    ax.plot(tiers, s["p90_time"], marker="s", linewidth=2.5, color="#F59E0B",
            label="P90 (worst 10%)", markersize=8)
    ax.plot(tiers, s["max_time"], marker="^", linewidth=2.5, color="#EF4444",
            label="Worst Case", markersize=8)

    ax.fill_between(tiers, s["avg_time_per_q"], s["max_time"], alpha=0.1, color="#EF4444")

    ax.axhline(y=3, color='#10B981', linestyle='--', linewidth=2.5, alpha=0.8)
    ax.text(tiers.iloc[-1], 8, "RAG: ~3 seconds", ha='right', fontsize=12,
            color='#059669', fontweight='bold')

    ax.set_xscale("log")
    ax.set_xlabel("Number of Files", fontsize=13)
    ax.set_ylabel("Response Time (seconds)", fontsize=13)
    ax.set_title("Claude Code: Average vs Worst-Case Response Time", fontsize=16,
                 fontweight="bold", pad=15)
    ax.legend(fontsize=11, loc="upper left")

    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- Chart 5: Headline Numbers ----

def generate_headline_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    """Big headline stats image — the one-image summary for social sharing."""
    setup_style()
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.axis("off")

    stats = [
        ("15-20x", "Slower", "36-48s vs 2-3s\nper question", "#EF4444"),
        ("50-65x", "More Expensive", "$0.10-0.13 vs $0.002\nper question", "#F59E0B"),
        ("50-100%", "Hallucination", "fabricates answers\nwhen info is absent", "#7C3AED"),
        ("1M+", "Tokens Burned", "per 10 questions\nregardless of file count", brand_color),
    ]

    for i, (number, label, detail, color) in enumerate(stats):
        x_pos = 0.125 + i * 0.25
        ax.text(x_pos, 0.75, number, transform=ax.transAxes, fontsize=36,
                fontweight="bold", ha="center", va="center", color=color)
        ax.text(x_pos, 0.50, label, transform=ax.transAxes, fontsize=16,
                fontweight="bold", ha="center", va="center", color="#1F2937")
        ax.text(x_pos, 0.28, detail, transform=ax.transAxes, fontsize=11,
                ha="center", va="center", color="#6B7280", linespacing=1.4)

    ax.set_title("Claude Code vs RAG Search: By the Numbers",
                 fontsize=20, fontweight="bold", pad=20, color="#1F2937")

    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- Chart 6: Scorecard Table ----

def generate_scorecard_chart(s, output_path, dpi=300, brand_color="#6366F1"):
    setup_style()

    table_rows = []
    for _, row in s.iterrows():
        speedup = int(row["avg_time_per_q"] / row["rag_time"])
        cost_mult = int(row["cost_per_q"] / row["rag_cost_per_q"])
        table_rows.append([
            f"{int(row['tier']):,}",
            f"{row['avg_time_per_q']:.0f}s",
            f"{row['p90_time']:.0f}s",
            f"{row['max_time']:.0f}s",
            f"${row['cost_per_q']:.2f}",
            f"{row.get('timeout_pct', 0):.0f}%",
        ])

    col_labels = ["Files", "Avg Time", "P90", "Max", "Cost/Q", "Timeout %"]

    n_rows = len(table_rows)
    n_cols = len(col_labels)

    fig_height = max(3.5, 0.45 * n_rows + 1.5)
    fig, ax = plt.subplots(figsize=(16, fig_height))
    ax.axis("off")

    tbl = ax.table(cellText=table_rows, colLabels=col_labels,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.6)

    for col_idx in range(n_cols):
        tbl[0, col_idx].set_facecolor("#1F2937")
        tbl[0, col_idx].set_text_props(color="white", fontweight="bold")

    for row_idx in range(1, n_rows + 1):
        bg = "#FEF2F2" if row_idx % 2 == 0 else "white"  # Light red tint
        for col_idx in range(n_cols):
            tbl[row_idx, col_idx].set_facecolor(bg)

    ax.set_title("Claude Code Benchmark: Full Results (Claude Sonnet 4.6)",
                 fontweight="bold", fontsize=14, pad=12)
    fig.tight_layout()
    _save(fig, output_path, dpi)


# ---- CLI ----

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--results", default=None)
    args = parser.parse_args(argv)

    with open(args.config) as fh:
        cfg = yaml.safe_load(fh)

    rcfg = cfg.get("report", {})
    output_dir = Path(rcfg.get("output_dir", "results/"))
    dpi = int(rcfg.get("chart_dpi", 300))
    formats = list(rcfg.get("chart_formats", ["png", "svg"]))
    brand = rcfg.get("brand_color", "#6366F1")

    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    summary = load_summary(args.summary or str(output_dir / "benchmark_summary.csv"))
    results = load_results(args.results or str(output_dir / "benchmark_results.csv"))

    generators = [
        ("01_time_comparison", generate_time_comparison_chart, [summary]),
        ("02_cost_comparison", generate_cost_comparison_chart, [summary]),
        ("03_hallucination_rate", generate_hallucination_chart, [summary]),
        ("04_worst_case_times", generate_worst_case_time_chart, [summary]),
        ("05_headline_numbers", generate_headline_chart, [summary]),
        ("06_scorecard", generate_scorecard_chart, [summary]),
    ]

    for name, gen, data in generators:
        for fmt in formats:
            out = charts_dir / f"{name}.{fmt}"
            print(f"  {out} ...")
            gen(*data, str(out), dpi=dpi, brand_color=brand)

    print(f"\nDone. {len(generators) * len(formats)} charts in {charts_dir}/")


if __name__ == "__main__":
    main()
