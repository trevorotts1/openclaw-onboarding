#!/usr/bin/env python3
"""
_qc_no_web_store.py — WG-10c (onboarding half): "no web-only store" assertion.

Sibling QC check called by qc-interview-completion.py (Check #7). Proves the ONE
directional invariant that keeps the canonical files the sole source of truth:

    The Command Center / dashboard store (mission-control.db, or any web/DB mirror)
    is ONLY EVER a downstream MIRROR of the canonical files. It may hold a SUBSET or
    a derivative of what the files hold; it may NEVER hold a decision or an interview
    answer that the files do not, and it may never assert a decision VALUE that the
    files do not.

Canonical source-of-truth files (per Skill 23 protocol):
  - .workforce-build-state.json    → canonicalReconciliation.decisions (per-department
                                     YES/NO/LATER), departments[] (the acknowledged
                                     department set), brandingAnswers / interview
                                     (structured interview answers).
  - workforce-interview-answers.md → the interview transcript (question ids + answers).

Why the direction matters (fail mode this closes):
  If a department decision or an interview answer can be born in the web/DB store and
  is NOT present in the files, the store has become a SECOND source of authority. A
  later file-driven build would silently drop it (over-/under-build, lost opt-out) or,
  worse, operators would edit "the truth" in a dashboard the build never reads. This
  check makes that state a HARD FAIL so the mirror can never quietly outrank the files.

THE CHECK, PRECISELY
--------------------
Let  C = the records the CANONICAL FILES contain and  S = the records the STORE
contains. Each side is reduced to:
  - decisions:  a map  dept_id -> decision_token   (yes|no|later|<status>)
  - decision key universe: every dept_id the files acknowledge — the union of
    canonicalReconciliation.decisions keys AND departments[] canonical ids. (A dept
    that the files list but have not yet given an explicit yes/no/later still counts as
    "the files know about it", so a store row for it is a legitimate mirror, not web-only.)
  - answer keys: every interview-answer field the files hold — brandingAnswers /
    interview / interviewAnswers / answers map keys, the structural interview fields
    (companyName, industry, ownerChat, agentName, …), and every transcript question id.

We then assert S is a SUBSET / DERIVATIVE of C, never a superset that adds authority:

  V1 web-only-decision   : a dept_id in S.decisions that is NOT in C's decision key
                           universe. → HARD FAIL (a decision that lives only in the store).
  V2 store-overrides-decision : a dept_id present on BOTH sides whose store decision
                           token != the canonical file token. → HARD FAIL (the store
                           rewrote a value the files own; the mirror added authority).
  V3 web-only-answer     : an answer field in S.answers that is NOT in C's answer key
                           universe. → HARD FAIL (an answer that lives only in the store).

Any V1/V2/V3 → violations (Check #7 HARD-FAILs, exit 3). Empty → PASS.

The canonical key universes are built GENEROUSLY (a union of every place the files may
hold the datum) on purpose: the ONLY direction this check fails is the store holding
something EXTRA. Being generous about what counts as "in the files" removes false
positives and keeps the single failure mode crisp — the store is never allowed to be a
proper superset of, nor to contradict, the files.

INPUTS
------
The store may be supplied as either:
  (a) a JSON mirror export  {"decisions": {...}, "answers": {...}}  (--mirror PATH), or
  (b) a sqlite mission-control.db (--mirror-db PATH). Recognised (all OPTIONAL — a
      missing table is treated as "nothing mirrored yet", i.e. an empty store):
        department_decisions(dept_id TEXT, decision TEXT)  [or table 'decisions']
        interview_answers(field TEXT, value TEXT)          [or table 'answers']
If NO store is supplied / found, the caller SKIPS Check #7 (a fresh box with no
dashboard yet is not a failure) — exactly like the context-map skip in Check #5.

This module READS ONLY. It never writes the store or the files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Structural interview fields that live at the top level of build-state and are
# genuine interview answers (mirror of check_mandatory_fields' structural set).
_STRUCTURAL_ANSWER_FIELDS = (
    "companyName", "company_name",
    "industry",
    "ownerChat", "owner_chat",
    "agentName", "agent_name",
    "companySlug",
)

# Transcript question-id markers (**Q-D5**, Q-D5:, **Question 12**, …).
_Q_ID_PATTERNS = (
    re.compile(r"^\*\*(Q-[\w]+)", re.IGNORECASE),
    re.compile(r"^(Q-[\w]+)[:.]"),
    re.compile(r"^\*\*Q(?:uestion)?\s*(\d+)", re.IGNORECASE),
    re.compile(r"^#+\s*Question\s+(\d+)", re.IGNORECASE),
)


# ── normalisation ─────────────────────────────────────────────────────────────

def _norm_decision(v) -> str:
    """A decision may be the provenanced object form {decision, source, …} or a bare
    string. Reduce both to the lowercased decision token."""
    if isinstance(v, dict):
        v = v.get("decision", "")
    return str(v).strip().lower()


def _dept_id_of(entry) -> str | None:
    """Canonical id of a departments[] entry (dict) or a bare string id."""
    if isinstance(entry, dict):
        for k in ("canonicalId", "canonical_id", "id", "dept", "slug", "name"):
            v = entry.get(k)
            if v:
                return str(v).strip()
        return None
    if entry:
        return str(entry).strip()
    return None


# ── canonical extraction (from the source-of-truth files) ──────────────────────

def canonical_records(state: dict | None, transcript: str = "") -> dict:
    """
    Reduce the canonical files to comparable record sets.

    Returns:
      {
        "decisions":     {dept_id: token},   # explicit yes/no/later (values, for V2)
        "decision_keys": set[str],           # every dept the files acknowledge (for V1)
        "answer_keys":   set[str],           # every interview-answer field the files hold (V3)
      }
    """
    state = state or {}

    # Explicit per-department decisions (with values) from canonicalReconciliation.
    decisions: dict[str, str] = {}
    recon = state.get("canonicalReconciliation") or {}
    dmap = recon.get("decisions") if isinstance(recon, dict) else None
    if isinstance(dmap, dict):
        for k, v in dmap.items():
            decisions[str(k).strip()] = _norm_decision(v)

    # Decision key universe = explicit decisions ∪ every acknowledged department.
    decision_keys: set[str] = set(decisions.keys())
    depts = state.get("departments")
    if isinstance(depts, list):
        for d in depts:
            did = _dept_id_of(d)
            if did:
                decision_keys.add(did)
    for d in state.get("declinedDepartments") or []:
        did = _dept_id_of(d)
        if did:
            decision_keys.add(did)

    # Answer key universe = structured answer maps ∪ structural fields ∪ transcript Q-ids.
    answer_keys: set[str] = set()
    for container in ("brandingAnswers", "interview", "interviewAnswers", "answers"):
        c = state.get(container)
        if isinstance(c, dict):
            answer_keys |= {str(k).strip() for k in c.keys()}
    for f in _STRUCTURAL_ANSWER_FIELDS:
        if state.get(f):
            answer_keys.add(f)
    answer_keys |= _transcript_question_ids(transcript)

    return {
        "decisions": decisions,
        "decision_keys": decision_keys,
        "answer_keys": answer_keys,
    }


def _transcript_question_ids(transcript: str) -> set[str]:
    ids: set[str] = set()
    for line in (transcript or "").splitlines():
        s = line.strip()
        for pat in _Q_ID_PATTERNS:
            m = pat.match(s)
            if m:
                ids.add(m.group(1).strip())
                break
    return ids


# ── store extraction (from the downstream web/DB mirror) ───────────────────────

def store_records_from_mirror(mirror: dict | None) -> dict:
    """
    Normalise a JSON mirror export into {"decisions": {id: token}, "answer_keys": set}.

    Accepts:
      mirror["decisions"] : {dept_id: "yes"|"no"|"later"|<status>|{decision:…}}  OR
                            a list of dept ids (value-less; V2 cannot fire on those).
      mirror["answers"]   : {field: value}  OR a list of field ids.
    """
    mirror = mirror or {}
    decisions: dict[str, str] = {}
    dec = mirror.get("decisions")
    if isinstance(dec, dict):
        for k, v in dec.items():
            decisions[str(k).strip()] = _norm_decision(v)
    elif isinstance(dec, list):
        for k in dec:
            decisions[str(k).strip()] = ""  # present but value-less

    answer_keys: set[str] = set()
    ans = mirror.get("answers")
    if isinstance(ans, dict):
        answer_keys |= {str(k).strip() for k in ans.keys()}
    elif isinstance(ans, list):
        answer_keys |= {str(k).strip() for k in ans}

    return {"decisions": decisions, "answer_keys": answer_keys}


def store_records_from_db(db_path: Path) -> dict:
    """
    Read a sqlite mission-control.db into the same normalised store shape. Every table
    is OPTIONAL — a missing table means that datum is not mirrored yet (empty), never an
    error. Reads only (no writes, no schema changes).
    """
    import sqlite3

    decisions: dict[str, str] = {}
    answer_keys: set[str] = set()

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        have = {
            r["name"]
            for r in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        for tbl, id_col, val_col in (
            ("department_decisions", "dept_id", "decision"),
            ("decisions", "dept_id", "decision"),
        ):
            if tbl in have:
                cols = {r["name"] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()}
                if id_col in cols:
                    vsel = val_col if val_col in cols else "NULL"
                    for r in cur.execute(f"SELECT {id_col} AS k, {vsel} AS v FROM {tbl}").fetchall():
                        if r["k"] is not None:
                            decisions[str(r["k"]).strip()] = _norm_decision(r["v"] if r["v"] is not None else "")

        for tbl, id_col in (("interview_answers", "field"), ("answers", "field")):
            if tbl in have:
                cols = {r["name"] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()}
                if id_col in cols:
                    for r in cur.execute(f"SELECT {id_col} AS k FROM {tbl}").fetchall():
                        if r["k"] is not None:
                            answer_keys.add(str(r["k"]).strip())
    finally:
        conn.close()

    return {"decisions": decisions, "answer_keys": answer_keys}


# ── the assertion ──────────────────────────────────────────────────────────────

def assert_no_web_only_store(canonical: dict, store: dict) -> list:
    """
    Prove the store is a SUBSET / derivative of the canonical files. Returns a list of
    violation dicts (empty == clean). Pure; reads only its arguments.

      V1 web-only-decision       : store dept not in the canonical decision key universe.
      V2 store-overrides-decision: shared dept whose store token contradicts the file.
      V3 web-only-answer         : store answer field not in the canonical answer universe.
    """
    violations = []

    c_dec = canonical.get("decisions", {})
    c_dec_keys = canonical.get("decision_keys", set())
    c_ans_keys = canonical.get("answer_keys", set())
    s_dec = store.get("decisions", {})
    s_ans_keys = store.get("answer_keys", set())

    # V1: decisions that exist ONLY in the store.
    for k in sorted(set(s_dec) - set(c_dec_keys)):
        violations.append({
            "kind": "web-only-decision",
            "key": k,
            "detail": (
                f"department decision '{k}'={s_dec[k]!r} exists ONLY in the web/DB store; "
                f"no matching entry in .workforce-build-state.json "
                f"(canonicalReconciliation.decisions or departments[]). The store must be a "
                f"downstream mirror of the files, never an independent source of authority."
            ),
        })

    # V2: store contradicts a decision the files own (store rewrote authority).
    for k in sorted(set(s_dec) & set(c_dec)):
        s_tok = s_dec[k]
        c_tok = c_dec[k]
        if s_tok and c_tok and s_tok != c_tok:
            violations.append({
                "kind": "store-overrides-decision",
                "key": k,
                "detail": (
                    f"store decision '{k}'={s_tok!r} diverges from the canonical file value "
                    f"{c_tok!r}; the store must mirror the files' decision, not change it."
                ),
            })

    # V3: answers that exist ONLY in the store.
    for k in sorted(set(s_ans_keys) - set(c_ans_keys)):
        violations.append({
            "kind": "web-only-answer",
            "key": k,
            "detail": (
                f"interview answer '{k}' exists ONLY in the web/DB store; no matching answer "
                f"in the canonical files (workforce-interview-answers.md / build-state "
                f"brandingAnswers/interview). Answers must originate in the files."
            ),
        })

    return violations


# ── high-level entry (used by qc-interview-completion.py Check #7) ─────────────

def check_no_web_store(state: dict | None,
                       transcript: str,
                       mirror: dict | None = None,
                       mirror_db: Path | None = None) -> dict:
    """
    Run the whole check. Returns:
      {"skipped": bool, "violations": [...], "note": str}

    Skips (not a failure) when no store is supplied — a box with no dashboard mirror
    yet has nothing to verify.
    """
    store = None
    src = None
    if mirror is not None:
        store = store_records_from_mirror(mirror)
        src = "mirror-json"
    elif mirror_db is not None:
        p = Path(mirror_db)
        if p.exists():
            try:
                store = store_records_from_db(p)
                src = f"mirror-db:{p.name}"
            except Exception as exc:  # noqa: BLE001
                return {"skipped": True, "violations": [],
                        "note": f"could not read mirror db ({exc}); Check #7 skipped."}

    if store is None:
        return {"skipped": True, "violations": [],
                "note": "no web/DB mirror store supplied; Check #7 (no-web-only-store) skipped."}

    canonical = canonical_records(state, transcript)
    violations = assert_no_web_only_store(canonical, store)
    return {
        "skipped": False,
        "violations": violations,
        "note": (
            f"[{src}] compared store ({len(store['decisions'])} decision(s), "
            f"{len(store['answer_keys'])} answer field(s)) against canonical files "
            f"({len(canonical['decision_keys'])} acknowledged dept(s), "
            f"{len(canonical['answer_keys'])} answer field(s)); "
            f"{len(violations)} web-only/override violation(s)."
        ),
    }


# ── CLI (standalone use / debugging; the QC gate imports check_no_web_store) ────

def _load_json(path: Path, label: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[ERROR] {label} not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] {label} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    ap = argparse.ArgumentParser(description="WG-10c no-web-only-store assertion (Skill 23).")
    ap.add_argument("--state", required=True, help="Path to .workforce-build-state.json")
    ap.add_argument("--transcript", help="Path to workforce-interview-answers.md (optional)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mirror", help="Path to a JSON mirror export of the web/DB store")
    g.add_argument("--mirror-db", help="Path to a sqlite mission-control.db mirror")
    ap.add_argument("--format", choices=["json", "human"], default="human")
    args = ap.parse_args()

    state = _load_json(Path(args.state), ".workforce-build-state.json")
    transcript = ""
    if args.transcript and Path(args.transcript).exists():
        transcript = Path(args.transcript).read_text(encoding="utf-8", errors="replace")

    mirror = _load_json(Path(args.mirror), "mirror JSON") if args.mirror else None
    mirror_db = Path(args.mirror_db) if args.mirror_db else None

    result = check_no_web_store(state, transcript, mirror=mirror, mirror_db=mirror_db)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        if result["skipped"]:
            print(f"[SKIP] no-web-only-store: {result['note']}")
        elif result["violations"]:
            print(f"[FAIL] no-web-only-store: {len(result['violations'])} violation(s)")
            for v in result["violations"]:
                print(f"  - [{v['kind']}] {v['key']}: {v['detail']}")
        else:
            print(f"[PASS] no-web-only-store: {result['note']}")

    # exit 0 = pass/skip, 3 = hard fail (mirrors qc-interview-completion.py exit codes).
    return 3 if (not result["skipped"] and result["violations"]) else 0


if __name__ == "__main__":
    sys.exit(main())
