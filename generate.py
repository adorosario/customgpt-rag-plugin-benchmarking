#!/usr/bin/env python3
"""Email generator for the Claude Code Scaling Benchmark.

Generates tiered email corpora with injected needle facts and easy-pattern
emails for retrieval evaluation.
"""

import argparse
import os
import random
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# 1. Config / template loading
# ---------------------------------------------------------------------------

def load_config(config_path="config.yaml"):
    """Load the project configuration YAML."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_templates(templates_dir="templates/"):
    """Load all three template YAMLs and return a combined dict.

    Returns
    -------
    dict with keys: "departments", "topics", "needles"
    """
    base = Path(templates_dir)
    with open(base / "departments.yaml") as f:
        departments = yaml.safe_load(f)
    with open(base / "topics.yaml") as f:
        topics = yaml.safe_load(f)
    with open(base / "needles.yaml") as f:
        needles = yaml.safe_load(f)
    return {
        "departments": departments,
        "topics": topics,
        "needles": needles,
    }


# ---------------------------------------------------------------------------
# 2. Employee helpers
# ---------------------------------------------------------------------------

def get_all_employees(departments_data):
    """Flatten employees from all departments.

    Each employee dict gets ``department`` and ``team_email`` fields added.
    """
    employees = []
    for dept in departments_data["departments"]:
        for emp in dept["employees"]:
            entry = dict(emp)
            entry["department"] = dept["name"]
            entry["team_email"] = dept["team_email"]
            employees.append(entry)
    return employees


# ---------------------------------------------------------------------------
# 3. Date helpers
# ---------------------------------------------------------------------------

def random_date(start_str, end_str, rng):
    """Return a random datetime string between *start_str* and *end_str*.

    Parameters
    ----------
    start_str, end_str : str  – "YYYY-MM-DD"
    rng : random.Random

    Returns
    -------
    str – e.g. "2025-08-14 02:37 PM"
    """
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    delta_seconds = int((end - start).total_seconds())
    offset = rng.randint(0, delta_seconds)
    dt = start + timedelta(seconds=offset)
    return dt.strftime("%Y-%m-%d %I:%M %p")


# ---------------------------------------------------------------------------
# 4. Email rendering
# ---------------------------------------------------------------------------

def render_email(sender, recipient, cc, date, subject, body):
    """Format an email as plain-text with standard headers."""
    lines = [
        f"From: {sender}",
        f"To: {recipient}",
    ]
    if cc:
        lines.append(f"CC: {cc}")
    lines += [
        f"Date: {date}",
        f"Subject: {subject}",
        "",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. Placeholder value pools
# ---------------------------------------------------------------------------

_COMPONENTS = [
    "AuthService", "PaymentGateway", "NotificationEngine", "SearchIndex",
    "DataPipeline", "UserProfileService", "AnalyticsDashboard", "BillingModule",
    "ReportingEngine", "CacheLayer", "APIGateway", "MessageBroker",
    "FileStorageService", "AuditLog", "SchedulerService", "WebhookDispatcher",
]

_SUBSYSTEMS = [
    "caching layer", "authentication module", "rate limiter", "event bus",
    "load balancer", "serialization engine", "queue processor", "connection pool",
    "config manager", "logging pipeline", "metrics collector", "service mesh",
]

_VERSIONS = [
    "v2.4.1", "v3.0.0", "v2.7.3", "v1.9.5", "v4.1.0", "v3.2.2",
    "v2.1.0", "v5.0.0-beta", "v3.8.1", "v2.6.0",
]

_CLIENTS = [
    "Globex", "Soylent Corp", "Umbrella Inc", "Wayne Enterprises",
    "Stark Industries", "Cyberdyne", "Weyland-Yutani", "Tyrell Corp",
    "Massive Dynamic", "Oscorp", "Hooli", "Pied Piper",
]

_PRODUCTS = [
    "Enterprise Suite", "Analytics Pro", "Sync Platform", "Data Vault",
    "Cloud Connect", "Integration Hub", "Insight Engine",
]

_GREETINGS = [
    "Hi team", "Hey everyone", "Hello", "Hi all", "Good morning",
    "Hi", "Hey", "Good afternoon",
]

_SIGN_OFFS = [
    "Best,\n{sender_first}",
    "Thanks,\n{sender_first}",
    "Cheers,\n{sender_first}",
    "Regards,\n{sender_first}",
    "Best regards,\n{sender_first}",
    "Talk soon,\n{sender_first}",
]

_QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

_CITIES = [
    "Berlin", "London", "Tokyo", "New York", "San Francisco",
    "Singapore", "Sydney", "Toronto",
]

_TEAMS = [
    "Engineering", "Sales", "Marketing", "HR", "Legal", "Finance", "Product",
]


def _placeholder_values(rng, sender_first, employees):
    """Return a defaultdict mapping placeholder names to random values."""
    assignee_emp = rng.choice(employees)
    assignee_name = f"{assignee_emp['first_name']} {assignee_emp['last_name']}"

    vals = {
        "component": rng.choice(_COMPONENTS),
        "subsystem": rng.choice(_SUBSYSTEMS),
        "version": rng.choice(_VERSIONS),
        "client": rng.choice(_CLIENTS),
        "product": rng.choice(_PRODUCTS),
        "greeting": rng.choice(_GREETINGS),
        "sign_off": rng.choice(_SIGN_OFFS).replace("{sender_first}", sender_first),
        "assignee": assignee_name,
        "date": f"{rng.choice(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])}, {rng.choice(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'])} {rng.randint(1, 28)}",
        "threshold": f"{rng.randint(50, 500)}ms",
        "current_value": f"{rng.randint(50, 500)}ms",
        "metric": str(rng.randint(10, 200)),
        "percent": f"{rng.randint(5, 60)}%",
        "amount": f"${rng.randint(20, 500)},{rng.randint(0,9)}{rng.randint(0,9)}{rng.randint(0,9)}",
        "quarter": rng.choice(_QUARTERS),
        "deadline": f"{rng.choice(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'])} {rng.randint(1, 28)}",
        "city": rng.choice(_CITIES),
        "team": rng.choice(_TEAMS),
    }

    # Wrap in defaultdict so missing keys resolve to "N/A"
    return defaultdict(lambda: "N/A", vals)


# ---------------------------------------------------------------------------
# 6. Filler paragraph generation
# ---------------------------------------------------------------------------

_FILLER_SENTENCES = [
    "We should circle back on this during the next all-hands meeting.",
    "I have attached the updated spreadsheet for your review.",
    "Please let me know if you have any questions or need further clarification.",
    "The vendor confirmed delivery by the end of the month.",
    "Our team has been making great progress on the quarterly objectives.",
    "The budget was approved last week after the final round of revisions.",
    "I would appreciate your feedback on the attached proposal by Friday.",
    "The office lease renewal is currently under negotiation with the landlord.",
    "We had a successful demo with the client yesterday and they seemed impressed.",
    "Human Resources will be hosting a wellness workshop next Tuesday.",
    "The infrastructure upgrade over the weekend went smoothly with no downtime.",
    "Customer support tickets have decreased by fifteen percent since the last release.",
    "The marketing campaign is scheduled to launch at the beginning of next quarter.",
    "I spoke with the legal team and they confirmed we are in full compliance.",
    "The new onboarding process has received positive feedback from recent hires.",
    "We need to finalize the travel arrangements for the conference in November.",
    "The data migration is expected to complete within the next two weeks.",
    "Please review the attached meeting notes and flag any discrepancies.",
    "Engineering is currently conducting a thorough code review of the new module.",
    "The finance team provided updated projections that look promising for the year.",
    "I recommend we schedule a follow-up call to discuss the outstanding items.",
    "The partnership agreement has been signed and is now in effect.",
    "Our NPS score improved by eight points compared to the previous quarter.",
    "The security audit did not reveal any critical vulnerabilities in the system.",
    "We should consider hiring a contractor to help with the backlog this month.",
    "The product roadmap was presented to stakeholders and received approval.",
    "I will send out the meeting invite for the cross-functional sync later today.",
    "Compliance training is mandatory for all employees and must be completed by month end.",
    "The client asked for a revised timeline and we are working on an updated proposal.",
    "Server performance metrics have been stable since the latest patch deployment.",
    "The design review meeting is scheduled for Thursday at two in the afternoon.",
    "We received the signed contract from the vendor this morning.",
    "The annual report is being compiled and should be ready for distribution next week.",
    "Please ensure all expense reports are submitted before the accounting deadline.",
    "The pilot program has shown encouraging results and we plan to expand it.",
    "Our cloud infrastructure costs came in under budget for the third consecutive month.",
    "The hiring pipeline is strong with several qualified candidates in the final stage.",
    "I have updated the project tracker to reflect the revised milestones.",
    "The team celebrated the successful product launch with a dinner on Friday.",
    "We are evaluating three potential vendors for the upcoming integration project.",
    "The accessibility audit revealed several areas where we can improve the user experience.",
    "Training materials have been distributed to all new team members in the department.",
    "The quarterly business review with the executive team is confirmed for next Monday.",
    "Our documentation was updated to reflect the changes introduced in the latest release.",
    "Customer feedback highlighted the need for improved search functionality.",
    "The inventory reconciliation is complete and all discrepancies have been resolved.",
    "We received approval to proceed with the second phase of the project.",
    "The monthly newsletter will feature a spotlight on the engineering team's achievements.",
    "Performance reviews are coming up and managers should schedule one-on-ones with direct reports.",
    "The disaster recovery plan was tested successfully with no issues identified.",
]


def _generate_filler_paragraph(rng, min_words=80, max_words=250):
    """Generate a realistic filler paragraph by combining random sentences."""
    target_words = rng.randint(min_words, max_words)
    sentences = []
    total_words = 0
    available = list(_FILLER_SENTENCES)
    rng.shuffle(available)
    idx = 0
    while total_words < target_words:
        sentence = available[idx % len(available)]
        sentences.append(sentence)
        total_words += len(sentence.split())
        idx += 1
    return " ".join(sentences)


# ---------------------------------------------------------------------------
# 7. Single (filler) email generation
# ---------------------------------------------------------------------------

def generate_single_email(templates, config, email_number, seed=None):
    """Generate one random email from the topic templates.

    Parameters
    ----------
    templates : dict – output of load_templates()
    config : dict – output of load_config()
    email_number : int – ordinal for determinism
    seed : int | None

    Returns
    -------
    str – full email text
    """
    rng = random.Random(seed if seed is not None else email_number)

    employees = get_all_employees(templates["departments"])
    topics_by_dept = templates["topics"]["topics"]

    # Pick random department and topic
    dept_name = rng.choice(list(topics_by_dept.keys()))
    topic = rng.choice(topics_by_dept[dept_name])

    # Pick sender from matching department, recipient from any
    dept_employees = [e for e in employees if e["department"] == dept_name]
    sender = rng.choice(dept_employees)
    recipient = rng.choice(employees)
    # Avoid self-send
    attempts = 0
    while recipient["email"] == sender["email"] and attempts < 10:
        recipient = rng.choice(employees)
        attempts += 1

    # Optionally add CC
    cc = ""
    if rng.random() < 0.4:
        cc = sender["team_email"]

    date_range = config["emails"]["date_range"]
    date_str = random_date(date_range["start"], date_range["end"], rng)

    placeholders = _placeholder_values(rng, sender["first_name"], employees)

    subject = topic["subject_template"].format_map(placeholders)
    body_text = topic["body_template"].format_map(placeholders)

    # Ensure body meets min word count by appending filler
    min_words = config["emails"]["words_per_email"]["min"]
    max_words = config["emails"]["words_per_email"]["max"]
    word_count = len(body_text.split())
    if word_count < min_words:
        filler = _generate_filler_paragraph(rng, min_words - word_count, max_words - word_count)
        body_text = body_text.rstrip() + "\n\n" + filler

    return render_email(sender["email"], recipient["email"], cc, date_str, subject, body_text)


# ---------------------------------------------------------------------------
# 8. Needle email generation
# ---------------------------------------------------------------------------

def generate_needle_email(needle_def):
    """Generate a specific needle email from its definition in needles.yaml.

    Parameters
    ----------
    needle_def : dict – one entry from hard_needles list

    Returns
    -------
    str – full email text
    """
    return render_email(
        sender=needle_def["from"],
        recipient=needle_def["to"],
        cc=needle_def.get("cc", ""),
        date=needle_def["date"],
        subject=needle_def["subject"],
        body=needle_def["body"],
    )


# ---------------------------------------------------------------------------
# 9. Pattern email generation
# ---------------------------------------------------------------------------

def generate_pattern_email(pattern_def, index, templates, config, rng):
    """Generate one email that mentions an easy-pattern topic.

    Uses the pattern's email_subjects and body_keywords to build a relevant
    email with the appropriate topic scattered throughout.

    Parameters
    ----------
    pattern_def : dict – one entry from easy_patterns list
    index : int – which instance of this pattern (for subject cycling)
    templates : dict
    config : dict
    rng : random.Random

    Returns
    -------
    str – full email text
    """
    employees = get_all_employees(templates["departments"])

    # Pick sender from one of the pattern's departments if possible
    pattern_depts = pattern_def.get("departments", [])
    if pattern_depts:
        dept_employees = [e for e in employees if e["department"] in pattern_depts]
        if not dept_employees:
            dept_employees = employees
    else:
        dept_employees = employees

    sender = rng.choice(dept_employees)
    recipient = rng.choice(employees)
    attempts = 0
    while recipient["email"] == sender["email"] and attempts < 10:
        recipient = rng.choice(employees)
        attempts += 1

    cc = ""
    if rng.random() < 0.5:
        cc = sender["team_email"]

    date_range = config["emails"]["date_range"]
    date_str = random_date(date_range["start"], date_range["end"], rng)

    # Cycle through available subjects
    subjects = pattern_def["email_subjects"]
    subject = subjects[index % len(subjects)]

    # Build body using keywords
    keywords = pattern_def["body_keywords"]
    topic = pattern_def["topic"]

    # Create a body that weaves in the keywords naturally
    body_parts = [
        f"Hi {recipient['first_name']},",
        "",
        f"I wanted to share an update on {topic}. We have been making good progress "
        f"and I want to make sure everyone is aligned on the current status.",
        "",
    ]

    # Add keyword-rich sentences
    keyword_sentences = [
        f"The {keywords[i % len(keywords)]} aspect is progressing well and the team has been focused on delivering results."
        for i in range(rng.randint(3, 6))
    ]
    body_parts.append(" ".join(keyword_sentences))
    body_parts.append("")

    # Add filler for realistic length
    filler = _generate_filler_paragraph(rng, 40, 120)
    body_parts.append(filler)
    body_parts.append("")

    # Closing with another keyword mention
    body_parts.append(
        f"Let me know if you have any questions about {topic}. Happy to discuss further."
    )
    body_parts.append("")
    body_parts.append(f"Best,\n{sender['first_name']}")

    body = "\n".join(body_parts)

    return render_email(sender["email"], recipient["email"], cc, date_str, subject, body)


# ---------------------------------------------------------------------------
# 10. Tier building
# ---------------------------------------------------------------------------

def build_tier(tier_size, templates, config, ground_truth, seed=42):
    """Build a complete tier of emails.

    Parameters
    ----------
    tier_size : int
    templates : dict – output of load_templates()
    config : dict – output of load_config()
    ground_truth : dict – loaded ground_truth.yaml
    seed : int

    Returns
    -------
    list[str] – email text strings, length == tier_size
    """
    rng = random.Random(seed)
    emails = []

    # --- Hard needles ---
    needle_lookup = {n["id"]: n for n in templates["needles"]["hard_needles"]}

    for needle_gt in ground_truth["hard_needles"]:
        if needle_gt["first_appears_at"] <= tier_size:
            needle_id = needle_gt["id"]
            if needle_id not in needle_lookup:
                raise ValueError(
                    f"Needle '{needle_id}' referenced in ground_truth but not found "
                    f"in templates/needles.yaml"
                )
            emails.append(generate_needle_email(needle_lookup[needle_id]))

    # --- Easy patterns ---
    easy_patterns = templates["needles"].get("easy_patterns", [])
    total_pattern_emails = sum(p.get("mention_count", 10) for p in easy_patterns)

    for pattern in easy_patterns:
        count = pattern.get("mention_count", 10)
        scaled = max(2, round(count * tier_size / config["emails"]["total_count"]))
        # Don't exceed the tier size minus existing emails
        for i in range(scaled):
            email = generate_pattern_email(pattern, i, templates, config, rng)
            emails.append(email)

    # --- Fill remaining with random emails ---
    remaining = tier_size - len(emails)
    for i in range(remaining):
        email = generate_single_email(
            templates, config, email_number=i, seed=rng.randint(0, 2**31)
        )
        emails.append(email)

    # Shuffle all emails together
    rng.shuffle(emails)

    # Truncate to exact tier size (pattern minimums can overshoot for tiny tiers)
    return emails[:tier_size]


# ---------------------------------------------------------------------------
# 11. Write tier to disk
# ---------------------------------------------------------------------------

def write_tier(tier_size, emails, output_base="emails"):
    """Write email list to disk as individual .txt files.

    Creates ``{output_base}/tier_{tier_size}/email_0001.txt`` etc.
    """
    tier_dir = Path(output_base) / f"tier_{tier_size}"
    tier_dir.mkdir(parents=True, exist_ok=True)

    for idx, email_text in enumerate(emails, start=1):
        filename = f"email_{idx:04d}.txt"
        (tier_dir / filename).write_text(email_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# 12. CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate tiered email corpora for the Claude Code Scaling Benchmark."
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--output", default="emails", help="Base output directory"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    templates = load_templates("templates/")

    gt_path = Path(args.config).parent / "ground_truth.yaml"
    with open(gt_path) as f:
        ground_truth = yaml.safe_load(f)

    tiers = config["tiers"]
    for tier_size in tiers:
        print(f"Building tier {tier_size}...")
        emails = build_tier(tier_size, templates, config, ground_truth, seed=args.seed)
        write_tier(tier_size, emails, output_base=args.output)
        print(f"  -> wrote {len(emails)} emails to {args.output}/tier_{tier_size}/")

    print("Done.")


if __name__ == "__main__":
    main()
