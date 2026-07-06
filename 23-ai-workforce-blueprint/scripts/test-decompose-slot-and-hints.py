#!/usr/bin/env python3
"""
test-decompose-slot-and-hints.py — DEP-4 matcher-side contract lock (F3.7 + F3.9).

Locks the four DEP-4 invariants, HERMETICALLY (no live persona DB is read or
written: select_persona / record_selection / DB resolution are monkeypatched, so
this suite can never clobber the operator's own workspace — the skill-23
state-script hazard):

  T1 DEPT-HINT CANONICAL LOCK (F3.7)
      Every _DEPT_HINT_KEYWORDS target is a LIVE canonical DEPT_DOMAIN_TAGS key
      (idempotent under canonical_dept_slug) — no dead slug (creative/billing/
      hr/operations) survives. Mirrors test-dept-domain-mirror.py's philosophy.

  T2 MECHANICAL GATE SINGLE-SOURCE (F3.7 sub-gap 3)
      The decomposer imports the SAME shared-utils/mechanical-gate.py classifier;
      the BASE shell-command rule is identical for selector + decompose, and the
      DELIVERY_VERBS extension applies to the per-subtask gate ONLY.

  T3 SLOT-DRIVEN MULTI-PERSONA (F3.9)
      combined_select(slots=[...]) SKIPS text decomposition, uses slots as the
      authoritative sub-task list, forces each slot's task_category, folds the
      task audience into the content slot's sub-task text, and assigns a DISTINCT
      persona per slot (the multi-persona contract).

  T4 NO-NAKED FALLBACK (F3.9 -> F3.1)
      A REQUIRED slot that comes back empty is backfilled with
      DEFAULT_PERSONA_FALLBACK (never empty); a mechanical sub-task keeps
      no_persona_required=True but carries GOVERNANCE_PERSONA_FALLBACK — so NO
      sub-task is ever dispatched naked.

Each check also has a NO-WEAKENING probe proving it FAILS on injected drift.

EXIT: 0 = all passed (incl. every NO-WEAKENING case); 1 otherwise.
Usage: python3 test-decompose-slot-and-hints.py [REPO_ROOT]
"""
import ast
import importlib.util
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
sys.path.insert(0, str(REPO / "shared-utils"))
from canonical_slug import canonical_dept_slug  # noqa: E402

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


# ── Load the decompose module BY PATH, then neutralise every DB/selection touch
# so the whole suite is hermetic (no persona DB read/write). ──────────────────
def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dt = _load_module(SCRIPTS / "decompose-task.py", "decompose_task_under_test")

# The live DEPT_DOMAIN_TAGS the selector actually looks up at runtime.
DEPT_DOMAIN_TAGS = dt._SEL.DEPT_DOMAIN_TAGS
LIVE_KEYS = set(DEPT_DOMAIN_TAGS.keys())

_SENTINEL_EMPTY = "no persona exists for this slot on an empty universe"


def _fake_select_persona(subtask_text, dept, mode, weights, paths, db_path, variety=True):
    """Deterministic in-memory persona: distinct per subtask text; empty on the
    sentinel so the REQUIRED-slot fallback can be exercised."""
    if _SENTINEL_EMPTY in (subtask_text or ""):
        return {"persona_id": None, "warning": "NO_PERSONAS_AVAILABLE",
                "message": "no persona available", "score": 0.0}
    pid = "persona-" + str(abs(hash(subtask_text)) % 100000)
    return {"persona_id": pid, "persona_name": pid.replace("-", " ").title(),
            "score": 0.8, "layers": {"task_fit": 0.8}, "interaction_mode": mode}


# Hermetic patches — combined_select resolves these globals at call time.
dt.select_persona = _fake_select_persona
dt.record_selection = lambda *a, **k: None
dt.find_dashboard_db = lambda: Path("/nonexistent/hermetic.db")
dt.is_db_found = lambda p: False
dt.get_openclaw_paths = lambda: {}


# ─────────────────────────── T1 — DEPT-HINT CANONICAL LOCK ─────────────────────
print("=" * 70)
print("T1  DEPT-HINT CANONICAL LOCK (F3.7)")
print("=" * 70)


