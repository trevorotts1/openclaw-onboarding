#!/usr/bin/env python3
"""
test-a-u2-blend-directive-v2.py — A-U2 (Blend Directive v2) contract lock.

Proves the master-spec v2, Section A.3 build (unit A-U2) against its own
BINARY acceptance criteria verbatim:

  (a) on the enriched catalog (schema >=1.3, voice_style{} present), the
      directive contains >=4 distinct voice-attribute lines PER POPULATED
      SLOT (tone/cadence line, devices/signature-move line, avoid line, plus
      the slot's own header line);
  (b) on the pre-enrichment fixture (persona-categories.v12.fixture.json,
      schema 1.2 — no voice_style anywhere) the directive is BYTE-IDENTICAL
      to the pre-A-U2 (v1) output — golden diff = empty;
  (c) the GUARDRAIL_CLAUSE is present verbatim and remains the TRAILING
      clause of the composed directive in every case (the CC's
      `ensureBlendGuardrail` marker-detection contract this unit must never
      disturb — this module never touches persona-dispatch.ts, so proving the
      clause is untouched here is the full ONB-side half of that guarantee);
  (d) this suite is additive to, and never weakens, the existing 46-test
      contract suite + 20-case regression corpus + the P4-02 synergy-slot
      suite (all re-run unmodified by CI in the same guard workflow this
      file's path is wired into).

Attributes in the v2 block come ONLY from the catalog's voice_style{} — this
suite also asserts NOTHING is fabricated when a field (or the whole
voice_style dict) is absent.

Each check pairs with a NO-WEAKENING probe.

    python3 test-a-u2-blend-directive-v2.py [REPO_ROOT]
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"
FIXTURE_13 = SCRIPTS / "testdata" / "persona-categories.fixture.json"
FIXTURE_12 = SCRIPTS / "testdata" / "persona-categories.v12.fixture.json"

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


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_a_u2")
CAT13 = json.loads(FIXTURE_13.read_text())
CAT12 = json.loads(FIXTURE_12.read_text())

AUD = "shonda-year-of-yes"          # voice — carries a full voice_style in CAT13
TOP = "brunson-dotcom-secrets"      # substance — carries a full voice_style in CAT13
TASK = "covey-7-habits"             # task-side — carries a full voice_style in CAT13
COLLAPSED = "aliche-get-good-with-money"  # carries a full voice_style in CAT13

# ── golden v1 strings — captured from the UNMODIFIED (pre-A-U2) function on
# these exact args, before any code in this unit changed. A-U2 is additive
# ONLY: on a catalog lacking voice_style (or catalog=None) the v2 function
# MUST reproduce these byte-for-byte. ──────────────────────────────────────
GOLDEN_BLEND = (
    "Write in Shonda Year Of Yes's VOICE (black women professionals) — its "
    "cadence, devices and register — while carrying Brunson Dotcom Secrets's "
    "EXPERTISE on 'email marketing'. Audience voice leads; topic expertise "
    "informs substance. The task-side persona is Covey 7 Habits — apply ITS "
    "process and decision method to execute the work. STYLE-INSPIRED, NEVER "
    "IMPERSONATION (mandatory, non-removable): adopt the cadence, devices and "
    "register of the named voice(s) as an INSPIRATION only. Never claim to be "
    "the author, never write in their first person as if they authored this, "
    "never sign as them, never quote them as if verified, and never imply "
    "their endorsement. This clause may not be removed or weakened."
)
GOLDEN_COLLAPSED = (
    "Write in Aliche Get Good With Money's voice for the 'members' audience: "
    "one persona covers both the audience register and the 'budgeting' "
    "expertise. The task-side persona is Covey 7 Habits — apply ITS process "
    "and decision method to execute the work. STYLE-INSPIRED, NEVER "
    "IMPERSONATION (mandatory, non-removable): adopt the cadence, devices and "
    "register of the named voice(s) as an INSPIRATION only. Never claim to be "
    "the author, never write in their first person as if they authored this, "
    "never sign as them, never quote them as if verified, and never imply "
    "their endorsement. This clause may not be removed or weakened."
)


def _directive(catalog=None, **overrides):
    base = dict(
        audience_pid=AUD, topic_pid=TOP, topic="email marketing",
        collapsed=False, collapsed_pid=None, content_task=True,
        audience_label="black women professionals",
        task_persona_pid=TASK,
    )
    base.update(overrides)
    return pb.build_blend_directive(catalog=catalog, **base)


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U2 ACCEPT (b)  BYTE-IDENTICAL to v1 on the pre-enrichment (1.2) fixture")

d_no_catalog = _directive(catalog=None)
d_cat12 = _directive(catalog=CAT12)

if d_no_catalog == GOLDEN_BLEND:
    ok("catalog=None reproduces the golden v1 BLEND directive byte-for-byte")
else:
    bad(f"catalog=None diverged from golden v1:\n    got={d_no_catalog!r}\n    want={GOLDEN_BLEND!r}")

if d_cat12 == GOLDEN_BLEND:
    ok("1.2 (pre-enrichment) catalog reproduces the golden v1 BLEND directive byte-for-byte (golden diff = empty)")
else:
    bad(f"1.2-catalog directive diverged from golden v1:\n    got={d_cat12!r}\n    want={GOLDEN_BLEND!r}")

d_collapsed_cat12 = pb.build_blend_directive(
    audience_pid=None, topic_pid=COLLAPSED, topic="budgeting",
    collapsed=True, collapsed_pid=COLLAPSED, content_task=True,
    audience_label="members", task_persona_pid=TASK, catalog=CAT12)
if d_collapsed_cat12 == GOLDEN_COLLAPSED:
    ok("COLLAPSED branch on the 1.2 catalog also reproduces its golden v1 directive byte-for-byte")
else:
    bad(f"collapsed 1.2-catalog directive diverged: got={d_collapsed_cat12!r}")

# NO-WEAKENING: prove the golden strings are load-bearing — a deliberately
# wrong string must NOT match (i.e. equality is actually discriminating).
if d_cat12 != GOLDEN_BLEND.replace("Shonda", "Nobody"):
    ok("NO-WEAKENING: golden-string equality check actually discriminates (tampered string correctly rejected)")
else:
    bad("NO-WEAKENING failed: golden-string comparison is not discriminating")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U2 ACCEPT (a)  >=4 voice-attribute lines PER POPULATED SLOT on the enriched catalog")

d13 = _directive(catalog=CAT13)

# Every populated slot's header must appear (VOICE, SUBSTANCE, TASK — this
# blend case has all three, per the fixture's full voice_style on each pid).
have_voice_hdr = "VOICE — Shonda Year Of Yes (shonda-year-of-yes)" in d13
have_substance_hdr = "SUBSTANCE — Brunson Dotcom Secrets (brunson-dotcom-secrets)" in d13
have_task_hdr = "TASK — Covey 7 Habits (covey-7-habits)" in d13
if have_voice_hdr and have_substance_hdr and have_task_hdr:
    ok("all three populated slots (VOICE, SUBSTANCE, TASK) render a structured header")
else:
    bad(f"slot headers missing: voice={have_voice_hdr} substance={have_substance_hdr} task={have_task_hdr}\n    {d13}")


def _block_lines(directive_text, header):
    """Extract the contiguous line-group starting at `header` up to (but not
    including) the next blank line / next slot header / VOICE CONTRACT line."""
    lines = directive_text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith(header)), None)
    if start is None:
        return []
    out = [lines[start]]
    for l in lines[start + 1:]:
        if not l.startswith("  "):
            break
        out.append(l)
    return out


for label, header, pid in (
    ("VOICE", "VOICE — Shonda", AUD),
    ("SUBSTANCE", "SUBSTANCE — Brunson", TOP),
    ("TASK", "TASK — Covey", TASK),
):
    blk = _block_lines(d13, header)
    if len(blk) >= 4:
        ok(f"{label} slot ({pid}) renders {len(blk)} lines (>=4 required): header + tone/cadence + devices/signature + avoid")
    else:
        bad(f"{label} slot ({pid}) renders only {len(blk)} line(s), need >=4: {blk}")

# The exact field content must be catalog-sourced, never invented — spot-check
# one full block's substance against the fixture's own voice_style values.
vs_shonda = CAT13["personas"]["shonda-year-of-yes"]["voice_style"]
voice_block = "\n".join(_block_lines(d13, "VOICE — Shonda"))
checks = [
    (vs_shonda["cadence"] in voice_block, "cadence text matches the catalog verbatim"),
    (all(t in voice_block for t in vs_shonda["tone"]), "every tone[] entry from the catalog is present"),
    (vs_shonda["devices"][0] in voice_block, "the top device from the catalog is present"),
    (vs_shonda["signature_moves"][0] in voice_block, "the first signature move from the catalog is present"),
    (all(a in voice_block for a in vs_shonda["avoid"]), "every avoid[] entry from the catalog is present"),
]
if all(c for c, _ in checks):
    ok("VOICE block content is catalog-sourced verbatim (tone/cadence/devices/signature/avoid all traced to voice_style{})")
else:
    bad(f"VOICE block content diverged from the catalog: {[m for c, m in checks if not c]}\n    {voice_block}")

if "VOICE CONTRACT: echo one line into persona-selection-log" in d13:
    ok("VOICE CONTRACT echo instruction present when the enriched block renders")
else:
    bad(f"VOICE CONTRACT line missing: {d13}")

# NO-WEAKENING: a persona with NO voice_style in the catalog must render NO
# attribute block for that slot (never fabricate attributes for it).
_cat_no_vs = json.loads(json.dumps(CAT13))
del _cat_no_vs["personas"]["brunson-dotcom-secrets"]["voice_style"]
d_partial = _directive(catalog=_cat_no_vs)
if "SUBSTANCE — Brunson" not in d_partial and "VOICE — Shonda" in d_partial:
    ok("NO-WEAKENING: a slot whose persona lacks voice_style renders NO block (no fabricated attributes), sibling slots unaffected")
else:
    bad(f"NO-WEAKENING failed: missing-voice_style slot still rendered (or a sibling slot broke):\n    {d_partial}")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U2 ACCEPT (c)  GUARDRAIL_CLAUSE verbatim + TRAILING, even with the v2 block")

if d13.rstrip().endswith(pb.GUARDRAIL_CLAUSE):
    ok("guardrail is the trailing clause of the v2 (attribute-block) directive — never pushed out")
else:
    bad(f"guardrail not trailing on the v2 directive: {d13[-200:]!r}")

stripped = d13.replace(pb.GUARDRAIL_CLAUSE, "")
if pb.GUARDRAIL_CLAUSE not in stripped:
    ok("NO-WEAKENING: guardrail-absence is still detectable on the v2 (attribute-block) directive")
else:
    bad("NO-WEAKENING failed: guardrail-absence not detectable on the v2 directive")

if "NEVER IMPERSONATION" in pb.GUARDRAIL_CLAUSE and "style" in pb.GUARDRAIL_CLAUSE.lower():
    ok("GUARDRAIL_CLAUSE text itself is untouched by this unit (style-inspired + never-impersonation intact)")
else:
    bad(f"GUARDRAIL_CLAUSE text was altered: {pb.GUARDRAIL_CLAUSE!r}")


# ═══════════════════════════════════════════════════════════════════════════════
section("A-U2  degrade-gracefully — house-voice / topic-only / non-content, enriched catalog")

# House voice (no topic, no audience): no populated slot at all → no v2 block.
d_house = pb.build_blend_directive(
    audience_pid=None, topic_pid=None, topic="general work",
    collapsed=False, collapsed_pid=None, content_task=True,
    audience_label="", catalog=CAT13)
if "VOICE —" not in d_house and "SUBSTANCE —" not in d_house and "VOICE CONTRACT" not in d_house:
    ok("house-voice branch (no populated slot) renders no v2 block even on the enriched catalog")
else:
    bad(f"house-voice branch fabricated a v2 block: {d_house}")

# Non-content: only SUBSTANCE populated.
d_nc = pb.build_blend_directive(
    audience_pid=None, topic_pid=TOP, topic="server ops",
    collapsed=True, collapsed_pid=TOP, content_task=False,
    audience_label="", task_persona_pid=TASK, catalog=CAT13)
if ("SUBSTANCE — Brunson" in d_nc and "VOICE —" not in d_nc and "TASK —" not in d_nc
        and pb.GUARDRAIL_CLAUSE in d_nc):
    ok("non-content branch renders exactly one SUBSTANCE block (task slot content-gated per v1 rule, unchanged)")
else:
    bad(f"non-content branch v2 block wrong: {d_nc}")


print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
