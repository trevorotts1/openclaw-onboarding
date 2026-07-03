#!/usr/bin/env python3
"""
test-dept-domain-mirror.py — persona↔matrix MIRROR-DRIFT lock (PRD §3).

Locks the invariant that persona-selector-v2.py `DEPT_DOMAIN_TAGS` (Stage-B dept
pre-qualifier) stays a faithful mirror of build-workforce.py `dept_to_domains`
(the persona-matrix / governing-personas pool author) and covers every live
department. This is the guard that stops the two sides silently re-diverging —
the failure mode that (a) left 18 canonical departments with raw_dept_tags=[]
before the 2026-07-03 coverage sync, and (b) left eight pre-canonical DEAD keys
(billing, operations, creative, hr, it, app-development, ceo, com) in the table.

WHY AST, NOT IMPORT:  the three inputs are extracted from the shipped source with
ast.literal_eval (never imported/executed), exactly like test-gate-scope-exemptions.py
extracts the real analyzer heredocs. So the test reads the SAME literals that run
in production and CANNOT drift from them — and it touches NO database, network, or
persona DB (a hard requirement: this suite must never read or write a live persona DB).

The looked-up key is ALWAYS a canonical slug: main() runs args.department through
canonical_dept_slug() before Stage B does DEPT_DOMAIN_TAGS.get(department, []), and
build-workforce resolves domains via dept_to_domains.get(dept_id, ["leadership"]) on
the same canonical dept_id. So both sides are modelled here as MAP.get(canonical_slug,
default) and compared per canonical slug.

ASSERTIONS (each also proven to FAIL on injected drift — the NO-WEAKENING block):
  T1 COVERAGE     every live _index.json department, canonicalised, has a non-empty
                  DEPT_DOMAIN_TAGS entry.
  T2 NO-DEAD-KEYS every DEPT_DOMAIN_TAGS key is idempotent-canonical AND is the
                  canonical slug of some live department (no pre-canonical dead keys).
  T3 VOCAB        every tag normalises into the known domain vocabulary
                  (build-workforce's own domain set + the video-production extension).
  T4 LOCKSTEP     build-workforce's two dept_to_domains copies are byte-identical.
  T5 NO-NARROWING for every live dept, the selector pool is a SUPERSET of the matrix
                  pool — it never silently drops a domain the matrix authored — except
                  for a small, explicit, documented set of legacy divergences.
  T6 OVERLAP      for every live dept, the selector pool and the matrix pool share at
                  least one domain (the same department can never map to a fully
                  disjoint pool on the two sides).

EXIT: 0 = every assertion (incl. every NO-WEAKENING case) passed; 1 otherwise.
Usage:
  python3 test-dept-domain-mirror.py [REPO_ROOT]
"""
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
SELECTOR = SCRIPTS / "persona-selector-v2.py"
BUILDER = SCRIPTS / "build-workforce.py"
INDEX = REPO / "23-ai-workforce-blueprint" / "templates" / "role-library" / "_index.json"

# canonical_dept_slug is the REAL identity contract used by the selector at runtime.
sys.path.insert(0, str(REPO / "shared-utils"))
from canonical_slug import canonical_dept_slug  # type: ignore  # noqa: E402

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


# ── the SAME normalisation the selector applies (_norm_tag) ────────────────────
def norm(s: str) -> str:
    return re.sub(r"[/ _]+", "-", s.lower()).strip("-")


def normset(tags) -> set:
    return {norm(t) for t in (tags or [])}


