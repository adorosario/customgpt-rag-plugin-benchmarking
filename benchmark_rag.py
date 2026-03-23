"""Phase 2B: Run RAG benchmark — query CustomGPT API directly and capture metrics.

Same questions as benchmark.py but queries go through CustomGPT RAG API
instead of Claude Code file search. Measures pure RAG performance.
"""

import argparse
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

import yaml


def load_config(config_path="config.yaml"):
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_questions(gt_path="ground_truth.yaml"):
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


def load_api_key():
    """Load CustomGPT API key from ~/.claude/customgpt-config.json."""
    import os
    config_path = os.path.expanduser("~/.claude/customgpt-config.json")
    with open(config_path) as f:
        return json.load(f)["apiKey"]


def create_session(agent_id, api_key, name="rag-benchmark"):
    """Create a new conversation session."""
    url = f"https://app.customgpt.ai/api/v1/projects/{agent_id}/conversations"
    data = urllib.parse.urlencode({"name": name}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Authorization": f"Bearer {api_key}"})
    resp = json.loads(urllib.request.urlopen(req).read())
    return resp["data"]["session_id"]


def query_rag(agent_id, session_id, api_key, question, timeout=60):
    """Send a question to the RAG agent and return response + timing."""
    url = f"https://app.customgpt.ai/api/v1/projects/{agent_id}/conversations/{session_id}/messages"
    data = urllib.parse.urlencode({"prompt": question, "stream": "false"}).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Authorization": f"Bearer {api_key}"})

    start = time.time()
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        elapsed = time.time() - start

        response_text = resp["data"].get("openai_response", "") or ""
        citations = resp["data"].get("citations") or []

        return {
            "response": response_text,
            "time_seconds": round(elapsed, 2),
            "citations": len(citations),
            "citation_details": [
                {"title": c.get("title", ""), "url": c.get("url", "")}
                for c in citations
            ],
            "error": None,
            "timed_out": False,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "response": "",
            "time_seconds": round(elapsed, 2),
            "citations": 0,
            "citation_details": [],
            "error": str(e),
            "timed_out": elapsed >= timeout * 0.95,
        }


def main():
    parser = argparse.ArgumentParser(description="Run RAG benchmark via CustomGPT API")
    parser.add_argument("--agent-id", type=int, required=True,
                        help="CustomGPT agent ID")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--repetitions", type=int, default=3,
                        help="Runs per question (default: 3)")
    parser.add_argument("--output-dir", default="results_rag/raw",
                        help="Output directory for raw results")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true")
    args = parser.parse_args()

    api_key = load_api_key()
    questions = load_questions()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(questions) * args.repetitions
    print(f"RAG Benchmark: {len(questions)} questions x {args.repetitions} reps = {total_runs} runs")
    print(f"Agent ID: {args.agent_id}")

    if args.dry_run:
        for q in questions:
            for r in range(1, args.repetitions + 1):
                print(f"  [DRY RUN] {q['id']} run {r}: \"{q['question'][:60]}...\"")
        return

    if not args.yes:
        confirm = input("Proceed? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

    total_time = 0
    run_count = 0

    for r in range(1, args.repetitions + 1):
        # Fresh session per repetition
        session_id = create_session(args.agent_id, api_key, f"bench-run-{r}")
        print(f"\n--- Run {r}/{args.repetitions} (session: {session_id[:8]}...) ---")

        for q in questions:
            run_count += 1
            print(f"  [{run_count}/{total_runs}] {q['id']}...", end=" ", flush=True)

            result = query_rag(args.agent_id, session_id, api_key, q["question"])

            # Build output record
            record = {
                "question_id": q["id"],
                "question_type": q["type"],
                "run": r,
                "question": q["question"],
                "response": result["response"],
                "time_seconds": result["time_seconds"],
                "citations": result["citations"],
                "citation_details": result["citation_details"],
                "timed_out": result["timed_out"],
                "error": result["error"],
                "method": "rag",
                "agent_id": args.agent_id,
            }

            # Save
            filename = f"rag_{q['id']}_run{r}.json"
            with open(output_dir / filename, "w") as f:
                json.dump(record, f, indent=2)

            total_time += result["time_seconds"]
            status = "TIMEOUT" if result["timed_out"] else ("ERROR" if result["error"] else "OK")
            print(f"{status} ({result['time_seconds']}s, {result['citations']} citations)")

    print(f"\nDone! {run_count} results saved to {output_dir}")
    print(f"Total time: {total_time:.1f}s | Avg: {total_time/run_count:.1f}s per question")


if __name__ == "__main__":
    main()
