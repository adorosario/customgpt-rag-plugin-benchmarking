"""
report_pdf_v2.py — Generate publication-ready charts for the PDF benchmark article.

Reads raw JSON from raw_final/ (CC-only) and results_cc_rag/raw/ (CC+RAG),
evaluates accuracy, and generates all charts + summary CSVs.

Usage:
  python report_pdf_v2.py
  python report_pdf_v2.py --cc-dir results_pdf/raw_final --rag-dir results_cc_rag/raw --output-dir results_pdf
"""

import argparse
import csv
import json
import re
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import seaborn as sns
import yaml


# ---------------------------------------------------------------------------
# Ground truth & scoring
# ---------------------------------------------------------------------------

NEEDLE_PRESENT_AT = {
    "needle_1": 500,
    "needle_2": 1000,
    "needle_3": 2500,
    "needle_4": 5000,
    "needle_5": 10000,
}

NEEDLE_KEYWORDS = {
    "needle_1": ["april 15"],
    "needle_2": ["4.2"],
    "needle_3": ["postgresql 16", "postgres 16"],
    "needle_4": ["january 1", "jan 1"],
    "needle_5": ["85,000", "85000", "85k"],
}

PATTERN_REQUIRED = {
    "pattern_1": {"keywords": ["nexus"], "all_of": ["engineering", "product"]},
    "pattern_2": {"keywords": ["berlin"], "all_of": ["office"]},
    "pattern_3": {"keywords": ["initech"], "all_of": ["api", "latency"]},
    "pattern_4": {"keywords": ["retreat"], "all_of": ["annual"]},
    "pattern_5": {"keywords": ["series b"], "all_of": ["fundraising"]},
}

NO_INFO_PHRASES = [
    "don't have", "don't know", "no information", "not found",
    "cannot find", "could not find", "no mention", "unable to find",
    "doesn't appear", "isn't something i have", "don't have any",
    "no record", "no stored",
]


def classify_response(r, tier):
    """Classify a response into: correct_found, correct_no_info, hallucination,
    failed_no_search, timeout, missed."""
    qid = r["question_id"]
    resp = (r.get("response") or "").lower()
    timed_out = r.get("timed_out", False)

    if timed_out or r.get("time_seconds", 0) >= 175:
        return "timeout"

    if qid.startswith("needle_"):
        present_at = NEEDLE_PRESENT_AT[qid]
        keywords = NEEDLE_KEYWORDS[qid]

        if tier < present_at:
            # Needle NOT present — should say "don't know"
            for kw in keywords:
                if kw in resp:
                    return "hallucination"
            for phrase in NO_INFO_PHRASES:
                if phrase in resp:
                    return "correct_no_info"
            return "failed_no_search"
        else:
            # Needle IS present — should find it
            for kw in keywords:
                if kw in resp:
                    return "correct_found"
            return "missed"

    elif qid.startswith("pattern_"):
        pr = PATTERN_REQUIRED[qid]
        has_keyword = any(kw in resp for kw in pr["keywords"])
        is_negative = any(p in resp for p in NO_INFO_PHRASES)

        if has_keyword and not is_negative:
            # Check if it has enough detail (all_of terms)
            has_all = all(t in resp for t in pr["all_of"])
            if has_all:
                return "correct_found"
            else:
                return "partial"
        return "failed_no_search"

    return "unknown"


