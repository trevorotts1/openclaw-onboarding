#!/usr/bin/env python3
"""
test-persona-match-regression-corpus.py — P4-01 step 2: "strengthen matching
quality measurably: add a persona-match regression corpus (20 labeled
request->expected-persona cases, drafted ... from real board history) as a
test the matcher must score >=90% on". Grown 20 -> 40 cases by A-U13 (Skill 6
v2 master-spec section A, ONB, P2, dep A-U3): +10 emotional-register-intent
cases (C21-C30) and +10 conversion-style-intent cases (C31-C40), each tagged
`intent_tag` in the corpus JSON and each individually verified against the
live matcher before being locked in (see corpus `_doc` for the full A-U13
rationale). The original 20 cases (C01-C20) are untouched.

WHAT THIS PROVES
-----------------
Loads testdata/persona-match-regression-corpus.json (40 cases) and the REAL,
shipped 99-persona catalog at
22-book-to-persona-coaching-leadership-system/persona-categories.json (never
a synthetic fixture — this measures actual production match quality, not a
hermetic stand-in). For each case it calls the matcher's pure tag-ranking
functions directly:
  dimension == "topic"    -> persona_blend.match_topic_persona(catalog, request)
  dimension == "audience" -> persona_blend.match_audience_persona(catalog, request)
No DB, no network, no LLM call, no selector/decompose mocking needed — both
functions are pure reads over the catalog dict. Asserts the winning
persona_id equals `expected_persona_id` for >=90% (18/20) of cases; a lower
score is a HARD FAIL (drift lock).

FAIL-FIRST / NO-WEAKENING (this is not a test that merely happens to pass):
this suite was built by discovering a REAL defect in _tag_hit's substring-
containment nudge. The function's own docstring promises "substring
containment for long tokens (>=5 chars)" but, pre-fix, only the QUERY-side
token was length-gated -- a SHORT tag-side token (e.g. 'a'/'b' from the tag
'a-b-testing', or 'hr' from 'hr-leaders') is a trivial substring of almost
any long query word, so those tags silently won matches against
semantically-unrelated requests. Measured: 84 of 99 personas' audience/topic
tags in the live catalog carry a <=2-char hyphen-split token, so this was not
a corner case. Against the PRE-FIX matcher this corpus scored 15/20 = 75%
(below gate); the fix (persona_blend.py::_tag_hit, gating `len(xs) >= 5`
too) raised it to 18/20 = 90% (at gate) with zero regressions in the existing
46-test persona-blend suite. `test_no_weakening_pre_fix_tag_hit_fails_gate`
below RE-INTRODUCES the pre-fix behavior in-process (a local monkeypatched
copy of the buggy function, never touching the shipped file) and proves the
corpus's own scoring would have caught it -- the drift-lock actually locks.

Usage: python3 test-persona-match-regression-corpus.py [REPO_ROOT]
Exit: 0 = pass rate >= gate (and the NO-WEAKENING probe demonstrates the gate
bites); 1 otherwise.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
CORPUS_PATH = SCRIPTS / "testdata" / "persona-match-regression-corpus.json"
LIVE_CATALOG_PATH = (REPO / "22-book-to-persona-coaching-leadership-system"
                      / "persona-categories.json")

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


def section(title):
    print("=" * 72)
    print(title)
    print("=" * 72)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_regression_corpus_under_test")

for f in (CORPUS_PATH, LIVE_CATALOG_PATH):
    if not f.exists():
        print(f"FATAL: missing {f}")
        sys.exit(2)

CORPUS = json.loads(CORPUS_PATH.read_text())
CASES = CORPUS["cases"]
GATE = CORPUS.get("gate_pass_rate", 0.90)
CATALOG = json.loads(LIVE_CATALOG_PATH.read_text())


def score_corpus(catalog, match_topic_fn, match_audience_fn):
    """Run every corpus case against the given matcher functions. Returns
    (hits, total, per_case_results[])."""
    hits = 0
    results = []
    for case in CASES:
        dim = case["dimension"]
        expect = case["expected_persona_id"]
        if dim == "topic":
            r = match_topic_fn(catalog, case["request"])
        elif dim == "audience":
            r = match_audience_fn(catalog, case["request"])
        else:
            raise ValueError(f"unknown dimension {dim!r} in case {case['id']}")
        got = r["persona_id"] if r else None
        hit = got == expect
        if hit:
            hits += 1
        results.append((case["id"], dim, expect, got, hit))
    return hits, len(CASES), results


# ── 1. Corpus shape sanity ──────────────────────────────────────────────────
section("SHAPE  corpus has >=40 cases (A-U13 floor), each with the required fields")
required = {"id", "dimension", "request", "expected_persona_id"}
MIN_CORPUS = 40
if len(CASES) >= MIN_CORPUS:
    ok(f"corpus has >= {MIN_CORPUS} cases (got {len(CASES)})")
else:
    bad(f"corpus expected >= {MIN_CORPUS} cases (A-U13 floor), got {len(CASES)}")
missing_fields = [c["id"] for c in CASES if not required.issubset(c.keys())] \
    if all("id" in c for c in CASES) else ["<case missing id>"]
if not missing_fields:
    ok("every case carries id/dimension/request/expected_persona_id")
else:
    bad(f"cases missing required fields: {missing_fields}")
ids = [c["id"] for c in CASES]
if len(set(ids)) == len(ids):
    ok("every case id is unique")
else:
    bad(f"duplicate case ids found: {ids}")

# A-U13 accept (d): >=5 cases must assert emotional-register intent and >=5
# must assert conversion-style intent, each TAGGED in the corpus JSON via
# `intent_tag` (not inferred) — this is the binding acceptance criterion, so
# it is asserted here as a hard gate, not left to eyeballing the JSON.
section("A-U13  >=5 emotional-register-intent + >=5 conversion-style-intent "
        "cases, tagged via intent_tag")
MIN_INTENT = 5
emo_count = sum(1 for c in CASES if c.get("intent_tag") == "emotional-register")
conv_count = sum(1 for c in CASES if c.get("intent_tag") == "conversion-style")
if emo_count >= MIN_INTENT:
    ok(f"{emo_count} case(s) tagged intent_tag='emotional-register' "
       f"(>= {MIN_INTENT} required)")
else:
    bad(f"only {emo_count} case(s) tagged intent_tag='emotional-register' "
        f"(need >= {MIN_INTENT})")
if conv_count >= MIN_INTENT:
    ok(f"{conv_count} case(s) tagged intent_tag='conversion-style' "
       f"(>= {MIN_INTENT} required)")
else:
    bad(f"only {conv_count} case(s) tagged intent_tag='conversion-style' "
        f"(need >= {MIN_INTENT})")
# every expected_persona_id must be a REAL persona in the live catalog (never
# a fabricated id — the corpus must be grounded in the shipped catalog).
live_personas = pb._persona_meta(CATALOG)
unknown = [c["id"] for c in CASES if c["expected_persona_id"] not in live_personas]
if not unknown:
    ok(f"every expected_persona_id exists in the live 99-persona catalog "
       f"({len(live_personas)} personas checked)")
else:
    bad(f"cases reference personas NOT in the live catalog: {unknown}")

# ── 2. THE GATE — matcher must score >=90% on the corpus, against the REAL
#    shipped catalog ─────────────────────────────────────────────────────────
section(f"GATE  matcher scores >= {GATE:.0%} on the {len(CASES)}-case corpus "
        f"(REAL shipped 99-persona catalog)")
hits, total, results = score_corpus(CATALOG, pb.match_topic_persona,
                                     pb.match_audience_persona)
rate = hits / total if total else 0.0
for cid, dim, expect, got, hit in results:
    mark = "PASS" if hit else "FAIL"
    print(f"    [{mark}] {cid} ({dim}): expect={expect!r} got={got!r}")
if rate >= GATE:
    ok(f"pass rate {hits}/{total} = {rate:.1%} >= gate {GATE:.0%}")
else:
    bad(f"pass rate {hits}/{total} = {rate:.1%} BELOW gate {GATE:.0%} — "
        f"matcher quality regressed")

# ── 3. NO-WEAKENING — the PRE-FIX _tag_hit bug would have failed this gate ──
section("NO-WEAKENING  a monkeypatched pre-fix _tag_hit drops the corpus below gate")


def _pre_fix_stem(tok: str) -> str:
    if len(tok) > 5 and tok.endswith("ing"):
        return tok[:-3]
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


def _pre_fix_tag_hit(query_tokens, tags):
    """Byte-for-byte reproduction of _tag_hit as it shipped BEFORE the P4-01
    fix — only the query-side stem was length-gated (>=5), not the tag-side
    stem. Reproduced locally (never imported from a git-historical copy) so
    this test has no dependency on repo history and stays hermetic."""
    if not query_tokens or not tags:
        return 0, [], []
    qstems = {}
    for q in query_tokens:
        qstems.setdefault(_pre_fix_stem(q), q)
    matched_orig = set()
    matched_tags = []
    for t in tags:
        toks = [x for x in re.split(r"[^a-z0-9]+", str(t).lower()) if x]
        hit = False
        for x in toks:
            xs = _pre_fix_stem(x)
            if xs in qstems:
                matched_orig.add(qstems[xs])
                hit = True
                continue
            for st, orig in qstems.items():
                if len(st) >= 5 and (st in xs or xs in st):  # BUG: no len(xs) gate
                    matched_orig.add(orig)
                    hit = True
        if hit:
            matched_tags.append(t)
    return len(matched_orig), sorted(set(matched_tags)), sorted(matched_orig)


def _pre_fix_match_topic_persona(catalog, task_text, topic_hint="", semantic_pick=""):
    """Reproduction of match_topic_persona wired to the buggy _pre_fix_tag_hit,
    so the NO-WEAKENING probe exercises the exact same ranking logic the real
    function uses -- only the one-line bug differs."""
    personas = pb._persona_meta(catalog)
    if not personas:
        return None
    q = pb._tokens(task_text) | pb._tokens(topic_hint)
    ranked = []
    any_topics = False
    for pid, pinfo in personas.items():
        if not isinstance(pinfo, dict) or pinfo.get("fallback"):
            continue
        ua = pb._usable_as(pinfo)
        if "topic" not in ua:
            continue
        tops = pinfo.get("topics") or []
        if tops:
            any_topics = True
        hits_, mtags, mtoks = _pre_fix_tag_hit(q, tops)
        nudge = 1 if (semantic_pick and pid == semantic_pick) else 0
        score = hits_ + 0.25 * nudge
        if hits_ > 0 or nudge:
            ranked.append((score, hits_, len(mtags), pid, mtags, mtoks))
    if not any_topics and not ranked:
        return None
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r[0], -r[1], -r[2], r[3]))
    score, hits_, _n, pid, mtags, mtoks = ranked[0]
    if hits_ == 0:
        return None
    return {"persona_id": pid, "why": "pre-fix reproduction", "matched_tags": mtags,
            "matched_tokens": mtoks, "score": score}


def _pre_fix_match_audience_persona(catalog, audience_label):
    personas = pb._persona_meta(catalog)
    if not audience_label or not personas:
        return None
    q = pb._tokens(audience_label)
    ranked = []
    for pid, pinfo in personas.items():
        if not isinstance(pinfo, dict) or pinfo.get("fallback"):
            continue
        if "audience" not in pb._usable_as(pinfo):
            continue
        auds = pinfo.get("audiences") or []
        if not auds:
            continue
        hits_, mtags, mtoks = _pre_fix_tag_hit(q, auds)
        if hits_ > 0:
            ranked.append((hits_, len(mtags), pid, mtags, mtoks))
    if not ranked:
        return None
    ranked.sort(key=lambda r: (-r[0], -r[1], r[2]))
    hits_, _n, pid, mtags, mtoks = ranked[0]
    return {"persona_id": pid, "why": "pre-fix reproduction", "matched_tags": mtags,
            "matched_tokens": mtoks, "score": hits_}


pre_hits, pre_total, pre_results = score_corpus(
    CATALOG, _pre_fix_match_topic_persona, _pre_fix_match_audience_persona)
pre_rate = pre_hits / pre_total if pre_total else 0.0
print(f"    pre-fix reproduction score: {pre_hits}/{pre_total} = {pre_rate:.1%}")
if pre_rate < GATE:
    ok(f"pre-fix behavior scores {pre_rate:.1%} < gate {GATE:.0%} — "
       f"the corpus WOULD HAVE FAILED this gate before the fix (drift-lock has teeth)")
else:
    bad(f"pre-fix behavior scores {pre_rate:.1%} >= gate {GATE:.0%} — "
        f"the corpus does NOT discriminate the known-bad state (drift-lock is toothless)")
if pre_rate < rate:
    ok(f"post-fix rate ({rate:.1%}) strictly improves on pre-fix rate ({pre_rate:.1%})")
else:
    bad(f"post-fix rate ({rate:.1%}) did not improve on pre-fix rate ({pre_rate:.1%})")

print(f"\n{'=' * 72}")
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'=' * 72}")
sys.exit(1 if FAIL else 0)
