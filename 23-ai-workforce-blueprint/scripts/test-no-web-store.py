#!/usr/bin/env python3
"""
test-no-web-store.py — WG-10c lock: the web/DB store is a MIRROR, never a source.

Proves _qc_no_web_store.assert_no_web_only_store() enforces the single directional
invariant that keeps the canonical files the sole source of truth: the Command Center /
dashboard store may hold a SUBSET / derivative of the files, but NEVER a department
decision or interview answer that lives only in the store, and never a decision value
that contradicts the files.

Structure mirrors test-dept-domain-mirror.py:
  REAL DATA (must be clean)  — a PASSING fixture: a mirror derived from the files.
  NO-WEAKENING               — FAILING fixtures: each violation class (web-only decision,
                               store-overrides-decision, web-only answer) MUST be caught,
                               proving the check is non-vacuous.
Also exercises the sqlite mirror reader (store_records_from_db) against a temp DB and
the high-level check_no_web_store() skip/fail paths.

Touches NO live DB, network, or ~/.openclaw: every fixture is built in-memory or in a
tempdir. Reads only.

EXIT: 0 = every assertion (incl. every NO-WEAKENING case) passed; 1 otherwise.
Usage:  python3 test-no-web-store.py [REPO_ROOT]
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _qc_no_web_store as M  # noqa: E402

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


# ── the canonical FILES (source of truth) ──────────────────────────────────────
# .workforce-build-state.json — owner made three per-department decisions and a
# fourth department is acknowledged (in departments[]) but not yet given a token.
STATE = {
    "companyName": "Acme Co",
    "industry": "roofing",
    "canonicalReconciliation": {
        "decisions": {
            "sales":     {"decision": "yes",   "source": "owner-interview",
                          "decidedAt": "2026-07-04T00:00:00Z", "decidedBy": "owner"},
            "marketing": {"decision": "no",    "source": "owner-interview",
                          "decidedAt": "2026-07-04T00:00:00Z", "decidedBy": "owner"},
            "finance":   {"decision": "later", "source": "owner-interview",
                          "decidedAt": "2026-07-04T00:00:00Z", "decidedBy": "owner"},
        },
    },
    "departments": [
        {"canonicalId": "sales",   "status": "building"},
        {"canonicalId": "support", "status": "pending"},  # acknowledged, no explicit token
    ],
    "brandingAnswers": {
        "logoStyle": "wordmark",
        "primaryColor": "#0a0a0a",
    },
}

# workforce-interview-answers.md — transcript with two question ids.
TRANSCRIPT = (
    "# Workforce Interview Answers\n\n"
    "**Q-D1** What does the company do?\n"
    "> We install and repair roofs.\n\n"
    "---\n\n"
    "**Q-D2** Who is the owner?\n"
    "> Jane, the founder.\n"
)

CANON = M.canonical_records(STATE, TRANSCRIPT)


# ══════════════════ REAL DATA — a faithful mirror MUST be clean ════════════════
print("=" * 70)
print("NO-WEB-ONLY-STORE LOCK — store must be a SUBSET/derivative of the files")
print("=" * 70)
print(f"canonical decision keys : {sorted(CANON['decision_keys'])}")
print(f"canonical answer keys   : {sorted(CANON['answer_keys'])}")

print("-" * 70)
print("REAL DATA (a mirror derived from the files must be CLEAN)")
print("-" * 70)

# PASSING fixture: a proper downstream mirror — a subset of decisions with IDENTICAL
# tokens, an acknowledged-but-untokened dept row (support), and a subset of answers.
GOOD_MIRROR = {
    "decisions": {
        "sales": "yes",         # same token as the file
        "marketing": "no",      # same token as the file
        "support": "pending",   # in departments[] → acknowledged by the files
    },
    "answers": {
        "logoStyle": "wordmark",   # subset of brandingAnswers
        "Q-D1": "We install and repair roofs.",  # a transcript question id
        "companyName": "Acme Co",
    },
}
good_store = M.store_records_from_mirror(GOOD_MIRROR)
good_viol = M.assert_no_web_only_store(CANON, good_store)
if not good_viol:
    ok("faithful mirror (subset + matching tokens) produces ZERO violations")
else:
    bad(f"faithful mirror wrongly flagged {len(good_viol)} violation(s): "
        + "; ".join(v["kind"] + ":" + v["key"] for v in good_viol))

# An EMPTY store (nothing mirrored yet) is trivially a subset → clean.
empty_viol = M.assert_no_web_only_store(CANON, M.store_records_from_mirror({}))
if not empty_viol:
    ok("empty store (nothing mirrored yet) is clean")
else:
    bad(f"empty store wrongly flagged {len(empty_viol)} violation(s)")


# ══════════════════ NO-WEAKENING — each violation class MUST fire ══════════════
print("-" * 70)
print("NO-WEAKENING (each web-only / override class must be caught)")
print("-" * 70)


def expect_kind(label, violations, kind, key):
    hit = [v for v in violations if v["kind"] == kind and v["key"] == key]
    if hit:
        ok(f"{label}: caught {kind} for {key!r}")
    else:
        bad(f"{label}: did NOT catch {kind} for {key!r} — check is too weak "
            f"(got {[v['kind'] + ':' + v['key'] for v in violations]})")


# V1 — a department decision present ONLY in the store (the headline failing fixture).
web_only_dec = M.store_records_from_mirror({
    "decisions": {"sales": "yes", "hr": "yes"},  # 'hr' is nowhere in the files
})
expect_kind("V1 web-only-decision",
            M.assert_no_web_only_store(CANON, web_only_dec),
            "web-only-decision", "hr")

# V2 — the store contradicts a decision the files own (yes → no).
override_dec = M.store_records_from_mirror({
    "decisions": {"sales": "no"},  # file says 'yes'
})
expect_kind("V2 store-overrides-decision",
            M.assert_no_web_only_store(CANON, override_dec),
            "store-overrides-decision", "sales")

# V3 — an interview answer present ONLY in the store.
web_only_ans = M.store_records_from_mirror({
    "answers": {"secretPricingTier": "gold"},  # nowhere in files
})
expect_kind("V3 web-only-answer",
            M.assert_no_web_only_store(CANON, web_only_ans),
            "web-only-answer", "secretPricingTier")

# A combined store that adds authority on all three axes at once.
combined = M.store_records_from_mirror({
    "decisions": {"hr": "yes", "marketing": "yes"},  # hr web-only; marketing override(no→yes)
    "answers": {"secretPricingTier": "gold"},
})
kinds = {v["kind"] for v in M.assert_no_web_only_store(CANON, combined)}
if {"web-only-decision", "store-overrides-decision", "web-only-answer"} <= kinds:
    ok("combined store adding authority on all 3 axes is caught on all 3")
else:
    bad(f"combined store missed some axis; caught only {sorted(kinds)}")

# A store that only MIRRORS a subset (drops finance, drops a branding answer) is fine —
# a mirror is allowed to be behind / smaller than the files.
subset_only = M.store_records_from_mirror({"decisions": {"sales": "yes"}, "answers": {}})
if not M.assert_no_web_only_store(CANON, subset_only):
    ok("a store that mirrors only a SUBSET (never a superset) is clean")
else:
    bad("a legitimate subset mirror was wrongly flagged")


# ══════════════════ sqlite mirror reader + high-level entry ════════════════════
print("-" * 70)
print("sqlite mirror reader + check_no_web_store() skip/fail paths")
print("-" * 70)

with tempfile.TemporaryDirectory() as td:
    db = Path(td) / "mission-control.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE department_decisions (dept_id TEXT, decision TEXT)")
    conn.execute("CREATE TABLE interview_answers (field TEXT, value TEXT)")
    # Mirror rows: one faithful, one web-only decision, one web-only answer.
    conn.executemany("INSERT INTO department_decisions VALUES (?,?)",
                     [("sales", "yes"), ("hr", "yes")])
    conn.executemany("INSERT INTO interview_answers VALUES (?,?)",
                     [("logoStyle", "wordmark"), ("secretPricingTier", "gold")])
    conn.commit()
    conn.close()

    db_store = M.store_records_from_db(db)
    if db_store["decisions"].get("sales") == "yes" and "hr" in db_store["decisions"] \
            and "secretPricingTier" in db_store["answer_keys"]:
        ok("store_records_from_db read decisions + answers from sqlite mirror")
    else:
        bad(f"store_records_from_db read wrong rows: {db_store}")

    res = M.check_no_web_store(STATE, TRANSCRIPT, mirror_db=db)
    kinds = {v["kind"] for v in res["violations"]}
    if not res["skipped"] and {"web-only-decision", "web-only-answer"} <= kinds:
        ok("check_no_web_store(mirror_db=...) HARD-FAILs on web-only rows")
    else:
        bad(f"check_no_web_store db path wrong: skipped={res['skipped']} kinds={sorted(kinds)}")

# No store supplied → SKIP (not a failure).
skip_res = M.check_no_web_store(STATE, TRANSCRIPT)
if skip_res["skipped"] and not skip_res["violations"]:
    ok("check_no_web_store with no store supplied SKIPS (fresh box, no dashboard)")
else:
    bad(f"no-store path did not skip cleanly: {skip_res}")

# Faithful JSON mirror through the high-level entry → clean, not skipped.
good_res = M.check_no_web_store(STATE, TRANSCRIPT, mirror=GOOD_MIRROR)
if not good_res["skipped"] and not good_res["violations"]:
    ok("check_no_web_store(mirror=faithful) is clean and NOT skipped")
else:
    bad(f"faithful mirror through entry wrong: {good_res}")


print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