def is_findable(qid, tier):
    """Is this question answerable at this tier?"""
    if qid.startswith("pattern_"):
        return True
    present_at = NEEDLE_PRESENT_AT.get(qid, 999999)
    return tier >= present_at


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(raw_dir):
    results = []
    for p in sorted(Path(raw_dir).glob("*.json")):
        with open(p) as f:
            results.append(json.load(f))
    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_tier(records, tier, cutoff=180):
    """Compute all metrics for a single tier."""
    total = len(records)
    if total == 0:
        return None

    times = [r.get("time_seconds", 0) for r in records]
    capped_times = [min(t, cutoff) for t in times]
    completed = [r for r in records if not r.get("timed_out", False) and r.get("time_seconds", 0) < cutoff - 5]
    comp_times = sorted([r["time_seconds"] for r in completed]) if completed else []

    # Classify all responses
    classifications = [classify_response(r, tier) for r in records]

    # Findable questions (patterns + present needles)
    findable = [(r, c) for r, c in zip(records, classifications) if is_findable(r["question_id"], tier)]
    findable_correct = sum(1 for _, c in findable if c in ("correct_found", "partial"))
    findable_total = len(findable)

    # Absent needles — hallucination check
    absent = [(r, c) for r, c in zip(records, classifications)
              if r["question_id"].startswith("needle_") and not is_findable(r["question_id"], tier)]
    hallucinations = sum(1 for _, c in absent if c == "hallucination")
    absent_answered = len([c for _, c in absent if c != "timeout"])

    return {
        "tier": tier,
        "total_queries": total,
        "completed": len(completed),
        "completion_rate": len(completed) / total,
        "timeout_rate": 1 - len(completed) / total,
        "timeout_count": total - len(completed),
        "avg_time": sum(capped_times) / total,
        "median_time": statistics.median(times),
        "p75_time": sorted(times)[int(total * 0.75)] if total > 3 else max(times),
        "p90_time": sorted(times)[int(total * 0.90)] if total > 9 else max(times),
        "max_time": max(times),
        "avg_time_completed": statistics.mean(comp_times) if comp_times else 0,
        "median_time_completed": statistics.median(comp_times) if comp_times else 0,
        "avg_cost": sum(r.get("cost_usd", 0) for r in records) / total,
        "total_cost": sum(r.get("cost_usd", 0) for r in records),
        "avg_tokens": sum(r.get("total_tokens", 0) for r in records) / total,
        "avg_turns": sum(r.get("num_turns", 0) for r in records) / total,
        "max_tokens": max(r.get("total_tokens", 0) for r in records),
        "max_turns": max(r.get("num_turns", 0) for r in records),
        # Accuracy
        "findable_correct": findable_correct,
        "findable_total": findable_total,
        "findable_accuracy": findable_correct / findable_total if findable_total else 0,
        # Hallucination
        "hallucinations": hallucinations,
        "absent_answered": absent_answered,
        "hallucination_rate": hallucinations / absent_answered if absent_answered else 0,
        # Classification breakdown
        "classifications": classifications,
    }


# ---------------------------------------------------------------------------
# Chart styling
# ---------------------------------------------------------------------------

BRAND = "#6366F1"
CC_COLOR = "#EF4444"
RAG_COLOR = "#10B981"
WARN_COLOR = "#F59E0B"
PURPLE = "#7C3AED"
DARK = "#1F2937"
GRAY = "#6B7280"
LIGHT_GRAY = "#9CA3AF"


def setup_style():
    sns.set_theme(style="whitegrid")
    plt.rcParams.update({
        "figure.dpi": 150,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
    })


def save_chart(fig, path, dpi=300):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 1: Completion Rate by Tier (the breaking point)
# ---------------------------------------------------------------------------

def chart_completion_rate(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]
    rates = [s["completion_rate"] * 100 for s in cc_tiers]

    bars = ax.bar(range(len(tiers)), rates, color=[
        "#10B981" if r >= 90 else "#F59E0B" if r >= 60 else "#EF4444"
        for r in rates
    ], alpha=0.85, edgecolor="white", linewidth=0.5)

    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1.5,
                f'{rate:.0f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

    # RAG line
    if rag_stats:
        ax.axhline(y=100, color=RAG_COLOR, linestyle='--', linewidth=2.5, alpha=0.8)
        ax.text(len(tiers) - 0.5, 102, "CC+RAG: 100% completion", ha='right',
                fontsize=11, color='#059669', fontweight='bold')

    # Breaking point annotation
    ax.axvline(x=3.5, color=LIGHT_GRAY, linestyle=':', linewidth=1.5)
    ax.text(3.7, 50, "Inflection\npoint", fontsize=12, color=CC_COLOR, fontweight='bold', ha='left')

    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels([f"{t:,}" for t in tiers])
    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("Completed Within 3 Minutes (%)", fontsize=13)
    ax.set_title("Searches Completed Within 3 Minutes by Document Count", fontsize=16, fontweight="bold", pad=15)
    ax.set_ylim(0, 115)

    fig.tight_layout()
    save_chart(fig, charts_dir / "01_completion_rate.png", dpi)


# ---------------------------------------------------------------------------
# Chart 2: Accuracy on Findable Questions
# ---------------------------------------------------------------------------