def check_hint_targets_live(hint_pairs, live_keys):
    """Return list of problems: any hint dept not a live idempotent-canonical key."""
    probs = []
    for kws, dept in hint_pairs:
        if canonical_dept_slug(dept) != dept:
            probs.append(f"hint {kws[0]!r}->{dept!r} is not idempotent-canonical "
                         f"(canonical_dept_slug -> {canonical_dept_slug(dept)!r})")
        elif dept not in live_keys:
            probs.append(f"hint {kws[0]!r}->{dept!r} is not a LIVE DEPT_DOMAIN_TAGS key "
                         f"(would fall to raw_dept_tags=[])")
    return probs


REAL_HINTS = dt._DEPT_HINT_KEYWORDS
probs = check_hint_targets_live(REAL_HINTS, LIVE_KEYS)
if not probs:
    ok(f"all {len(REAL_HINTS)} dept hints target a live canonical slug "
       f"({sorted({d for _, d in REAL_HINTS})})")
else:
    bad(f"{len(probs)} dead/non-canonical hint target(s)")
    for p in probs:
        print(f"          - {p}")

# The four historically-dead slugs must NOT be hint targets anymore.
DEAD = {"creative", "billing", "hr", "operations"}
still_dead = {d for _, d in REAL_HINTS} & DEAD
if not still_dead:
    ok("no dead slug (creative/billing/hr/operations) remains a hint target")
else:
    bad(f"dead slug(s) still targeted: {sorted(still_dead)}")

# NO-WEAKENING: a dead slug injected as a hint target MUST be caught.
probs_drift = check_hint_targets_live([(("x",), "creative")], LIVE_KEYS)
if probs_drift:
    ok("NO-WEAKENING: dead-slug hint target is caught")
else:
    bad("NO-WEAKENING: dead-slug hint target NOT caught — check too weak")


# ─────────────────────────── T2 — MECHANICAL SINGLE-SOURCE ─────────────────────
print("=" * 70)
print("T2  MECHANICAL GATE SINGLE-SOURCE (F3.7 sub-gap 3)")
print("=" * 70)

mg = _load_module(REPO / "shared-utils" / "mechanical-gate.py", "mech_gate_under_test")

# The decomposer must be using the SHARED base classifier + DELIVERY_VERBS.
base_true = ["restart the box", "reboot", "ping the host", "ls the dir",
             "chmod +x", "chown it", "check disk", "check memory"]
base_false_whole = ["write the sales emails", "plan the shipping route",
                    "review the controls", "build the tools page"]
delivery = ["send the sequence", "deploy the funnel", "publish to blog",
            "upload the assets", "blast the list"]

t2 = []
for t in base_true:
    if not mg.is_mechanical(t):
        t2.append(f"shared base should be mechanical: {t!r}")
    if not dt._is_mechanical(t):
        t2.append(f"decompose gate should be mechanical (base): {t!r}")
for t in base_false_whole:
    if mg.is_mechanical(t):
        t2.append(f"shared base should NOT be mechanical: {t!r}")
for t in delivery:
    # delivery verbs are mechanical for decompose (per-subtask) but NOT for the
    # whole-task base rule.
    if mg.is_mechanical(t):
        t2.append(f"delivery verb must NOT hit the base rule: {t!r}")
    if not dt._is_mechanical(t):
        t2.append(f"delivery verb should be mechanical for decompose: {t!r}")
if not t2:
    ok("decompose gate == shared base rule; DELIVERY_VERBS extend the per-subtask gate only")
else:
    bad(f"{len(t2)} mechanical-gate contract mismatch(es)")
    for p in t2:
        print(f"          - {p}")

# NO-WEAKENING: a non-command craft phrase must never be mechanical.
if not dt._is_mechanical("write the launch story for founders"):
    ok("NO-WEAKENING: craft phrase is not mechanical")
else:
    bad("NO-WEAKENING: craft phrase wrongly gated mechanical")


# ─────────────────────────── T3 — SLOT-DRIVEN MULTI-PERSONA ────────────────────
print("=" * 70)
print("T3  SLOT-DRIVEN MULTI-PERSONA (F3.9)")
print("=" * 70)

TASK = "Build a website for an audience of Black women founders"
SLOTS = [
    {"slot": "content", "task_category": "content-write", "domains": ["copywriting"],
     "audience_from": "task", "required": True},
    {"slot": "code", "task_category": "web-development", "domains": ["software-craft"],
     "required": True},
    {"slot": "image", "task_category": "design", "domains": ["visual-storytelling"],
     "required": False},
]
res = dt.combined_select(TASK, "web-development", use_llm=False, record=False, slots=SLOTS)

t3 = []
if not res.get("slot_driven"):
    t3.append("slot_driven flag not set")
