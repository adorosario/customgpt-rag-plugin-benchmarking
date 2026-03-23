"""Phase 3: Score benchmark results and produce summary CSVs.

Reads all JSON files from results/raw/, scores each response against
ground_truth.yaml, and writes:
  results/benchmark_results.csv  — one row per raw result file
  results/benchmark_summary.csv  — one row per tier
"""

import argparse
import csv
import json
import re
import statistics
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Core scoring helpers
# ---------------------------------------------------------------------------

def count_sentences(text: str) -> int:
    """Count sentences by splitting on '.', '!', or '?'."""
    if not text or not text.strip():
        return 0
    parts = re.split(r"[.!?]", text)
    # Filter out empty/whitespace-only segments produced by the split
    non_empty = [p for p in parts if p.strip()]
    # If there are no sentence-ending punctuation marks, the whole text is
    # considered one sentence (as long as there is content).
    if not non_empty:
        return 0
    # Each split segment (except trailing empty ones) represents a sentence
    # only if the original text actually contained the delimiter.
    # A simpler and correct approach: count delimiter occurrences that are
    # preceded by non-whitespace content.
    matches = re.findall(r"[^\s][.!?]", text)
    sentence_count = len(matches)
    # If there's content but no terminators, it's still one sentence.
    if sentence_count == 0 and text.strip():
        return 1
    return sentence_count


def detect_hallucination(response: str, gt_entry: dict) -> bool:
    """Return True if the response contains any required_facts strings.

    Used for absent-needle detection: if the needle is NOT present at this
    tier but the model still reports specific facts from it, that is a
    hallucination.
    """
    required_facts = gt_entry.get("required_facts", [])
    response_lower = response.lower()
    for fact in required_facts:
        if fact.lower() in response_lower:
            return True
    return False


def score_response(response: str, gt_entry: dict, question_type: str = "hard"):
    """Score a single response against its ground-truth entry.

    Returns (score, grade) where:
      (1.0, "correct")  — all required criteria met
      (0.5, "partial")  — some criteria met but not all
      (0.0, "wrong")    — nothing useful found
    """
    response_lower = response.lower()

    required_facts = gt_entry.get("required_facts", [])
    partial_facts = gt_entry.get("partial_facts", [])

    if question_type == "easy":
        required_all_of = gt_entry.get("required_all_of", [])
        min_detail_sentences = gt_entry.get("min_detail_sentences", 0)

        # All required_facts must be present
        all_required = all(f.lower() in response_lower for f in required_facts)
        # All required_all_of terms must be present
        all_required_all_of = all(t.lower() in response_lower for t in required_all_of)
        # Sentence-count threshold
        sentence_ok = count_sentences(response) >= min_detail_sentences

        if all_required and all_required_all_of and sentence_ok:
            return (1.0, "correct")

        # Partial: any partial_fact present, or most (but not all) criteria met
        any_partial = any(f.lower() in response_lower for f in partial_facts)
        any_required = any(f.lower() in response_lower for f in required_facts)
        any_all_of = any(t.lower() in response_lower for t in required_all_of)

        if any_partial or any_required or any_all_of:
            return (0.5, "partial")

        return (0.0, "wrong")

    else:  # hard needle
        # All required_facts must be present for a correct answer
        all_required = all(f.lower() in response_lower for f in required_facts)
        if all_required and required_facts:
            return (1.0, "correct")

        # Partial: at least one partial_fact present
        any_partial = any(f.lower() in response_lower for f in partial_facts)
        if any_partial:
            return (0.5, "partial")

        return (0.0, "wrong")


