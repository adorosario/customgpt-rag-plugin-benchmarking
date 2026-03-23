"""Tests for the email generator."""

import os
import sys

import yaml

# Ensure the project root is on the path so `generate` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generate import (
    build_tier,
    generate_needle_email,
    generate_single_email,
    load_config,
    load_templates,
)

# All helpers resolve paths relative to the benchmark root
_ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_generate_single_email_has_required_headers():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    config = load_config(os.path.join(_ROOT, "config.yaml"))
    email = generate_single_email(templates, config, email_number=1, seed=42)
    assert "From:" in email
    assert "To:" in email
    assert "Date:" in email
    assert "Subject:" in email
    assert "@acmecorp.com" in email


def test_generate_single_email_word_count():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    config = load_config(os.path.join(_ROOT, "config.yaml"))
    email = generate_single_email(templates, config, email_number=1, seed=42)
    parts = email.split("\n\n", 1)
    body = parts[1] if len(parts) > 1 else ""
    word_count = len(body.split())
    assert 50 <= word_count <= 500, f"Body word count {word_count} outside expected range"


def test_needle_email_contains_required_facts():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    needles = templates["needles"]["hard_needles"]
    needle_1 = needles[0]
    email = generate_needle_email(needle_1)
    assert "April 15" in email or "April 15th" in email
    assert "Sarah" in email


def test_build_tier_size_is_correct():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    config = load_config(os.path.join(_ROOT, "config.yaml"))
    gt = yaml.safe_load(open(os.path.join(_ROOT, "ground_truth.yaml")))
    tier_emails = build_tier(100, templates, config, gt, seed=42)
    assert len(tier_emails) == 100


def test_build_tier_includes_needles_at_correct_tier():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    config = load_config(os.path.join(_ROOT, "config.yaml"))
    gt = yaml.safe_load(open(os.path.join(_ROOT, "ground_truth.yaml")))
    tier_emails = build_tier(500, templates, config, gt, seed=42)
    all_text = "\n".join(tier_emails)
    assert "April 15" in all_text or "April 15th" in all_text


def test_build_tier_excludes_future_needles():
    templates = load_templates(os.path.join(_ROOT, "templates/"))
    config = load_config(os.path.join(_ROOT, "config.yaml"))
    gt = yaml.safe_load(open(os.path.join(_ROOT, "ground_truth.yaml")))
    tier_emails = build_tier(50, templates, config, gt, seed=42)
    # Check needle's unique subject is not present
    needle_subject = templates["needles"]["hard_needles"][0]["subject"]
    all_text = "\n".join(tier_emails)
    assert needle_subject not in all_text
