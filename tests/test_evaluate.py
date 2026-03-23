"""Tests for evaluate.py scoring, sentence counting, and hallucination detection."""

import sys
import os

# Ensure the benchmark root is on the path so `evaluate` can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evaluate import score_response, count_sentences, detect_hallucination


def test_score_correct_hard_needle():
    gt = {"required_facts": ["April 15", "Sarah"], "partial_facts": ["patent filing", "deadline"]}
    response = "Sarah from Legal mentioned that the patent filing deadline was moved to April 15th."
    score, grade = score_response(response, gt, question_type="hard")
    assert score == 1.0
    assert grade == "correct"


def test_score_partial_hard_needle():
    gt = {"required_facts": ["April 15", "Sarah"], "partial_facts": ["patent filing", "deadline"]}
    response = "There was something about a patent filing deadline change."
    score, grade = score_response(response, gt, question_type="hard")
    assert score == 0.5
    assert grade == "partial"


def test_score_wrong_hard_needle():
    gt = {"required_facts": ["April 15", "Sarah"], "partial_facts": ["patent filing", "deadline"]}
    response = "I searched through the emails but could not find any relevant information."
    score, grade = score_response(response, gt, question_type="hard")
    assert score == 0.0
    assert grade == "wrong"


def test_score_correct_easy_pattern():
    gt = {"required_facts": ["Nexus"], "required_all_of": ["Engineering", "Product"],
          "partial_facts": ["Nexus"], "min_detail_sentences": 2}
    response = (
        "Project Nexus is a cross-platform initiative led by the Engineering team. "
        "The Product team is also deeply involved in roadmap planning and feature prioritization."
    )
    score, grade = score_response(response, gt, question_type="easy")
    assert score == 1.0
    assert grade == "correct"


def test_score_partial_easy_too_brief():
    gt = {"required_facts": ["Nexus"], "required_all_of": ["Engineering", "Product"],
          "partial_facts": ["Nexus"], "min_detail_sentences": 2}
    response = "Nexus involves Engineering and Product."
    score, grade = score_response(response, gt, question_type="easy")
    assert score == 0.5
    assert grade == "partial"


def test_count_sentences():
    assert count_sentences("Hello. World.") == 2
    assert count_sentences("One sentence") == 1
    assert count_sentences("First. Second! Third?") == 3


def test_hallucination_detection():
    gt = {"required_facts": ["April 15", "Sarah"]}
    assert detect_hallucination("I couldn't find anything.", gt) == False
    assert detect_hallucination("Sarah mentioned April 15th.", gt) == True
    assert detect_hallucination("No relevant information found.", gt) == False