if res.get("decomposition_method") != "sop-slots":
    t3.append(f"method should be 'sop-slots', got {res.get('decomposition_method')!r}")
if res.get("subtask_count") != 3:
    t3.append(f"expected 3 slot rows, got {res.get('subtask_count')}")
plan = res.get("plan", [])
cats = [p.get("task_category") for p in plan]
if cats != ["content-write", "web-development", "design"]:
    t3.append(f"forced task_category order wrong: {cats}")
slots_seen = [p.get("slot") for p in plan]
if slots_seen != ["content", "code", "image"]:
    t3.append(f"slot labels not carried: {slots_seen}")
# audience folded into the content slot's sub-task text (Layer-5 query input).
if plan and "Black women" not in (plan[0].get("subtask") or ""):
    t3.append("task audience not folded into the content slot sub-task text")
# distinct persona per slot (the multi-persona contract; hermetic stub is
# distinct-by-text, so distinct text -> distinct personas).
if res.get("distinct_persona_count") != 3:
    t3.append(f"expected 3 distinct personas, got {res.get('distinct_persona_count')}")
if not t3:
    ok("slots authoritative: 3 rows, forced categories, slot labels, audience "
       "in content query, 3 distinct personas")
else:
    bad(f"{len(t3)} slot-mode problem(s)")
    for p in t3:
        print(f"          - {p}")

# NO-WEAKENING: forcing a category must OVERRIDE text inference.
entry = dt.select_for_subtask("send the sequence", "marketing", {}, None,
                              variety=False, force_category="content-write")
if entry.get("task_category") == "content-write" and entry.get("persona_id"):
    ok("NO-WEAKENING: force_category overrides text inference AND suppresses the "
       "mechanical gate for an explicit slot")
else:
    bad(f"NO-WEAKENING: forced-category slot mis-handled: "
        f"cat={entry.get('task_category')} pid={entry.get('persona_id')}")


# ─────────────────────────── T4 — NO-NAKED FALLBACK ───────────────────────────
print("=" * 70)
print("T4  NO-NAKED FALLBACK (F3.9 -> F3.1)")
print("=" * 70)

# Required slot that comes back empty -> DEFAULT_PERSONA_FALLBACK attached.
empty_slots = [
    {"slot": "content", "task_category": "content-write",
     "subtask": _SENTINEL_EMPTY, "audience_from": "none", "required": True},
    {"slot": "image", "task_category": "design",
     "subtask": _SENTINEL_EMPTY, "audience_from": "none", "required": False},
]
res2 = dt.combined_select("x", "web-development", use_llm=False, record=False, slots=empty_slots)
p_req = res2["plan"][0]
p_opt = res2["plan"][1]
t4 = []
if p_req.get("persona_id") != dt.DEFAULT_PERSONA_FALLBACK:
    t4.append(f"required empty slot not backfilled: {p_req.get('persona_id')}")
if p_req.get("fallback") != "default_persona":
    t4.append("required-slot fallback not tagged 'default_persona'")
if p_opt.get("persona_id") is not None:
    t4.append(f"optional empty slot should stay empty, got {p_opt.get('persona_id')}")
if not t4:
    ok(f"required empty slot -> {dt.DEFAULT_PERSONA_FALLBACK} (never empty); "
       f"optional empty slot left truthfully empty")
else:
    bad(f"{len(t4)} required-slot fallback problem(s)")
    for p in t4:
        print(f"          - {p}")

# Mechanical sub-task keeps no_persona_required but carries a governance persona.
mech = dt.select_for_subtask("restart the server", "openclaw-maintenance", {}, None,
                             variety=False)
if (mech.get("no_persona_required") is True
        and mech.get("governance_persona_id") == dt.GOVERNANCE_PERSONA_FALLBACK):
    ok(f"mechanical sub-task: no_persona_required=True + governance_persona_id="
       f"{dt.GOVERNANCE_PERSONA_FALLBACK} (never naked)")
else:
    bad(f"mechanical sub-task governance wiring wrong: "
        f"npr={mech.get('no_persona_required')} gov={mech.get('governance_persona_id')}")

# NO-WEAKENING: a NON-required empty slot must NOT be silently backfilled.
if p_opt.get("persona_id") is None and not p_opt.get("fallback"):
    ok("NO-WEAKENING: optional empty slot is not force-filled")
else:
    bad("NO-WEAKENING: optional empty slot was wrongly backfilled")


# ────────────────────────────────── RESULTS ───────────────────────────────────
print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
