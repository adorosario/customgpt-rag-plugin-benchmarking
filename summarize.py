"""Summarize benchmark results into a clean comparison table.

Usage:
  python summarize.py                          # defaults
  python summarize.py --cc-dir results_pdf/raw_v2 --cutoff 180
  python summarize.py --cc-dir results_pdf/raw_v2 --rag-dir results_cc_rag/raw --cutoff 180 --csv out.csv
"""

import argparse
import csv
import json
from pathlib import Path


def load_results(raw_dir: Path) -> list[dict]:
    results = []
    for p in sorted(raw_dir.glob("*.json")):
        with open(p) as f:
            results.append(json.load(f))
    return results


def extract_tier(record: dict) -> int:
    if "tier" in record:
        return record["tier"]
    return 500


def summarize_group(records: list[dict], cutoff: int) -> dict:
    times = [r.get("time_seconds", 0) for r in records]
    total = len(times)
    completed = [t for t in times if t < cutoff]
    capped_times = [min(t, cutoff) for t in times]

    return {
        "total_queries": total,
        "completed": len(completed),
        "completion_rate": len(completed) / total if total else 0,
        "avg_time": sum(capped_times) / total if total else 0,
        "avg_time_completed_only": sum(completed) / len(completed) if completed else 0,
        "max_time": max(times) if times else 0,
        "min_time": min(times) if times else 0,
        "avg_cost": sum(r.get("cost_usd", 0) for r in records) / total if total else 0,
        "total_cost": sum(r.get("cost_usd", 0) for r in records),
    }


def main():
    parser = argparse.ArgumentParser(description="Summarize benchmark results")
    parser.add_argument("--cc-dir", default="results_pdf/raw",
                        help="Directory with CC-only raw JSON results")
    parser.add_argument("--rag-dir", default="results_cc_rag/raw",
                        help="Directory with CC+RAG raw JSON results")
    parser.add_argument("--cutoff", type=int, default=180,
                        help="Uniform timeout cutoff in seconds (default: 180)")
    parser.add_argument("--tiers", type=int, nargs="+", default=None,
                        help="Only show these tiers")
    parser.add_argument("--csv", default=None,
                        help="Write results to CSV file")
    args = parser.parse_args()

    cutoff_min = args.cutoff / 60

    cc_dir = Path(args.cc_dir)
    cc_results = load_results(cc_dir) if cc_dir.exists() else []

    cc_by_tier = {}
    for r in cc_results:
        tier = extract_tier(r)
        cc_by_tier.setdefault(tier, []).append(r)

    rag_dir = Path(args.rag_dir)
    rag_results = load_results(rag_dir) if rag_dir.exists() else []

    rag_by_tier = {}
    for r in rag_results:
        tier = extract_tier(r)
        rag_by_tier.setdefault(tier, []).append(r)

    all_tiers = sorted(set(list(cc_by_tier.keys()) + list(rag_by_tier.keys())))
    if args.tiers:
        all_tiers = [t for t in all_tiers if t in args.tiers]

    print(f"\n{'='*80}")
    print(f"BENCHMARK SUMMARY (uniform {args.cutoff}s / {cutoff_min:.0f}-min cutoff)")
    print(f"{'='*80}")
    print(f"CC-only data: {cc_dir} ({len(cc_results)} records)")
    print(f"CC+RAG data:  {rag_dir} ({len(rag_results)} records)")
    print(f"{'='*80}\n")

    header = f"{'PDFs':>6} | {'CC Avg':>8} | {'CC Done':>10} | {'RAG Avg':>8} | {'RAG Done':>10} | {'CC Cost':>8} | {'RAG Cost':>8}"
    print(header)
    print("-" * len(header))

    rows = []
    for tier in all_tiers:
        cc_data = cc_by_tier.get(tier, [])
        rag_data = rag_by_tier.get(tier, [])

        cc_s = summarize_group(cc_data, args.cutoff) if cc_data else None
        rag_s = summarize_group(rag_data, args.cutoff) if rag_data else None

        cc_avg = f"{cc_s['avg_time']:.0f}s" if cc_s else "—"
        cc_done = f"{cc_s['completion_rate']*100:.0f}%" if cc_s else "—"
        cc_cost = f"${cc_s['avg_cost']:.2f}" if cc_s else "—"

        rag_avg = f"{rag_s['avg_time']:.0f}s" if rag_s else "—"
        rag_done = f"{rag_s['completion_rate']*100:.0f}%" if rag_s else "—"
        rag_cost = f"${rag_s['avg_cost']:.2f}" if rag_s else "—"

        print(f"{tier:>6} | {cc_avg:>8} | {cc_done:>10} | {rag_avg:>8} | {rag_done:>10} | {cc_cost:>8} | {rag_cost:>8}")

        rows.append({
            "tier": tier,
            "cc_avg_time": cc_s["avg_time"] if cc_s else "",
            "cc_completion_rate": cc_s["completion_rate"] if cc_s else "",
            "cc_avg_cost": cc_s["avg_cost"] if cc_s else "",
            "cc_queries": cc_s["total_queries"] if cc_s else 0,
            "rag_avg_time": rag_s["avg_time"] if rag_s else "",
            "rag_completion_rate": rag_s["completion_rate"] if rag_s else "",
            "rag_avg_cost": rag_s["avg_cost"] if rag_s else "",
            "rag_queries": rag_s["total_queries"] if rag_s else 0,
        })

    print(f"\nCutoff: {args.cutoff}s ({cutoff_min:.0f} min). 'Done' = % of queries that returned an answer within the cutoff.\n")

    if args.csv:
        with open(args.csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"CSV written to {args.csv}")


if __name__ == "__main__":
    main()