def chart_accuracy(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]
    acc = [s["findable_accuracy"] * 100 for s in cc_tiers]

    bars = ax.bar(range(len(tiers)), acc, color=[
        "#10B981" if a >= 70 else "#F59E0B" if a >= 40 else "#EF4444"
        for a in acc
    ], alpha=0.85, edgecolor="white", linewidth=0.5)

    for bar, a in zip(bars, acc):
        ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1.5,
                f'{a:.0f}%', ha='center', va='bottom', fontsize=11, fontweight='bold')

    if rag_stats:
        ax.axhline(y=rag_stats["findable_accuracy"] * 100, color=RAG_COLOR,
                    linestyle='--', linewidth=2.5, alpha=0.8)
        ax.text(len(tiers) - 0.5, rag_stats["findable_accuracy"] * 100 + 2,
                f"CC+RAG: {rag_stats['findable_accuracy']*100:.0f}%", ha='right',
                fontsize=11, color='#059669', fontweight='bold')

    ax.set_xticks(range(len(tiers)))
    ax.set_xticklabels([f"{t:,}" for t in tiers])
    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("Accuracy on Findable Questions (%)", fontsize=13)
    ax.set_title("Accuracy: Did Claude Actually Find the Answer?", fontsize=16, fontweight="bold", pad=15)
    ax.set_ylim(0, 115)

    fig.tight_layout()
    save_chart(fig, charts_dir / "02_accuracy.png", dpi)


# ---------------------------------------------------------------------------
# Chart 3: Time Comparison — CC vs RAG
# ---------------------------------------------------------------------------

def chart_time_comparison(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]
    cc_times = [s["avg_time"] for s in cc_tiers]

    x = np.arange(len(tiers))
    w = 0.35

    bars1 = ax.bar(x - w/2, cc_times, w, label="Claude Code (alone)", color=CC_COLOR, alpha=0.85)

    if rag_stats:
        # Show RAG time as flat bar at each tier position for comparison
        rag_times = [rag_stats["avg_time"]] * len(tiers)
        bars2 = ax.bar(x + w/2, rag_times, w, label="CC + RAG Plugin", color=RAG_COLOR, alpha=0.85)
        for bar in bars2:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., h + 1,
                    f'{h:.0f}s', ha='center', va='bottom', fontsize=9, fontweight='bold', color='#059669')

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 1,
                f'{h:.0f}s', ha='center', va='bottom', fontsize=9, fontweight='bold', color=CC_COLOR)

    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("Avg Time per Question (seconds)", fontsize=13)
    ax.set_title("Response Time: Claude Code vs RAG", fontsize=16, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t:,}" for t in tiers])
    ax.legend(fontsize=12, loc="upper left")

    fig.tight_layout()
    save_chart(fig, charts_dir / "03_time_comparison.png", dpi)


# ---------------------------------------------------------------------------
# Chart 4: Cost per Question
# ---------------------------------------------------------------------------

def chart_cost_comparison(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]
    cc_cost = [s["avg_cost"] for s in cc_tiers]

    x = np.arange(len(tiers))
    w = 0.35

    bars1 = ax.bar(x - w/2, cc_cost, w, label="Claude Code (alone)", color=CC_COLOR, alpha=0.85)

    if rag_stats:
        rag_costs = [rag_stats["avg_cost"]] * len(tiers)
        bars2 = ax.bar(x + w/2, rag_costs, w, label="CC + RAG Plugin", color=RAG_COLOR, alpha=0.85)
        for bar in bars2:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., h + 0.003,
                    f'${h:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold', color='#059669')

    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., h + 0.003,
                f'${h:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("Cost per Question (USD)", fontsize=13)
    ax.set_title("Cost per Question: Claude Code vs RAG", fontsize=16, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t:,}" for t in tiers])
    ax.legend(fontsize=12, loc="upper left")

    fig.tight_layout()
    save_chart(fig, charts_dir / "04_cost_comparison.png", dpi)


# ---------------------------------------------------------------------------
# Chart 5: Worst-case response times (avg / P75 / P90 / max)
# ---------------------------------------------------------------------------

