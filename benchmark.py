"""Phase 2: Run claude -p at each tier and capture metrics.

TOKEN TRACKING:
Uses --output-format json which returns structured data including:
  - result: the response text
  - total_cost_usd: exact dollar cost
  - num_turns: number of tool-use turns (our tool call metric)
  - usage.input_tokens, output_tokens, cache tokens
  - duration_ms: server-side API time
  - modelUsage: per-model token/cost breakdown

MODEL CONTROL:
Use --model flag to pin a specific model (e.g., sonnet, opus).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml


def load_config(config_path="config.yaml"):
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_questions(gt_path="ground_truth.yaml"):
    """Load all questions from ground truth, tagged with type and metadata."""
    with open(gt_path) as f:
        gt = yaml.safe_load(f)
    questions = []
    for needle in gt.get("hard_needles", []):
        questions.append({
            "id": needle["id"],
            "type": "hard",
            "question": needle["question"],
            "first_appears_at": needle["first_appears_at"],
        })
    for pattern in gt.get("easy_patterns", []):
        questions.append({
            "id": pattern["id"],
            "type": "easy",
            "question": pattern["question"],
        })
    return questions


def get_timeout(tier, config):
    timeouts = config["benchmark"]["timeouts"]
    return timeouts.get(tier, timeouts.get(str(tier), 300))


def parse_claude_json(stdout):
    """Parse the JSON output from claude -p --output-format json.

    Returns a dict with all extracted metrics. The JSON schema includes:
    {
      "type": "result",
      "result": "response text",
      "duration_ms": 8763,
      "num_turns": 2,
      "total_cost_usd": 0.131,
      "usage": {
        "input_tokens": 3,
        "cache_creation_input_tokens": 32226,
        "cache_read_input_tokens": 28374,
        "output_tokens": 173
      },
      "modelUsage": { ... }
    }
    """
    try:
        data = json.loads(stdout)
        usage = data.get("usage", {})

        input_tokens = usage.get("input_tokens", 0)
        cache_creation = usage.get("cache_creation_input_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = input_tokens + cache_creation + cache_read + output_tokens

        return {
            "response": data.get("result", ""),
            "num_turns": data.get("num_turns", 0),
            "cost_usd": data.get("total_cost_usd", 0),
            "duration_api_ms": data.get("duration_api_ms", 0),
            "duration_ms": data.get("duration_ms", 0),
            "input_tokens": input_tokens,
            "cache_creation_tokens": cache_creation,
            "cache_read_tokens": cache_read,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "stop_reason": data.get("stop_reason", ""),
            "model": _extract_model(data),
            "is_error": data.get("is_error", False),
            "raw_json": data,
        }
    except (json.JSONDecodeError, TypeError):
        return {
            "response": stdout,
            "num_turns": 0,
            "cost_usd": 0,
            "duration_api_ms": 0,
            "duration_ms": 0,
            "input_tokens": 0,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "stop_reason": "",
            "model": "unknown",
            "is_error": False,
            "raw_json": None,
        }


def _extract_model(data):
    """Extract the model name from the JSON response."""
    model_usage = data.get("modelUsage", {})
    if model_usage:
        return list(model_usage.keys())[0]
    return "unknown"


def is_retryable_error(error_str):
    """Check if an error is a transient infrastructure issue worth retrying."""
    retryable_patterns = ["rate limit", "429", "connection refused", "connection reset",
                          "ECONNRESET", "EPIPE", "broken pipe", "overloaded"]
    return any(p in error_str.lower() for p in retryable_patterns)


def build_command(question, model=None, max_turns=None):
    """Build the claude CLI command."""
    cmd = ["claude", "-p", question, "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])
    return cmd


def run_single_benchmark(question, tier, tier_dir, timeout, run_number,
                         model=None, max_turns=None, max_retries=3):
    """Run a single claude -p query with exponential backoff retry on transient errors."""
    result = {
        "tier": tier,
        "question_id": question["id"],
        "question_type": question["type"],
        "run": run_number,
        "question": question["question"],
        "model": model or "default",
        "response": "",
        "time_seconds": 0,
        "num_turns": 0,
        "cost_usd": 0,
        "input_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "duration_api_ms": 0,
        "stop_reason": "",
        "timed_out": False,
        "error": None,
    }

    cmd = build_command(question["question"], model=model, max_turns=max_turns)

    for attempt in range(max_retries + 1):
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(tier_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            elapsed = time.time() - start
            result["time_seconds"] = round(elapsed, 2)

            # Parse structured JSON output
            parsed = parse_claude_json(proc.stdout)
            result["response"] = parsed["response"]
            result["num_turns"] = parsed["num_turns"]
            result["cost_usd"] = parsed["cost_usd"]
            result["input_tokens"] = parsed["input_tokens"]
            result["cache_creation_tokens"] = parsed["cache_creation_tokens"]
            result["cache_read_tokens"] = parsed["cache_read_tokens"]
            result["output_tokens"] = parsed["output_tokens"]
            result["total_tokens"] = parsed["total_tokens"]
            result["duration_api_ms"] = parsed["duration_api_ms"]
            result["stop_reason"] = parsed["stop_reason"]
            if parsed["model"] != "unknown":
                result["model"] = parsed["model"]

            # Check for rate-limit in stderr
            if proc.returncode != 0 and is_retryable_error(proc.stderr or ""):
                if attempt < max_retries:
                    backoff = min(2 ** (attempt + 1), 60)
                    print(f"RETRY (attempt {attempt+1}, backoff {backoff}s)...", end=" ", flush=True)
                    time.sleep(backoff)
                    continue
                else:
                    result["error"] = f"rate_limited_after_{max_retries}_retries"
            return result

        except subprocess.TimeoutExpired as e:
            elapsed = time.time() - start
            result["time_seconds"] = round(elapsed, 2)
            result["timed_out"] = True
            stdout = ""
            if e.stdout:
                stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout
            result["response"] = stdout
            result["error"] = "timeout"
            return result

        except Exception as e:
            elapsed = time.time() - start
            error_str = str(e)
            if is_retryable_error(error_str) and attempt < max_retries:
                backoff = min(2 ** (attempt + 1), 60)
                print(f"RETRY (attempt {attempt+1}, backoff {backoff}s)...", end=" ", flush=True)
                time.sleep(backoff)
                continue
            result["time_seconds"] = round(elapsed, 2)
            result["error"] = error_str
            return result

    return result


def main():
    parser = argparse.ArgumentParser(description="Run Claude Code benchmark")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--model", default=None,
                        help="Claude model to use (e.g., sonnet, opus)")
    parser.add_argument("--max-turns", type=int, default=None,
                        help="Max tool-use turns per query")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print commands without executing")
    parser.add_argument("--min-tier", type=int, default=None,
                        help="Start from this tier size (skip smaller tiers)")
    parser.add_argument("--max-tier", type=int, default=None,
                        help="Stop after this tier size")
    parser.add_argument("--cwd-template", default=None,
                        help="Override cwd template (e.g., emails_pdf/tier_{tier}/)")
    parser.add_argument("--output-dir", default=None,
                        help="Override output directory for raw results")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args()

    config = load_config(args.config)
    questions = load_questions()
    tiers = config["tiers"]
    repetitions = config["benchmark"]["repetitions"]
    cwd_template = args.cwd_template or config["benchmark"]["cwd_template"]
    output_dir = Path(args.output_dir or "results/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.min_tier:
        tiers = [t for t in tiers if t >= args.min_tier]
    if args.max_tier:
        tiers = [t for t in tiers if t <= args.max_tier]

    total_runs = len(tiers) * len(questions) * repetitions
    model_str = args.model or "default"
    print(f"Benchmark: {len(tiers)} tiers x {len(questions)} questions x {repetitions} reps = {total_runs} runs")
    print(f"Model: {model_str}")

    if args.dry_run:
        for tier in tiers:
            for q in questions:
                for r in range(1, repetitions + 1):
                    tier_dir = cwd_template.format(tier=tier)
                    cmd = build_command(q["question"][:50] + "...", model=args.model,
                                        max_turns=args.max_turns)
                    print(f"  [DRY RUN] {' '.join(cmd)} cwd={tier_dir} (run {r})")
        return

    if not args.yes:
        print(f"Estimated worst-case runtime: {total_runs * 5 // 60} minutes")
        confirm = input("Proceed? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

    total_cost = 0.0
    run_count = 0
    for tier in tiers:
        tier_dir = Path(cwd_template.format(tier=tier))
        timeout = get_timeout(tier, config)
        print(f"\n--- Tier {tier} (timeout: {timeout}s, model: {model_str}) ---")

        if not tier_dir.exists():
            print(f"  WARNING: {tier_dir} does not exist. Run generate.py first. Skipping.")
            continue

        for q in questions:
            for r in range(1, repetitions + 1):
                run_count += 1
                print(f"  [{run_count}/{total_runs}] {q['id']} run {r}...", end=" ", flush=True)
                result = run_single_benchmark(
                    q, tier, tier_dir, timeout, r,
                    model=args.model, max_turns=args.max_turns,
                )
                filename = f"tier_{tier}_{q['id']}_run{r}.json"
                with open(output_dir / filename, "w") as f:
                    json.dump(result, f, indent=2)

                total_cost += result.get("cost_usd", 0)
                status = "TIMEOUT" if result["timed_out"] else ("ERROR" if result["error"] else "OK")
                print(f"{status} ({result['time_seconds']}s, {result['num_turns']} turns, "
                      f"{result['total_tokens']} tokens, ${result['cost_usd']:.4f})")

    print(f"\nDone! {run_count} results saved to {output_dir}")
    print(f"Total cost: ${total_cost:.4f}")


if __name__ == "__main__":
    main()
