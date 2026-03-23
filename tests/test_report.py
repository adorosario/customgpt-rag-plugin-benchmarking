import pandas as pd
from pathlib import Path
from report import generate_breaking_point_chart, generate_scorecard_chart


def test_breaking_point_chart_creates_file(tmp_path):
    summary = pd.DataFrame({
        "tier": [50, 100, 250],
        "accuracy": [1.0, 0.9, 0.7],
        "median_time_seconds": [3.0, 8.0, 25.0],
    })
    output_path = tmp_path / "test_chart.png"
    generate_breaking_point_chart(summary, str(output_path), dpi=72)
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_scorecard_chart_creates_file(tmp_path):
    summary = pd.DataFrame({
        "tier": [50, 100],
        "accuracy": [1.0, 0.8],
        "median_time_seconds": [3.0, 10.0],
        "total_tokens": [5000, 20000],
        "total_turns": [10, 40],
        "total_cost_usd": [0.50, 2.10],
        "timeout_count": [0, 1],
    })
    output_path = tmp_path / "scorecard.png"
    generate_scorecard_chart(summary, str(output_path), dpi=72)
    assert output_path.exists()
    assert output_path.stat().st_size > 0
