#!/usr/bin/env python3
"""
prove_zhe_web_parity_fixture.py — self-contained fixture generator for the
WEB-vs-TELEGRAM build-parity proof (WG-6 onboarding half; consumed by
prove-zhe.py --web-parity).

WHY A GENERATOR, NOT A STATIC BLOB
----------------------------------
The parity proof needs two FULL, gate-passing OpenClaw roots — each with a
~4000-row section-tagged coaching-personas index, 40+ persona dirs, a live
Command Center mission-control.db, registered dept agents, an AGENTS.md carrying
every ZHE doctrine marker, a genuine interview transcript, full provenanced
decision coverage, and an equalityOk provisioning receipt. Committing that as a
binary/40-dir blob would be bulky and un-reviewable. Instead THIS module IS the
fixture: it deterministically materializes both roots into a caller-provided
directory. The code is the spec, and it is trivially auditable.

THE PARITY CLAIM IT SETS UP
---------------------------
A client built through the WEB /interview path and one built through TELEGRAM
run the SAME canonical scripts, so they must land BYTE-EQUAL canonical artifacts
and an EQUAL provisioning receipt / expected-set. build_pair() writes a
`web` root and a `ref` (telegram) root whose canonical set fields
(expectedSet / builtSet / declined / later / acceptedCustoms / equalityOk) are
identical. The ONLY intended difference is decision provenance `source`
("web-interview" vs "telegram-interview") and the transcript banner — neither of
which may perturb the receipt.

SEEDED SHORTCUTS (applied to the WEB root only)
-----------------------------------------------
build_pair(dest, shortcut=...) can inject exactly one genuine-build defect so
the prover can be shown to FAIL LOUDLY (non-vacuous):
  * "missing-decision"       — drop one expected dept's provenanced decision.
  * "synthetic-header"       — stamp the Non-Interactive (from-config) banner on
                               the transcript with NO ownerConsent record
                               (a fabricated transcript).
  * "unprovenanced-decline"  — record the decline as a bare "no" string with no
                               provenance and no ownerDeclineConfirmed gate.
  * "receipt-divergence"     — perturb the WEB receipt's expected/built set so it
                               no longer equals the reference receipt.
Each leaves the FIVE base ZHE gates green (they do not inspect provenance /
transcript genuineness), which is exactly why the parity mode adds the
genuineness + receipt-equality gates on top.

Dependency-free (stdlib json/os/sqlite3 only). Writes ONLY under `dest`.
Never touches ~/.openclaw or ~/.clawdbot.
"""
import json
import os
import sqlite3

# The exact banner build-workforce.build_from_config() stamps onto a
# synthetically-assembled (from-config, non-interactive) transcript. Kept in
# lock-step with qc-interview-completion.NON_INTERACTIVE_ANSWERS_HEADER and
# re-declared in prove-zhe.py; a transcript carrying it without an ownerConsent
# record is a fabricated transcript.
NON_INTERACTIVE_ANSWERS_HEADER = "# Workforce Interview Answers (Non-Interactive)"

# Built floor for the fixture. Slugs are single-token (no hyphens/underscores) so
# folder-name == agent-slug == CC-lane-token == normalized-receipt-id, keeping the
# fixture's intent legible (the prover's own normalization is exercised elsewhere).
BUILT_DEPTS = ["sales", "marketing", "operations", "finance", "support", "hr"]
# A genuinely, provenance-declined department: recorded "no", NOT built, NOT on disk.
DECLINED_DEPT = "legal"

PERSONA_COUNT = 45           # clears prove-zhe PERSONA_LIBRARY_FLOOR (40)
INDEX_ROWS = 4413            # matches prove-zhe EXPECTED_INDEX_ROWS (floor ~3971)

VALID_SHORTCUTS = (
    "missing-decision",
    "synthetic-header",
    "unprovenanced-decline",
    "receipt-divergence",
)