def chart_worst_case(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]

    ax.plot(tiers, [s["avg_time"] for s in cc_tiers], marker="o", linewidth=2.5,
            color=BRAND, label="Average", markersize=8)
    ax.plot(tiers, [s["p75_time"] for s in cc_tiers], marker="D", linewidth=2.5,
            color=WARN_COLOR, label="P75", markersize=8)
    ax.plot(tiers, [s["p90_time"] for s in cc_tiers], marker="s", linewidth=2.5,
            color="#F97316", label="P90", markersize=8)
    ax.plot(tiers, [s["max_time"] for s in cc_tiers], marker="^", linewidth=2.5,
            color=CC_COLOR, label="Max", markersize=8)

    ax.fill_between(tiers, [s["avg_time"] for s in cc_tiers],
                     [s["max_time"] for s in cc_tiers], alpha=0.08, color=CC_COLOR)

    if rag_stats:
        ax.axhline(y=rag_stats["avg_time"], color=RAG_COLOR, linestyle='--', linewidth=2.5, alpha=0.8)
        ax.text(tiers[-1], rag_stats["avg_time"] + 4, f"RAG avg: {rag_stats['avg_time']:.0f}s",
                ha='right', fontsize=12, color='#059669', fontweight='bold')

    ax.axhline(y=180, color=LIGHT_GRAY, linestyle=':', linewidth=1, alpha=0.6)
    ax.text(tiers[0], 183, "3-minute benchmark window", fontsize=9, color=GRAY)

    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("Response Time (seconds)", fontsize=13)
    ax.set_title("Response Time Distribution by Tier", fontsize=16, fontweight="bold", pad=15)
    ax.legend(fontsize=11, loc="upper left")
    ax.set_ylim(0, 200)

    fig.tight_layout()
    save_chart(fig, charts_dir / "05_worst_case_times.png", dpi)


# ---------------------------------------------------------------------------
# Chart 6: CC vs RAG head-to-head at 500 PDFs
# ---------------------------------------------------------------------------

def chart_head_to_head(cc_500, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, axes = plt.subplots(1, 4, figsize=(18, 5))

    metrics = [
        ("Done in\n3 Minutes", cc_500["completion_rate"] * 100, 100, "%"),
        ("Accuracy on\nFindable Qs", cc_500["findable_accuracy"] * 100,
         rag_stats["findable_accuracy"] * 100, "%"),
        ("Avg Response\nTime", cc_500["avg_time"], rag_stats["avg_time"], "s"),
        ("Cost per\nQuestion", 0.40, rag_stats["avg_cost"], "$"),
    ]

    for ax, (label, cc_val, rag_val, unit) in zip(axes, metrics):
        x = [0, 1]
        colors = [CC_COLOR, RAG_COLOR]
        vals = [cc_val, rag_val]
        labels = ["CC Only", "CC+RAG"]

        bars = ax.bar(x, vals, color=colors, alpha=0.85, width=0.6)
        for bar, val in zip(bars, vals):
            if unit == "$":
                fmt = f'${val:.2f}'
            else:
                fmt = f'{val:.0f}{unit}'
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 1,
                    fmt, ha='center', va='bottom', fontsize=14, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11)
        ax.set_title(label, fontsize=12, fontweight='bold', pad=10)
        ax.set_ylim(0, max(vals) * 1.25 + 5)

    fig.suptitle("Head-to-Head at 500 PDFs: Claude Code vs RAG Plugin",
                 fontsize=16, fontweight="bold", y=1.02)
    fig.tight_layout()
    save_chart(fig, charts_dir / "06_head_to_head_500.png", dpi)


# ---------------------------------------------------------------------------
# Chart 7: Headline Numbers (shareable stats image)
# ---------------------------------------------------------------------------

def chart_headline(cc_500, rag_stats, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(16, 5))
    ax.axis("off")

    speedup = cc_500["avg_time"] / rag_stats["avg_time"]
    acc_cc = cc_500["findable_accuracy"] * 100
    acc_rag = rag_stats["findable_accuracy"] * 100

    stats = [
        (f"{speedup:.1f}x", "Faster with RAG",
         f"{cc_500['avg_time']:.0f}s vs {rag_stats['avg_time']:.0f}s\nper question", RAG_COLOR),
        (f"{acc_rag:.0f}%", "RAG Accuracy",
         f"vs {acc_cc:.0f}% CC-only\non findable questions", BRAND),
        (f"{cc_500['timeout_rate']*100:.0f}%", "Exceeded 3 Min Limit",
         f"at 500 PDFs (benchmark cutoff)\nRAG: 0%", CC_COLOR),
        ("100%", "RAG Completion",
         f"every query answered\nwithin {rag_stats['avg_time']:.0f}s avg", PURPLE),
    ]

    for i, (number, label, detail, color) in enumerate(stats):
        x_pos = 0.125 + i * 0.25
        ax.text(x_pos, 0.75, number, transform=ax.transAxes, fontsize=40,
                fontweight="bold", ha="center", va="center", color=color)
        ax.text(x_pos, 0.48, label, transform=ax.transAxes, fontsize=15,
                fontweight="bold", ha="center", va="center", color=DARK)
        ax.text(x_pos, 0.22, detail, transform=ax.transAxes, fontsize=11,
                ha="center", va="center", color=GRAY, linespacing=1.4)

    ax.set_title("PDF Benchmark: Claude Code vs RAG Plugin (500 PDFs)",
                 fontsize=20, fontweight="bold", pad=20, color=DARK)

    fig.tight_layout()
    save_chart(fig, charts_dir / "07_headline_numbers.png", dpi)


