"""Phase 2C: Run Claude Code + RAG plugin benchmark.

Runs claude -p with --dangerously-skip-permissions so Claude can use
the CustomGPT RAG plugin to answer questions. Measures the full
end-to-end time of Claude Code orchestrating RAG search.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

import yaml


def load_questions(gt_path="ground_truth.yaml"):
    with open(gt_path) as f:
        gt = yaml.safe_load(f)
    questions = []
    for needle in gt.get("hard_needles", []):
        questions.append({
            "id": needle["id"],
            "type": "hard",
            "question": needle["question"],
        })
    for pattern in gt.get("easy_patterns", []):
        questions.append({
            "id": pattern["id"],
            "type": "easy",
            "question": pattern["question"],
        })
    return questions


def parse_claude_json(stdout):
    """Parse JSON output from claude -p --output-format json."""
    try:
        data = json.loads(stdout)
        usage = data.get("usage", {})
        return {
            "response": data.get("result", ""),
            "num_turns": data.get("num_turns", 0),
            "cost_usd": data.get("total_cost_usd", 0),
            "duration_ms": data.get("duration_ms", 0),
            "input_tokens": usage.get("input_tokens", 0),
            "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
            "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "total_tokens": (usage.get("input_tokens", 0) +
                           usage.get("cache_creation_input_tokens", 0) +
                           usage.get("cache_read_input_tokens", 0) +
                           usage.get("output_tokens", 0)),
            "model": list(data.get("modelUsage", {}).keys())[0] if data.get("modelUsage") else "unknown",
            "permission_denials": len(data.get("permission_denials", [])),
        }
    except (json.JSONDecodeError, TypeError, IndexError):
        return {
            "response": stdout,
            "num_turns": 0, "cost_usd": 0, "duration_ms": 0,
            "input_tokens": 0, "cache_creation_tokens": 0,
            "cache_read_tokens": 0, "output_tokens": 0,
            "total_tokens": 0, "model": "unknown", "permission_denials": 0,
        }


def run_single(question, cwd, model, timeout):
    """Run a single claude -p query with RAG plugin available."""
    prompt = f"Use /ask-agent to answer: {question}"

    cmd = ["claude", "-p", prompt,
           "--output-format", "json",
           "--dangerously-skip-permissions"]
    if model:
        cmd.extend(["--model", model])

    result = {
        "response": "",
        "time_seconds": 0,
        "num_turns": 0,
        "cost_usd": 0,
        "total_tokens": 0,
        "timed_out": False,
        "error": None,
    }

    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout)
        elapsed = time.time() - start
        result["time_seconds"] = round(elapsed, 2)

        parsed = parse_claude_json(proc.stdout)
        result["response"] = parsed["response"]
        result["num_turns"] = parsed["num_turns"]
        result["cost_usd"] = parsed["cost_usd"]
        result["total_tokens"] = parsed["total_tokens"]
        result["model"] = parsed["model"]
        result["permission_denials"] = parsed["permission_denials"]

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        result["time_seconds"] = round(elapsed, 2)
        result["timed_out"] = True
        result["error"] = "timeout"

    except Exception as e:
        elapsed = time.time() - start
        result["time_seconds"] = round(elapsed, 2)
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Run Claude Code + RAG plugin benchmark")
    parser.add_argument("--cwd", required=True,
                        help="Working directory with .customgpt-meta.json (e.g., emails_pdf/tier_500)")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout per query in seconds (default: 300)")
    parser.add_argument("--output-dir", default="results_cc_rag/raw")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true")
    args = parser.parse_args()

    questions = load_questions()
    cwd = Path(args.cwd)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(questions) * args.repetitions
    print(f"CC+RAG Benchmark: {len(questions)} questions x {args.repetitions} reps = {total_runs} runs")
    print(f"Model: {args.model}")
    print(f"CWD: {cwd}")
    print(f"Timeout: {args.timeout}s")

    if args.dry_run:
        for q in questions:
            for r in range(1, args.repetitions + 1):
                print(f"  [DRY RUN] {q['id']} run {r}")
        return

    if not args.yes:
        confirm = input("Proceed? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

    total_cost = 0
    run_count = 0

    for r in range(1, args.repetitions + 1):
        print(f"\n--- Run {r}/{args.repetitions} ---")

        for q in questions:
            run_count += 1
            print(f"  [{run_count}/{total_runs}] {q['id']}...", end=" ", flush=True)

            result = run_single(q["question"], cwd, args.model, args.timeout)

            record = {
                "question_id": q["id"],
                "question_type": q["type"],
                "run": r,
                "question": q["question"],
                "method": "cc_rag",
                **result,
            }

            filename = f"cc_rag_{q['id']}_run{r}.json"
            with open(output_dir / filename, "w") as f:
                json.dump(record, f, indent=2)

            total_cost += result.get("cost_usd", 0)
            status = "TIMEOUT" if result["timed_out"] else ("ERROR" if result["error"] else "OK")
            print(f"{status} ({result['time_seconds']}s, {result['num_turns']} turns, ${result['cost_usd']:.4f})")

    print(f"\nDone! {run_count} results saved to {output_dir}")
    print(f"Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