AGENTS_MD = """# AGENTS.md — Fixture Master Agent Doctrine

<!-- CEO_ORCHESTRATOR_RULE_V1 -->
The CEO agent routes every task to the right department. CEO_ROUTING_NO_LOOPHOLES_V1.

<!-- PERSONA_REFLEX_V1 -->
Persona reflex: match the coaching/leadership persona before acting.

<!-- FULL_CONTEXT_HANDOFF_V1 -->
Full-context handoff: every delegation carries pointer references to where the
documentation lives.

<!-- OWNER_REPORTING_V1 -->
Reporting to the owner: report back to the owner in plain language.

<!-- PLATFORM_FACTS_V1 -->
Platform facts: here is WHERE your environment file lives and how the box is wired.
"""

GENUINE_TRANSCRIPT_QA = [
    ("What is your company name?", "Northwind Trading Co."),
    ("What industry are you in?", "Wholesale distribution."),
    ("Who is the primary owner contact?", "Dana the operations lead."),
    ("What does your sales team do today?", "Outbound calls and quote follow-up."),
    ("How do you handle marketing?", "Email newsletters and a small ad budget."),
    ("Describe your operations workload.", "Order routing and supplier coordination."),
    ("What finance tasks recur?", "Invoicing, AP/AR, monthly close."),
    ("How is customer support staffed?", "Two reps on a shared inbox."),
    ("What HR work do you have?", "Onboarding and PTO tracking."),
    ("Do you need a legal department?", "No — we outsource legal to a firm."),
    ("What is your busiest season?", "Q4 holiday restock."),
    ("What tools do you use?", "A spreadsheet stack and one CRM."),
    ("What is your biggest bottleneck?", "Manual quote handoffs between sales and ops."),
    ("Who approves new spend?", "Dana and the owner jointly."),
    ("How many people are on the team?", "Eleven full-time."),
    ("What would a win look like in 90 days?", "Quotes out same-day, zero dropped orders."),
    ("Any compliance constraints?", "Standard retail; nothing special."),
    ("What is your brand voice?", "Direct, friendly, no fluff."),
    ("What reporting do you want?", "A weekly owner digest."),
    ("Where should the workforce escalate?", "To Dana first, then the owner."),
    ("What decisions do you want automated?", "Quote routing and follow-up nudges."),
    ("What must stay human?", "Final pricing on large accounts."),
    ("What is your growth target?", "Twenty percent revenue next year."),
    ("Any departments you explicitly do NOT want?", "Legal — outsourced."),
    ("Confirm the six departments to build?", "Sales, marketing, operations, finance, support, HR."),
]