# ── extract the REAL literals (no import / no execution / no DB) ────────────────
def extract_assign(path: Path, name: str):
    """Return a list of every top-level-or-nested `name = <literal>` value in path."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    found.append(ast.literal_eval(node.value))
    return found


def build_effective(BUILD: dict, slug: str) -> set:
    """Domains build-workforce assigns to canonical `slug` — a direct canonical-key
    lookup with build-workforce's own ["leadership"] fallback (dept_to_domains.get(
    dept_id, ["leadership"]))."""
    return normset(BUILD.get(slug, ["leadership"]))


# ── documented, tolerated legacy divergences (T5) ──────────────────────────────
# Each entry: canonical dept -> the set of matrix domains the selector intentionally
# does NOT carry. These predate the mirror doctrine (the selector reshaped one tag
# toward the craft framing) OR are deliberate selector-side reshapes:
#   web-development     — reshaped to the sales-funnel surface (U1 widen, A7-locked):
#                         added sales/copywriting/operations, dropped productivity-systems.
#   legal               — selector frames legal as ops/governance/leadership, not comms.
#   general-task        — catch-all swapped operations -> strategy-innovation.
#   communications      — swapped leadership -> copywriting (comms is copy-heavy).
#   personal-assistant  — swapped leadership -> communication (PA is comms-heavy).
# The check is `(matrix - selector) <= allowed`, so if any of these is later RECONCILED
# (the missing domain re-added) the test still passes; but any NEW dropped domain — or a
# new dept narrowing the matrix — is caught. Reconciling the VALUES is a coordinated
# selector+build change, out of scope for the dead-key reconciliation this test ships with.
ALLOWED_LEGACY_MISSING = {
    "communications":     {"leadership"},
    "general-task":       {"operations"},
    "legal":              {"communication"},
    "personal-assistant": {"leadership"},
    "web-development":     {"productivity-systems"},
}

# The eight pre-canonical keys reconciled out of DEPT_DOMAIN_TAGS. Named so their
# reappearance produces a crisp, self-documenting regression signal in T2.
LEGACY_DEAD_KEYS = {"billing", "operations", "creative", "hr", "it",
                    "app-development", "ceo", "com"}


# ── the six pure checks (return a list of human-readable problems) ─────────────
def check_coverage(DEPT, live):
    probs = []
    for s in live:
        v = DEPT.get(s)
        if not v:
            probs.append(f"live dept {s!r} has no DEPT_DOMAIN_TAGS entry "
                         f"(falls to raw_dept_tags=[] — Stage B loses pre-qualification)")
    return probs


def check_no_dead_keys(DEPT, live):
    live_set = set(live)
    probs = []
    for k in DEPT:
        if canonical_dept_slug(k) != k:
            probs.append(f"key {k!r} is not idempotent-canonical "
                         f"(canonical_dept_slug -> {canonical_dept_slug(k)!r}); it is never looked up")
        elif k not in live_set:
            hint = " (pre-canonical dead key)" if k in LEGACY_DEAD_KEYS else ""
            probs.append(f"key {k!r} is not the canonical slug of any live _index.json dept{hint}")
    return probs


def check_vocab(DEPT, known):
    probs = []
    for k, tags in DEPT.items():
        for t in normset(tags):
            if t not in known:
                probs.append(f"dept {k!r} uses unknown domain tag {t!r} (not in matrix vocab)")
    return probs


def check_no_narrowing(DEPT, BUILD, live, allowed):
    probs = []
    for s in live:
        sel = normset(DEPT.get(s, []))
        matrix = build_effective(BUILD, s)
        missing = matrix - sel
        extra = missing - allowed.get(s, set())
        if extra:
            probs.append(f"dept {s!r} selector pool NARROWER than matrix: "
                         f"missing {sorted(extra)} (selector={sorted(sel)} matrix={sorted(matrix)})")
    return probs


def check_overlap(DEPT, BUILD, live):
    probs = []
    for s in live:
        sel = normset(DEPT.get(s, []))
        matrix = build_effective(BUILD, s)
        if sel and matrix and not (sel & matrix):
            probs.append(f"dept {s!r} selector pool is DISJOINT from matrix "
                         f"(selector={sorted(sel)} matrix={sorted(matrix)})")
    return probs


# ── load the real inputs ───────────────────────────────────────────────────────
print("=" * 70)
print("MIRROR-DRIFT LOCK — DEPT_DOMAIN_TAGS  vs  build-workforce dept_to_domains")
print("=" * 70)
print(f"selector: {SELECTOR}")
print(f"builder:  {BUILDER}")
print(f"index:    {INDEX}")

dept_literals = extract_assign(SELECTOR, "DEPT_DOMAIN_TAGS")
assert len(dept_literals) == 1, f"expected exactly one DEPT_DOMAIN_TAGS, found {len(dept_literals)}"
DEPT = dept_literals[0]

build_literals = extract_assign(BUILDER, "dept_to_domains")
assert build_literals, "no dept_to_domains found in build-workforce.py"
BUILD = build_literals[0]

idx = json.loads(INDEX.read_text(encoding="utf-8"))
raw_depts = list(idx["departments"].keys())
LIVE = sorted({canonical_dept_slug(d) for d in raw_depts})

# Known vocabulary = build-workforce's own domain set + the video-production extension
# (video/editing/montage/visual-storytelling — present in persona-categories.json for
# video personas and used by the selector's video dept + _CATEGORY_DOMAINS video-edit).
VIDEO_EXT = {"video", "editing", "montage", "visual-storytelling"}
KNOWN_DOMAINS = set()
for v in BUILD.values():
    KNOWN_DOMAINS |= normset(v)
KNOWN_DOMAINS |= VIDEO_EXT

print(f"\nlive raw depts: {len(raw_depts)}  ->  canonical slugs: {len(LIVE)}")
print(f"DEPT_DOMAIN_TAGS keys: {len(DEPT)}   build dept_to_domains keys: {len(BUILD)}")
print(f"known domain vocab ({len(KNOWN_DOMAINS)}): {sorted(KNOWN_DOMAINS)}")

# ── diagnostics: per-dept mirror relationship (informational only) ─────────────
rel = {"EQUAL": 0, "SUPERSET": 0, "DIVERGE": 0}
diverge = []
for s in LIVE:
    sel = normset(DEPT.get(s, []))
    matrix = build_effective(BUILD, s)
    if sel == matrix:
        rel["EQUAL"] += 1
    elif matrix <= sel:
        rel["SUPERSET"] += 1
    else:
        rel["DIVERGE"] += 1
        diverge.append(s)
print(f"\nmirror relationship: EQUAL={rel['EQUAL']} SUPERSET(widened)={rel['SUPERSET']} "
      f"DIVERGE(tolerated)={rel['DIVERGE']}")
if diverge:
    print(f"  tolerated divergences: {diverge}")

# ───────────────────────────── REAL DATA — must be clean ──────────────────────
print("-" * 70)
print("REAL DATA (must be clean)")
print("-" * 70)

for label, probs in [
    ("T1 COVERAGE", check_coverage(DEPT, LIVE)),
    ("T2 NO-DEAD-KEYS", check_no_dead_keys(DEPT, LIVE)),
    ("T3 VOCAB", check_vocab(DEPT, KNOWN_DOMAINS)),
    ("T5 NO-NARROWING", check_no_narrowing(DEPT, BUILD, LIVE, ALLOWED_LEGACY_MISSING)),
    ("T6 OVERLAP", check_overlap(DEPT, BUILD, LIVE)),
]:
    if not probs:
        ok(f"{label}: clean across all {len(LIVE)} live departments")
    else:
        bad(f"{label}: {len(probs)} problem(s)")
        for p in probs:
            print(f"          - {p}")

# T4 LOCKSTEP: build-workforce's two dept_to_domains copies must be identical.
if len(build_literals) >= 2 and all(b == build_literals[0] for b in build_literals):
    ok(f"T4 LOCKSTEP: all {len(build_literals)} build-workforce dept_to_domains copies identical")
elif len(build_literals) == 1:
    ok("T4 LOCKSTEP: single build-workforce dept_to_domains block (nothing to diverge)")
else:
    bad("T4 LOCKSTEP: build-workforce dept_to_domains copies DIVERGE from each other")

# ── NO-WEAKENING: prove each check FAILS on injected drift ─────────────────────
print("-" * 70)
print("NO-WEAKENING (each check must catch injected drift)")
print("-" * 70)


def expect_catches(label, probs):
    if probs:
        ok(f"{label} STILL catches injected drift ({len(probs)} problem(s))")
    else:
        bad(f"{label} did NOT catch injected drift — check is too weak")


# 1) drop a live dept -> COVERAGE must fire.
victim = "presentations" if "presentations" in DEPT else next(iter(DEPT))
mutated = {k: v for k, v in DEPT.items() if k != victim}
expect_catches("COVERAGE", check_coverage(mutated, LIVE))

# 2) reintroduce a pre-canonical dead key -> NO-DEAD-KEYS must fire.
mutated = dict(DEPT); mutated["ceo"] = ["leadership"]
expect_catches("NO-DEAD-KEYS", check_no_dead_keys(mutated, LIVE))

# 3) a typo'd / off-vocab tag -> VOCAB must fire.
mutated = dict(DEPT); mutated["marketing"] = list(DEPT["marketing"]) + ["markteing"]
expect_catches("VOCAB", check_vocab(mutated, KNOWN_DOMAINS))

# 4) silently narrow a dept below the matrix -> NO-NARROWING must fire.
#    engineering mirrors the matrix EXACTLY; drop one of its domains.
narrow = dict(DEPT); narrow["engineering"] = ["strategy-innovation"]  # was 3 domains
expect_catches("NO-NARROWING", check_no_narrowing(narrow, BUILD, LIVE, ALLOWED_LEGACY_MISSING))

# 5) make a dept disjoint from the matrix -> OVERLAP must fire.
disj = dict(DEPT); disj["engineering"] = ["marketing"]  # matrix has no marketing for engineering
expect_catches("OVERLAP", check_overlap(disj, BUILD, LIVE))

print("=" * 70)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 70)
sys.exit(0 if FAIL == 0 else 1)