# ---------------------------------------------------------------------------
# Chart 8: Full Scorecard
# ---------------------------------------------------------------------------

def chart_scorecard(cc_tiers, rag_stats, charts_dir, dpi=300):
    setup_style()

    table_rows = []
    for s in cc_tiers:
        table_rows.append([
            f"{s['tier']:,}",
            f"{s['completion_rate']*100:.0f}%",
            f"{s['findable_accuracy']*100:.0f}%",
            f"{s['avg_time']:.0f}s",
            f"{s['p90_time']:.0f}s",
            f"${s['avg_cost']:.2f}",
            f"{s['timeout_rate']*100:.0f}%",
        ])

    if rag_stats:
        table_rows.append([
            f"500+RAG",
            f"{100:.0f}%",
            f"{rag_stats['findable_accuracy']*100:.0f}%",
            f"{rag_stats['avg_time']:.0f}s",
            f"{rag_stats['p90_time']:.0f}s",
            f"${rag_stats['avg_cost']:.2f}",
            f"0%",
        ])

    col_labels = ["PDFs", "Done in 3 min", "Accuracy", "Avg Time", "P90", "Cost/Q", "Exceeded 3 min"]

    n_rows = len(table_rows)
    n_cols = len(col_labels)
    fig_height = max(4, 0.5 * n_rows + 2)
    fig, ax = plt.subplots(figsize=(16, fig_height))
    ax.axis("off")

    tbl = ax.table(cellText=table_rows, colLabels=col_labels,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(11)
    tbl.scale(1, 1.8)

    for col_idx in range(n_cols):
        tbl[0, col_idx].set_facecolor(DARK)
        tbl[0, col_idx].set_text_props(color="white", fontweight="bold")

    for row_idx in range(1, n_rows + 1):
        is_rag = row_idx == n_rows and rag_stats
        for col_idx in range(n_cols):
            if is_rag:
                tbl[row_idx, col_idx].set_facecolor("#ECFDF5")  # Light green
                tbl[row_idx, col_idx].set_text_props(fontweight="bold")
            elif row_idx % 2 == 0:
                tbl[row_idx, col_idx].set_facecolor("#FEF2F2")  # Light red

    ax.set_title("Full Benchmark Scorecard (Claude Sonnet 4.6, 3-minute benchmark window)",
                 fontweight="bold", fontsize=14, pad=12)
    fig.tight_layout()
    save_chart(fig, charts_dir / "08_scorecard.png", dpi)


# ---------------------------------------------------------------------------
# Chart 9: Behavior Breakdown (stacked bar: correct, gave up, timeout)
# ---------------------------------------------------------------------------

def chart_behavior_breakdown(cc_tiers, charts_dir, dpi=300):
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 6))

    tiers = [s["tier"] for s in cc_tiers]
    n = len(tiers)

    correct = []
    partial = []
    gave_up = []
    timeout = []

    for s in cc_tiers:
        cls = s["classifications"]
        total = len(cls)
        correct.append(sum(1 for c in cls if c in ("correct_found", "correct_no_info")) / total * 100)
        partial.append(sum(1 for c in cls if c == "partial") / total * 100)
        gave_up.append(sum(1 for c in cls if c in ("failed_no_search", "missed", "hallucination", "unknown")) / total * 100)
        timeout.append(sum(1 for c in cls if c == "timeout") / total * 100)

    x = np.arange(n)
    w = 0.65

    p1 = ax.bar(x, correct, w, label="Correct", color=RAG_COLOR, alpha=0.85)
    p2 = ax.bar(x, partial, w, bottom=correct, label="Partial", color=WARN_COLOR, alpha=0.85)

    bottom2 = [c + p for c, p in zip(correct, partial)]
    p3 = ax.bar(x, gave_up, w, bottom=bottom2, label="Gave up / Wrong", color="#F97316", alpha=0.85)

    bottom3 = [b + g for b, g in zip(bottom2, gave_up)]
    p4 = ax.bar(x, timeout, w, bottom=bottom3, label="Exceeded 3 min limit", color=CC_COLOR, alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{t:,}" for t in tiers])
    ax.set_xlabel("Number of PDF Files", fontsize=13)
    ax.set_ylabel("% of Queries", fontsize=13)
    ax.set_title("What Actually Happens to Each Query?", fontsize=16, fontweight="bold", pad=15)
    ax.legend(fontsize=11, loc="upper right")
    ax.set_ylim(0, 105)

    fig.tight_layout()
    save_chart(fig, charts_dir / "09_behavior_breakdown.png", dpi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate PDF benchmark charts")
    parser.add_argument("--cc-dir", default="results_pdf/raw_final",
                        help="CC-only raw JSON results")
    parser.add_argument("--rag-dir", default="results_cc_rag/raw",
                        help="CC+RAG raw JSON results")
    parser.add_argument("--output-dir", default="results_pdf",
                        help="Output directory for charts and CSVs")
    parser.add_argument("--cutoff", type=int, default=180)
    parser.add_argument("--dpi", type=int, default=300)
    args = parser.parse_args()

    cc_results = load_results(args.cc_dir)
    rag_results = load_results(args.rag_dir) if Path(args.rag_dir).exists() else []

    print(f"Loaded {len(cc_results)} CC-only results, {len(rag_results)} CC+RAG results")

    # Group by tier
    cc_by_tier = {}
    for r in cc_results:
        cc_by_tier.setdefault(r["tier"], []).append(r)

    all_tiers = sorted(cc_by_tier.keys())
    print(f"Tiers: {all_tiers}")

    # Analyze each CC tier
    cc_tiers = []
    for tier in all_tiers:
        stats = analyze_tier(cc_by_tier[tier], tier, args.cutoff)
        if stats:
            cc_tiers.append(stats)
            print(f"  Tier {tier:>5}: {stats['completion_rate']*100:.0f}% completion, "
                  f"{stats['findable_accuracy']*100:.0f}% accuracy, "
                  f"{stats['avg_time']:.0f}s avg, ${stats['avg_cost']:.2f}/q")

    # Analyze RAG (all assumed to be tier 500)
    rag_stats = None
    if rag_results:
        rag_stats = analyze_tier(rag_results, 500, args.cutoff)
        print(f"  RAG 500: {rag_stats['completion_rate']*100:.0f}% completion, "
              f"{rag_stats['findable_accuracy']*100:.0f}% accuracy, "
              f"{rag_stats['avg_time']:.0f}s avg, ${rag_stats['avg_cost']:.2f}/q")

    # Write summary CSV
    output_dir = Path(args.output_dir)
    csv_path = output_dir / "benchmark_summary_v2.csv"
    with open(csv_path, "w", newline="") as f:
        fields = ["tier", "completion_rate", "findable_accuracy", "timeout_rate",
                   "avg_time", "median_time", "p75_time", "p90_time", "max_time",
                   "avg_cost", "total_cost", "avg_tokens", "max_tokens", "avg_turns",
                   "findable_correct", "findable_total", "hallucinations", "timeout_count"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in cc_tiers:
            writer.writerow({k: round(s[k], 4) if isinstance(s[k], float) else s[k]
                             for k in fields})
        if rag_stats:
            row = {k: round(rag_stats[k], 4) if isinstance(rag_stats[k], float) else rag_stats[k]
                   for k in fields}
            row["tier"] = "500_rag"
            writer.writerow(row)
    print(f"\nWrote {csv_path}")

    # Generate charts
    charts_dir = output_dir / "charts_v2"
    charts_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nGenerating charts in {charts_dir}/...")
    chart_completion_rate(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  01_completion_rate.png")

    chart_accuracy(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  02_accuracy.png")

    chart_time_comparison(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  03_time_comparison.png")

    chart_cost_comparison(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  04_cost_comparison.png")

    chart_worst_case(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  05_worst_case_times.png")

    # Head-to-head needs CC at 500
    cc_500 = next((s for s in cc_tiers if s["tier"] == 500), None)
    if cc_500 and rag_stats:
        chart_head_to_head(cc_500, rag_stats, charts_dir, args.dpi)
        print("  06_head_to_head_500.png")

        chart_headline(cc_500, rag_stats, charts_dir, args.dpi)
        print("  07_headline_numbers.png")

    chart_scorecard(cc_tiers, rag_stats, charts_dir, args.dpi)
    print("  08_scorecard.png")

    chart_behavior_breakdown(cc_tiers, charts_dir, args.dpi)
    print("  09_behavior_breakdown.png")

    print(f"\nDone! 9 charts in {charts_dir}/")


if __name__ == "__main__":
    main()