def _slug_norm(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _build_decisions(source, shortcut):
    """canonicalReconciliation.decisions map with full provenance for every
    built dept (yes) + the declined dept (no)."""
    decided_at = "2026-07-04T12:00:00+00:00"
    decisions = {}
    for slug in BUILT_DEPTS:
        if shortcut == "missing-decision" and slug == "finance":
            # DROP finance's decision entirely — expected-but-undecided.
            continue
        decisions[slug] = {
            "decision": "yes",
            "source": source,
            "decidedAt": decided_at,
            "decidedBy": "owner:dana",
        }
    if shortcut == "unprovenanced-decline":
        # Bare-string "no" with no provenance and no owner-confirm gate: the
        # shared reader REJECTS it (decline ignored / un-provenanced).
        decisions[DECLINED_DEPT] = "no"
    else:
        decisions[DECLINED_DEPT] = {
            "decision": "no",
            "source": source,
            "decidedAt": decided_at,
            "decidedBy": "owner:dana",
        }
    return decisions


def _build_state(source, shortcut):
    recon = {
        "decisions": _build_decisions(source, shortcut),
        # ownerDeclineConfirmed is the block-level gate for bare-string declines;
        # withhold it for the unprovenanced-decline shortcut so the bare "no"
        # cannot be silently honored.
        "ownerDeclineConfirmed": shortcut != "unprovenanced-decline",
    }
    state = {
        "version": 1,
        "interviewComplete": True,
        "interviewCompletedAt": "2026-07-04T12:05:00+00:00",
        "interviewVersion": "web-parity-fixture-v1",
        "ownerChat": 1234567890,
        "ownerName": "Dana",
        "companyName": "Northwind Trading Co.",
        "companySlug": "northwind-trading",
        "clientSlug": "northwind-trading",
        "industry": "Wholesale distribution",
        "agentName": "Atlas",
        "departments": [{"slug": s, "name": s.title(), "status": "done"} for s in BUILT_DEPTS],
        "canonicalReconciliation": recon,
        "interviewProgress": {"lastQuestionNumber": len(GENUINE_TRANSCRIPT_QA)},
    }
    return state


def _receipt(shortcut, is_web):
    expected = sorted(_slug_norm(s) for s in BUILT_DEPTS)
    built = list(expected)
    if shortcut == "receipt-divergence" and is_web:
        # WEB over-provisions relative to the reference: build an extra dept and
        # drop one expected — receipt no longer equals the reference receipt.
        built = sorted(set(built) - {"hr"} | {"logistics"})
    missing_from_built = sorted(set(expected) - set(built))
    extra = sorted(set(built) - set(expected))
    equality_ok = not (missing_from_built or extra)
    return {
        "schema": "provisioning-receipt/v1",
        "company": "Northwind Trading Co.",
        "generatedAt": "2026-07-04T12:10:00+00:00",
        "declined": [_slug_norm(DECLINED_DEPT)],
        "later": [],
        "acceptedCustoms": [],
        "mergedAwayCustoms": [],
        "verticalAdded": [],
        "expectedSet": expected,
        "builtSet": built,
        "expectedCount": len(expected),
        "builtCount": len(built),
        "missingFromBuilt": missing_from_built,
        "declinedButBuilt": sorted(set(built) & {_slug_norm(DECLINED_DEPT)}),
        "extraBeyondExpected": extra,
        "equalityOk": equality_ok,
        "reason": "fixture receipt",
    }


def _transcript(shortcut):
    lines = []
    if shortcut == "synthetic-header":
        # Fabricated: from-config banner, and _build_state withholds ownerConsent.
        lines.append(NON_INTERACTIVE_ANSWERS_HEADER)
    else:
        lines.append("# Workforce Interview Answers")
    lines.append("")
    for i, (q, a) in enumerate(GENUINE_TRANSCRIPT_QA, start=1):
        lines.append(f"**Q{i}** {q}")
        lines.append(f"**A** {a}")
        lines.append("")
    return "\n".join(lines) + "\n"


def _seed_persona_index(db_path):
    """Materialize a section-tagged coaching-personas index: `embeddings` table
    with mode + section_number columns, INDEX_ROWS rows, all section-tagged."""
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE embeddings ("
            "id INTEGER PRIMARY KEY, persona TEXT, chunk TEXT, "
            "mode TEXT DEFAULT 'both', section_number INTEGER)"
        )
        modes = ("leadership", "coaching", "both")
        rows = []
        for i in range(INDEX_ROWS):
            mode = modes[i % 3]
            section = (i % 12) + 1  # never NULL => genuinely section-tagged
            rows.append((i, f"persona-{i % PERSONA_COUNT:02d}", f"chunk-{i}", mode, section))
        cur.executemany(
            "INSERT INTO embeddings (id, persona, chunk, mode, section_number) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def _seed_mission_control(db_path):
    """Materialize the Command Center board: `workspaces` table with one lane row
    per built department (schema mirrors 32-.../seed-workspaces.py)."""
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE workspaces ("
            "id TEXT PRIMARY KEY, name TEXT, slug TEXT UNIQUE, "
            "description TEXT, icon TEXT, company_id TEXT)"
        )
        cur.executemany(
            "INSERT INTO workspaces (id, name, slug, description, icon, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(f"ws-{s}", s.title(), s, f"{s.title()} department", "🗂", "northwind")
             for s in BUILT_DEPTS],
        )
        conn.commit()
    finally:
        conn.close()


def _build_root(root, source, shortcut, is_web):
    """Materialize ONE complete gate-passing OpenClaw root at `root`."""
    ws = os.path.join(root, "workspace")
    os.makedirs(ws, exist_ok=True)

    # openclaw.json — dept agents registered as `dept-<slug>` (check a).
    cfg = {
        "agents": {
            "list": [{"id": f"dept-{s}", "name": s.title()} for s in BUILT_DEPTS],
        }
    }
    _write_json(os.path.join(root, "openclaw.json"), cfg)

    # departments/ folders on disk (check a).
    for s in BUILT_DEPTS:
        os.makedirs(os.path.join(ws, "departments", s), exist_ok=True)

    # build-state + genuine transcript + receipt.
    _write_json(os.path.join(ws, ".workforce-build-state.json"),
                _build_state(source, shortcut))
    with open(os.path.join(ws, "workforce-interview-answers.md"), "w",
              encoding="utf-8") as f:
        f.write(_transcript(shortcut if is_web else None))
    _write_json(os.path.join(ws, "provisioning-receipt.json"),
                _receipt(shortcut if is_web else None, is_web))

    # AGENTS.md doctrine markers (check d).
    with open(os.path.join(ws, "AGENTS.md"), "w", encoding="utf-8") as f:
        f.write(AGENTS_MD)

    # coaching-personas: dirs + categories + section-tagged index (check b).
    cp = os.path.join(ws, "data", "coaching-personas")
    personas_dir = os.path.join(cp, "personas")
    os.makedirs(personas_dir, exist_ok=True)
    cat_personas = {}
    for i in range(PERSONA_COUNT):
        name = f"persona-{i:02d}"
        os.makedirs(os.path.join(personas_dir, name), exist_ok=True)
        cat_personas[name] = {"domain": "leadership" if i % 2 else "coaching"}
    _write_json(os.path.join(cp, "persona-categories.json"),
                {"personas": cat_personas,
                 "domainTags": ["leadership", "coaching", "sales", "operations"]})
    _seed_persona_index(os.path.join(cp, "gemini-index.sqlite"))

    # Command Center board (check c).
    _seed_mission_control(os.path.join(ws, "mission-control.db"))
    return root


def build_pair(dest, shortcut=None):
    """Materialize a (web_root, ref_root) pair under `dest`.

    ref  = TELEGRAM-built reference (always clean).
    web  = WEB /interview-built root; `shortcut` (if given) seeds a genuine-build
           defect into the WEB root ONLY.

    Returns (web_root, ref_root) absolute paths.
    """
    if shortcut is not None and shortcut not in VALID_SHORTCUTS:
        raise ValueError(f"unknown shortcut {shortcut!r}; valid: {VALID_SHORTCUTS}")
    dest = os.path.abspath(dest)
    web_root = os.path.join(dest, "web")
    ref_root = os.path.join(dest, "ref")
    _build_root(ref_root, "telegram-interview", None, is_web=False)
    _build_root(web_root, "web-interview", shortcut, is_web=True)
    return web_root, ref_root


def _cli(argv):
    import argparse
    p = argparse.ArgumentParser(description="Materialize the web/telegram parity fixture pair.")
    p.add_argument("dest", help="destination dir (must be a sandbox/temp dir)")
    p.add_argument("--shortcut", choices=VALID_SHORTCUTS, default=None)
    ns = p.parse_args(argv[1:])
    web, ref = build_pair(ns.dest, shortcut=ns.shortcut)
    print(json.dumps({"web_root": web, "ref_root": ref, "shortcut": ns.shortcut}))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv))
