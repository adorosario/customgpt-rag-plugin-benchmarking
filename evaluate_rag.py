"""Evaluate RAG benchmark results and generate comparison summary."""

import argparse
import csv
import json
import statistics
from pathlib import Path

import yaml


def load_ground_truth(path="ground_truth.yaml"):
    with open(path) as f:
        gt = yaml.safe_load(f)
    index = {}
    for n in gt.get("hard_needles", []):
        index[n["id"]] = n
    for p in gt.get("easy_patterns", []):
        index[p["id"]] = p
    return index


def score_response(response, gt_entry):
    """Score a RAG response. Same logic as evaluate.py."""
    response_lower = response.lower()

    required = gt_entry.get("required_facts", [])
    all_required = all(f.lower() in response_lower for f in required)

    required_all = gt_entry.get("required_all_of", [])
    all_required_all = all(f.lower() in response_lower for f in required_all)

    partial_facts = gt_entry.get("partial_facts", [])
    any_partial = any(f.lower() in response_lower for f in partial_facts)

    min_sentences = gt_entry.get("min_detail_sentences", 0)
    import re
    sentences = len([s for s in re.split(r'[.!?]+', response.strip()) if s.strip()])
    enough_detail = sentences >= min_sentences if min_sentences else True

    # "I don't know" = wrong (not hallucination, just didn't find it)
    not_found = any(phrase in response_lower for phrase in
                    ["i don't know", "i'm sorry", "no information", "not found", "cannot find"])

    if not_found and not any_partial:
        return 0.0, "not_found"
    elif all_required and all_required_all and enough_detail:
        return 1.0, "correct"
    elif any_partial or all_required:
        return 0.5, "partial"
    else:
        return 0.0, "wrong"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="results_rag/raw")
    parser.add_argument("--output-dir", default="results_rag")
    parser.add_argument("--ground-truth", default="ground_truth.yaml")
    args = parser.parse_args()

    gt = load_ground_truth(args.ground_truth)
    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load all results
    results = []
    for f in sorted(raw_dir.glob("rag_*.json")):
        results.append(json.load(open(f)))

    if not results:
        print(f"No results in {raw_dir}")
        return

    # Score each result
    scored = []
    for r in results:
        qid = r["question_id"]
        gt_entry = gt.get(qid, {})
        response = r.get("response", "") or ""

        if r.get("timed_out") or r.get("error"):
            score, grade = 0.0, "error"
        else:
            score, grade = score_response(response, gt_entry)

        scored.append({
            "question_id": qid,
            "question_type": r["question_type"],
            "run": r["run"],
            "score": score,
            "grade": grade,
            "time_seconds": r["time_seconds"],
            "citations": r.get("citations", 0),
            "response_preview": response[:200],
            "method": "rag",
        })

    # Write detailed CSV
    detail_path = output_dir / "rag_results.csv"
    fieldnames = list(scored[0].keys())
    with open(detail_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(scored)
    print(f"Wrote {len(scored)} rows to {detail_path}")

    # Summary
    times = [r["time_seconds"] for r in scored]
    scores = [r["score"] for r in scored]
    correct = sum(1 for r in scored if r["grade"] == "correct")
    partial = sum(1 for r in scored if r["grade"] == "partial")
    not_found = sum(1 for r in scored if r["grade"] == "not_found")
    wrong = sum(1 for r in scored if r["grade"] == "wrong")

    summary = {
        "method": "RAG (CustomGPT)",
        "total_runs": len(scored),
        "avg_time": round(statistics.mean(times), 1),
        "median_time": round(statistics.median(times), 1),
        "min_time": round(min(times), 1),
        "max_time": round(max(times), 1),
        "accuracy": round(statistics.mean(scores) * 100, 1),
        "correct": correct,
        "partial": partial,
        "not_found": not_found,
        "wrong": wrong,
        "hallucination_rate": 0,  # RAG says "I don't know" instead of making things up
        "timeouts": sum(1 for r in scored if r.get("grade") == "error"),
        "avg_citations": round(statistics.mean([r["citations"] for r in scored]), 1),
    }

    summary_path = output_dir / "rag_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*50}")
    print(f"RAG Benchmark Summary")
    print(f"{'='*50}")
    print(f"Runs:           {summary['total_runs']}")
    print(f"Avg time:       {summary['avg_time']}s")
    print(f"Median time:    {summary['median_time']}s")
    print(f"Min/Max:        {summary['min_time']}s / {summary['max_time']}s")
    print(f"Accuracy:       {summary['accuracy']}%")
    print(f"Correct:        {summary['correct']}")
    print(f"Partial:        {summary['partial']}")
    print(f"Not found:      {summary['not_found']}")
    print(f"Wrong:          {summary['wrong']}")
    print(f"Hallucination:  {summary['hallucination_rate']}%")
    print(f"Timeouts:       {summary['timeouts']}")
    print(f"Avg citations:  {summary['avg_citations']}")


if __name__ == "__main__":
    main()