def is_needle_present(gt_entry: dict, tier: int) -> bool:
    """Return True if the needle should be findable at the given tier.

    Easy patterns are always present (no first_appears_at).
    Hard needles are present only when tier >= first_appears_at.
    """
    first_appears_at = gt_entry.get("first_appears_at")
    if first_appears_at is None:
        return True
    return tier >= first_appears_at


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_ground_truth(gt_path: str = "ground_truth.yaml") -> dict:
    """Load and index ground truth by question id."""
    with open(gt_path) as f:
        raw = yaml.safe_load(f)

    index = {}
    for needle in raw.get("hard_needles", []):
        index[needle["id"]] = {"type": "hard", **needle}
    for pattern in raw.get("easy_patterns", []):
        index[pattern["id"]] = {"type": "easy", **pattern}
    return index


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_raw_results(raw_dir: Path) -> list[dict]:
    results = []
    for p in sorted(raw_dir.glob("*.json")):
        with open(p) as f:
            results.append(json.load(f))
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate Claude Code benchmark results")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--ground-truth", default="ground_truth.yaml")
    parser.add_argument("--raw-dir", default="results/raw")
    parser.add_argument("--output-dir", default="results")
    args = parser.parse_args()

    config = load_config(args.config)
    gt_index = load_ground_truth(args.ground_truth)
    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tiers = config.get("tiers", [])
    timeouts = config["benchmark"]["timeouts"]

    raw_results = load_raw_results(raw_dir)
    if not raw_results:
        print(f"No JSON files found in {raw_dir}. Run benchmark.py first.")
        return

    # -----------------------------------------------------------------------
    # Score every raw result
    # -----------------------------------------------------------------------
    detail_rows = []

    for r in raw_results:
        tier = r["tier"]
        qid = r["question_id"]
        qtype = r.get("question_type", "hard")
        response = r.get("response", "") or ""

        gt_entry = gt_index.get(qid, {})
        needle_present = is_needle_present(gt_entry, tier)

        # Absent-needle questions are excluded from accuracy scoring
        # and only evaluated for hallucination
        hallucinated = False
        if not needle_present:
            hallucinated = detect_hallucination(response, gt_entry)
            score = None
            grade = "excluded"
        else:
            score, grade = score_response(response, gt_entry, question_type=qtype)

        # Timeout detection: timed_out flag OR time >= 95% of tier timeout
        tier_timeout = timeouts.get(tier, timeouts.get(str(tier), 300))
        timed_out = r.get("timed_out", False) or (r.get("time_seconds", 0) >= 0.95 * tier_timeout)

        detail_rows.append({
            "tier": tier,
            "question_id": qid,
            "question_type": qtype,
            "run": r.get("run", 1),
            "score": score,
            "grade": grade,
            "needle_present": needle_present,
            "hallucinated": hallucinated,
            "timed_out": timed_out,
            "time_seconds": r.get("time_seconds", 0),
            "num_turns": r.get("num_turns", r.get("tool_calls", 0)),
            "total_tokens": r.get("total_tokens", r.get("tokens_estimated", 0)),
            "cost_usd": r.get("cost_usd", 0),
            "input_tokens": r.get("input_tokens", 0),
            "output_tokens": r.get("output_tokens", 0),
            "model": r.get("model", ""),
            "error": r.get("error") or "",
        })

    # Write benchmark_results.csv
    results_csv = output_dir / "benchmark_results.csv"
    fieldnames = [
        "tier", "question_id", "question_type", "run",
        "score", "grade", "needle_present", "hallucinated",
        "timed_out", "time_seconds", "num_turns", "total_tokens",
        "cost_usd", "input_tokens", "output_tokens", "model", "error",
    ]
    with open(results_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(detail_rows)

    print(f"Wrote {len(detail_rows)} rows to {results_csv}")

    # -----------------------------------------------------------------------
    # Build summary per tier
    # -----------------------------------------------------------------------
    summary_rows = []

    for tier in tiers:
        tier_rows = [r for r in detail_rows if r["tier"] == tier]
        if not tier_rows:
            continue

        tier_timeout = timeouts.get(tier, timeouts.get(str(tier), 300))

        # --- Accuracy: median score per question (present needles only) ---
        present_rows = [r for r in tier_rows if r["needle_present"]]
        hard_present_rows = [r for r in present_rows if r["question_type"] == "hard"]
        easy_present_rows = [r for r in present_rows if r["question_type"] == "easy"]

        def median_scores_per_question(rows):
            """For each question, compute median score across runs; return list of medians."""
            by_q: dict[str, list[float]] = {}
            for r in rows:
                by_q.setdefault(r["question_id"], []).append(r["score"])
            return [statistics.median(scores) for scores in by_q.values()]

        overall_medians = median_scores_per_question(present_rows)
        hard_medians = median_scores_per_question(hard_present_rows)
        easy_medians = median_scores_per_question(easy_present_rows)

        accuracy = statistics.mean(overall_medians) if overall_medians else float("nan")
        hard_needle_accuracy = statistics.mean(hard_medians) if hard_medians else float("nan")
        easy_pattern_accuracy = statistics.mean(easy_medians) if easy_medians else float("nan")

        # --- Hallucination rate (absent needles only) ---
        absent_rows = [r for r in tier_rows if not r["needle_present"]]
        hallucination_rate = (
            sum(1 for r in absent_rows if r["hallucinated"]) / len(absent_rows)
            if absent_rows else float("nan")
        )

        # --- Timing ---
        times = [r["time_seconds"] for r in tier_rows]
        median_time = statistics.median(times) if times else float("nan")
        std_time = statistics.stdev(times) if len(times) > 1 else 0.0

        # --- Turns, tokens, cost: sum of per-question medians ---
        by_q_turns: dict[str, list] = {}
        by_q_tokens: dict[str, list] = {}
        by_q_cost: dict[str, list] = {}
        for r in tier_rows:
            by_q_turns.setdefault(r["question_id"], []).append(r["num_turns"])
            by_q_tokens.setdefault(r["question_id"], []).append(r["total_tokens"])
            by_q_cost.setdefault(r["question_id"], []).append(r["cost_usd"])

        total_turns = sum(
            statistics.median(v) for v in by_q_turns.values()
        )
        total_tokens = sum(
            statistics.median(v) for v in by_q_tokens.values()
        )
        total_cost = sum(
            statistics.median(v) for v in by_q_cost.values()
        )

        # --- Timeout count ---
        timeout_count = sum(
            1 for r in tier_rows if r.get("timed_out", False)
        )

        summary_rows.append({
            "tier": tier,
            "accuracy": round(accuracy, 4) if accuracy == accuracy else "",
            "hard_needle_accuracy": round(hard_needle_accuracy, 4) if hard_needle_accuracy == hard_needle_accuracy else "",
            "easy_pattern_accuracy": round(easy_pattern_accuracy, 4) if easy_pattern_accuracy == easy_pattern_accuracy else "",
            "hallucination_rate": round(hallucination_rate, 4) if hallucination_rate == hallucination_rate else "",
            "median_time_seconds": round(median_time, 2) if median_time == median_time else "",
            "std_time_seconds": round(std_time, 2),
            "total_turns": round(total_turns, 1),
            "total_tokens": round(total_tokens, 1),
            "total_cost_usd": round(total_cost, 4),
            "timeout_count": timeout_count,
        })

    summary_csv = output_dir / "benchmark_summary.csv"
    summary_fieldnames = [
        "tier", "accuracy", "hard_needle_accuracy", "easy_pattern_accuracy",
        "hallucination_rate", "median_time_seconds", "std_time_seconds",
        "total_turns", "total_tokens", "total_cost_usd", "timeout_count",
    ]
    with open(summary_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=summary_fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Wrote {len(summary_rows)} tier rows to {summary_csv}")


if __name__ == "__main__":
    main()
