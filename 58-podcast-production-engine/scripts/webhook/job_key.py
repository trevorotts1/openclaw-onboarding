#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE :: JOB KEY + CANONICAL SUBMISSION HASH
# webhook-design.md Section 3.1 (a redelivered webhook can never make a second
# episode)
# -----------------------------------------------------------------------------
# The invariant: one distinct submission produces at most one episode and at most
# one publish, no matter how many times its webhook is delivered.
#
#   job_key = "pd-" + <contact_id> + "-" + first16hex( sha256(canonical_submission) )
#
# - contact_id anchors the key to a person (extracted by the mapper).
# - canonical_submission is built AFTER meaning-mapping, from CANONICAL FIELDS ONLY
#   (HASH_FIELDS below), so the same submission arriving via Make.com and via a
#   Convert and Flow (GoHighLevel) webhook (different field spellings, same
#   meaning) hashes identically.
# - Volatile transport fields (delivery timestamps, event ids, execution ids,
#   signatures, retry counters, _test flags, routing hints like writing_model /
#   web_research_tool / workflow_trigger) are EXCLUDED so they cannot defeat dedup.
#
# Normalization (Section 3.1 step 3): trim whitespace, collapse internal runs of
# whitespace in answer text to single spaces, lowercase enum values, drop
# empty/null fields. Serialize as key=value lines sorted by key, joined with
# newlines; hash that. Deterministic and stdlib-only, so the hash is stable across
# machines and OpenClaw versions.
#
# Consequences: an identical redelivery collides (dedup fires); the same contact
# submitting a genuinely NEW survey (any hashed answer changed) produces a new
# hash and a new episode, which is correct for a weekly Personal Podcast.
#
# EXIT: 0 OK / 2 cannot build (no contact_id) / 3 usage.
# USAGE:
#   python3 job_key.py compute --canonical FILE   (JSON of mapped canonical fields)
#   python3 job_key.py --self-test
# =============================================================================
"""Deterministic job key and canonical submission hash for the Podcast Engine."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_NO_CONTACT = 2
EXIT_USAGE = 3

JOB_KEY_PREFIX = "pd-"
HASH_HEX_LEN = 16

# Exactly the Section 3.1 canonical fields (order irrelevant: we sort by key).
HASH_FIELDS = (
    "mode", "style", "show_name", "host_name", "first_name", "last_name",
    "preferred_pronoun", "q1_answer", "q2_answer", "q3_answer", "q4_answer",
    "q5_answer", "q6_answer", "q7_answer", "additional_info", "target_runtime",
    "tts_model", "podcast_id", "location_id", "contact_id", "publish_timestamp",
    "episode_type", "explicit",
)

ENUM_HASH_FIELDS = ("mode", "style", "episode_type", "explicit")
ANSWER_HASH_FIELDS = ("q1_answer", "q2_answer", "q3_answer", "q4_answer", "q5_answer",
                      "q6_answer", "q7_answer", "additional_info")


def _normalize_value(field, value):
    """Defensive normalization so the hash is stable regardless of how carefully
    the caller pre-normalized the canonical dict."""
    if value is None:
        return None
    text = str(value)
    if field in ANSWER_HASH_FIELDS:
        text = re.sub(r"\s+", " ", text)
    text = text.strip()
    if field in ENUM_HASH_FIELDS:
        text = text.lower()
    if text == "":
        return None
    return text


def build_canonical_submission(canonical):
    """Return the canonical submission string that gets hashed. Only HASH_FIELDS
    are considered; empty/null fields are dropped; lines are key=value sorted by
    key and newline-joined."""
    lines = []
    for field in HASH_FIELDS:
        norm = _normalize_value(field, canonical.get(field))
        if norm is None:
            continue
        lines.append("%s=%s" % (field, norm))
    lines.sort()
    return "\n".join(lines)


def canonical_hash(canonical):
    payload = build_canonical_submission(canonical)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:HASH_HEX_LEN]


def compute_job_key(canonical):
    """Return (job_key, error). error is set when contact_id is absent (the key
    cannot be anchored to a person; the caller must route to needs_input)."""
    contact_id = _normalize_value("contact_id", canonical.get("contact_id"))
    if not contact_id:
        return None, "contact_id absent: cannot anchor a job key"
    return "%s%s-%s" % (JOB_KEY_PREFIX, contact_id, canonical_hash(canonical)), None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compute the Podcast Engine job key.")
    ap.add_argument("cmd", nargs="?", choices=("compute",))
    ap.add_argument("--canonical", help="path to a JSON dict of mapped canonical fields")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.cmd != "compute":
        ap.error("a command is required (compute) or --self-test")
    if not args.canonical or not Path(args.canonical).is_file():
        ap.error("compute needs --canonical FILE")
    try:
        canonical = json.loads(Path(args.canonical).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read --canonical: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    job_key, err = compute_job_key(canonical)
    if err:
        print("ERROR: %s" % err, file=sys.stderr)
        return EXIT_NO_CONTACT
    if args.json:
        print(json.dumps({"job_key": job_key, "hash16": canonical_hash(canonical)}, indent=2))
    else:
        print(job_key)
    return EXIT_OK


# =============================================================================
# SELF-TEST
# =============================================================================
def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    base = {
        "mode": "interview_style_podcast", "style": "counter_intuitive",
        "contact_id": "CNT000000000000000wxyz", "location_id": "LOC0000000000000000abcd",
        "podcast_id": "pb-99", "first_name": "Dana",
        "q1_answer": "Everyone optimizes for speed; I optimize for silence.",
        "publish_timestamp": "2026-07-06T10:00:00Z", "explicit": "no",
    }
    k1, e1 = compute_job_key(base)
    check("job key built", e1 is None and k1 is not None)
    check("pd- prefix", k1.startswith("pd-"))
    check("contact_id anchored in key", "CNT000000000000000wxyz" in k1)
    check("hash suffix is 16 hex", bool(re.search(r"-[0-9a-f]{16}$", k1)))

    # Identical redelivery collides
    k1b, _ = compute_job_key(dict(base))
    check("identical redelivery collides", k1 == k1b)

    # Same submission, different field spelling/order/whitespace still collides
    reordered = {}
    for key in reversed(list(base.keys())):
        reordered[key] = base[key]
    reordered["q1_answer"] = "Everyone   optimizes for speed;   I optimize for silence."
    k1c, _ = compute_job_key(reordered)
    check("reorder + extra whitespace collides", k1 == k1c)

    # Volatile transport fields do NOT affect the key
    volatile = dict(base)
    volatile.update({"_test": True, "retry": True, "writing_model": "kimi-2.6",
                     "web_research_tool": "perplexity", "workflow_trigger": "field_change",
                     "eventId": "evt-abc", "delivery_ts": "2026-07-06T10:00:01Z"})
    k1d, _ = compute_job_key(volatile)
    check("volatile fields ignored", k1 == k1d)

    # A genuinely new survey (one hashed answer changed) diverges
    changed = dict(base)
    changed["q1_answer"] = "Everyone optimizes for speed; I optimize for depth."
    k2, _ = compute_job_key(changed)
    check("one-answer change diverges", k2 != k1)

    # A changed style diverges (enum is hashed)
    styled = dict(base)
    styled["style"] = "vulnerable"
    k3, _ = compute_job_key(styled)
    check("style change diverges", k3 != k1)

    # Enum case-insensitivity: PERSONAL vs personal do not create two jobs
    a = {"contact_id": "Cx1234567", "mode": "PERSONAL_PODCAST_STYLE", "style": "Vulnerable"}
    b = {"contact_id": "Cx1234567", "mode": "personal_podcast_style", "style": "vulnerable"}
    ka, _ = compute_job_key(a)
    kb, _ = compute_job_key(b)
    check("enum case folds to one key", ka == kb)

    # No contact_id -> error, no key
    k4, e4 = compute_job_key({"mode": "personal_podcast_style"})
    check("no contact_id -> error", k4 is None and e4 is not None)

    print("== job_key self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
