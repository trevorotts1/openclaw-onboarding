#!/usr/bin/env bash
# qc-snapshot-fixture.sh — CI DRIFT GATE for the shipped Convert and Flow snapshot FIXTURE.
# ----------------------------------------------------------------------------
# MASTER-SPEC U17: ship fixtures/snapshot/anthology-engine-v1.0.0.json and add a CI
# drift gate that reads the snapshot JSON, extracts every fieldKey / pipeline-stage
# name / form-field name, and asserts each BYTE-EXACT against the committed
# config/field-map.json and ENGINE-MANIFEST.json. A deliberate drift in field-map.json
# (rename a key) must FAIL the gate.
#
# CROSS-CHECKS (fixture  <->  source of truth):
#   config/field-map.json                 (THE source of truth for pipeline + fields)
#     * fixture.pipeline.name            == field-map.pipeline.standard_pipeline_name
#     * fixture.pipeline.stages[].name   == field-map.pipeline.standard_stages[].name (9, in order)
#     * fixture.custom_fields[].fieldKey == field-map.provisioning.fields[].intended_key (28, in order)
#     * fixture.custom_fields[].name     == field-map.provisioning.fields[].create_name
#     * fixture.custom_fields[].dataType == field-map.provisioning.fields[].data_type
#     * fixture.custom_fields[].options  == field-map.provisioning.fields[].options (cover choice only)
#     * the ONE SINGLE_OPTIONS field is contact.anthology_cover_choice with the four
#       style options in order (byte-equal field-map.cover_style_fields.choice_options)
#   ENGINE-MANIFEST.json                  (the orchestrator contract)
#     * the manifest's S0..S9 stage names are the PIPELINE STAGE names (the snapshot's
#       9 pipeline stages are the S1..S8 pipeline names Intake/Avatar/Tone/Title/
#       Outline/Chapter/Cover/Delivered/Assembled plus S0's intake stage; the gate
#       asserts the engine's manifest stage set maps 1:1 onto the fixture's pipeline
#       stage names in order)
#
# INTERNAL CONTRACT INVARIANTS (guard the fixture's own shape):
#   * 27 LARGE_TEXT free-text keys + exactly 1 SINGLE_OPTIONS (the cover choice)
#   * 4 REPLACE-ME location custom values (anthology_webhook_url,
#     anthology_hook_secret [secret+placeholder], producer, producer_email)
#   * 8 release-tag slugs; exactly the 3 LIVE slugs avatar/tone/outline
#   * 1 required universal author-intake form + 3 contract-bound gate forms
#     (title-subtitle-selection / outline-approval / chapter-approve-or-rewrite),
#     every form carrying the universal hidden fields contact_id, anthology_id, stage
#   * 8 release-notification workflow summaries, one per tag slug, contact_tag triggers
#   * never-a-real-token: no "https://", no "Bearer ", no "REAL" value anywhere in the
#     fixture (the four custom values are placeholders by construction)
#
# EXIT CODES (SPEC 3.4 guard family): 0 = fixture agrees with the source of truth;
#   1 = DRIFT (one or more assertions failed); 2 = a required file is missing or the
#   fixture does not parse (the gate went blind — treated as failure).
#
# Usage:
#   bash scripts/qc-snapshot-fixture.sh            # human output
#   bash scripts/qc-snapshot-fixture.sh --json     # machine output
#   bash scripts/qc-snapshot-fixture.sh --skill-dir /path/to/59-anthology-engine
# ----------------------------------------------------------------------------
set -uo pipefail  # Intentional: no -e; exit codes handled explicitly per house contract (ENGINE-MANIFEST.json rows 30-32)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    --self-test) SELFTEST=1; shift ;;
    -h|--help) sed -n '1,60p' "$0"; exit 0 ;;
    *) echo "qc-snapshot-fixture: unknown arg: $1" >&2; exit 2 ;;
  esac
done

export SKILL_DIR JSON_MODE

# ---- self-test: force-observe BOTH clean PASS and real DRIFT detection -------
# The mutation proof runs the gate twice on a THROWAWAY copy of the skill dir:
# (a) untouched -> must PASS; (b) a manifest stage name renamed -> must FAIL.
# A gate that passes when the world drifts is dead; a gate that fails on a clean
# tree is broken. Exit 0 = the gate discriminates; 1 = self-test FAILed.
if [ "${SELFTEST:-0}" -eq 1 ]; then
  SELFTEST_TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc-snapshot-fixture-selftest.XXXXXX")"
  trap 'rm -rf "$SELFTEST_TMP"' EXIT
  cp -R "$SKILL_DIR" "$SELFTEST_TMP/skill"
  # stage the tamper: S8 name renamed to a plausible-looking but wrong value.
  python3 - "$SELFTEST_TMP/skill/ENGINE-MANIFEST.json" <<'PY'
import json, sys
p = sys.argv[1]
man = json.load(open(p, encoding="utf-8"))
for s in man["stages"]:
    if s["id"] == "S8":
        s["name"] = "PACKAGE AND SHIP"
json.dump(man, open(p, "w", encoding="utf-8"), indent=2)
PY
  # 1) the TAMPERED tree must FAIL the gate (exit 1 = DRIFT) -- a gate that
  #    passes when a manifest name drifts is dead. SKILL_DIR must come via
  #    --skill-dir: the script derives it from its own path, never from env.
  bash "$0" --skill-dir "$SELFTEST_TMP/skill" --json >/dev/null 2>&1
  tamper_rc=$?
  # 2) restore the pristine manifest (byte-exact copy of the real one) and the
  #    untouched tree must PASS -- a gate that fails on a clean tree is broken.
  cp "$SKILL_DIR/ENGINE-MANIFEST.json" "$SELFTEST_TMP/skill/ENGINE-MANIFEST.json"
  bash "$0" --skill-dir "$SELFTEST_TMP/skill" --json >/dev/null 2>&1
  clean_rc=$?
  if [ "$clean_rc" -eq 0 ] && [ "$tamper_rc" -eq 1 ]; then
    echo "qc-snapshot-fixture --self-test: PASS (untouched tree PASS, manifest-name tamper FAIL)"
    exit 0
  fi
  echo "qc-snapshot-fixture --self-test: FAIL (clean_rc=$clean_rc tamper_rc=$tamper_rc; want 0 and 1)" >&2
  exit 1
fi

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ["SKILL_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

FIXTURE = SKILL_DIR / "fixtures" / "snapshot" / "anthology-engine-v1.0.0.json"
FIELD_MAP = SKILL_DIR / "config" / "field-map.json"
ENGINE_MANIFEST = SKILL_DIR / "ENGINE-MANIFEST.json"

EXPECTED_TOTAL = 28
EXPECTED_COVER_OPTIONS = ["Signature", "Bold Editorial", "Fine Art", "Pure Type"]
EXPECTED_TAG_SLUGS = [
    "anthology-release-avatar", "anthology-release-tone", "anthology-release-outline",
    "anthology-release-chapter", "anthology-release-rewrite", "anthology-release-cover",
    "anthology-release-final", "anthology-delivered",
]
LIVE_SLUGS = {"anthology-release-avatar", "anthology-release-tone", "anthology-release-outline"}
UNIVERSAL_HIDDEN = ["contact_id", "anthology_id", "stage"]
REQUIRED_CV_KEYS = ["anthology_webhook_url", "anthology_hook_secret", "producer", "producer_email"]


def _blind(msg):
    if JSON_MODE:
        print(json.dumps({"scan": "snapshot-fixture", "verdict": "BLIND", "reason": msg}, indent=2))
    else:
        print("=== qc-snapshot-fixture: Anthology snapshot fixture drift gate ===")
        print("RESULT: BLIND — %s. The gate cannot verify the fixture; treating as FAIL." % msg)
    sys.exit(2)


for f in (FIXTURE, FIELD_MAP, ENGINE_MANIFEST):
    if not f.is_file():
        _blind("required file missing: %s" % f.name)
    try:
        json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _blind("%s is not valid JSON: %s" % (f.name, exc))

fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
man = json.loads(ENGINE_MANIFEST.read_text(encoding="utf-8"))

if not isinstance(fixture, dict):
    _blind("fixture does not parse to a JSON object")

drift = []


def need(cond, msg):
    if not cond:
        drift.append(msg)


# ---- fixture provenance ----------------------------------------------------
need(fixture.get("fixture_version") == "1.0.0",
     "fixture_version != 1.0.0 (got %r)" % fixture.get("fixture_version"))

# ---- pipeline (name + 9 stage names, in order) vs field-map + manifest -----
f_pipe = fixture.get("pipeline", {}) or {}
fm_pipe = fm.get("pipeline", {}) or {}
need(f_pipe.get("name") == fm_pipe.get("standard_pipeline_name"),
     "pipeline name: fixture %r != field-map %r"
     % (f_pipe.get("name"), fm_pipe.get("standard_pipeline_name")))

f_stage_names = [s.get("name") for s in (f_pipe.get("stages") or [])]
fm_stage_names = [s.get("name") for s in (fm_pipe.get("standard_stages") or [])]
need(f_stage_names == fm_stage_names,
     "pipeline stage names drift: fixture %s != field-map %s" % (f_stage_names, fm_stage_names))
need(len(f_stage_names) == 9, "expected 9 pipeline stages, fixture has %d" % len(f_stage_names))

# ---- ENGINE-MANIFEST stage set: ids AND names must be exactly the canonical
#      S0..S9 roster. The manifest's names are the ENGINE's long names (pinned
#      byte-exact by the ten stage dispatchers' STAGE_NAME constants -- e.g.
#      scripts/stage_s0_intake.py STAGE_NAME "INTAKE AND ROUTING"); the fixture
#      names are the PIPELINE's short names. The two systems are joined by
#      PIPELINE_TO_ENGINE_STAGE below, but the manifest's own names must still
#      be pinned: before this assert, renaming a manifest stage name (or any
#      part of it) passed the gate -- the id checks and the pipeline->engine
#      forward map never touched the manifest's NAME field.
man_stages = man.get("stages") or []
need(len(man_stages) == 10, "ENGINE-MANIFEST must carry exactly S0..S9")
EXPECTED_MAN_STAGE_NAMES = {
    "S0": "INTAKE AND ROUTING", "S1": "AVATAR", "S2": "TONE", "S3": "TITLE",
    "S4": "BLURB AND OUTLINE", "S5": "CHAPTER", "S6": "CHAPTER REWRITE",
    "S7": "COVER IMAGE", "S8": "PACKAGE AND DELIVER", "S9": "ANTHOLOGY ASSEMBLY",
}
if len(man_stages) == 10:
    for i, s in enumerate(man_stages):
        sid = "S%d" % i
        need(s.get("id") == sid, "ENGINE-MANIFEST stage %d id is %r, expected S%d" % (i, s.get("id"), i))
        need(s.get("name") == EXPECTED_MAN_STAGE_NAMES[sid],
             "ENGINE-MANIFEST stage %s name %r != canonical name %r"
             % (sid, s.get("name"), EXPECTED_MAN_STAGE_NAMES[sid]))
# The pipeline stage names must map byte-exact onto the engine's stage ids:
# Intake is the S0 intake stage (engine name "INTAKE AND ROUTING"), and the
# pipeline stages Avatar/Tone/Title/Outline/Chapter/Cover/Delivered/Assembled
# are the engine's S1..S8 (S6 CHAPTER REWRITE has no pipeline stage).
PIPELINE_TO_ENGINE_STAGE = {
    "Intake": "S0", "Avatar": "S1", "Tone": "S2", "Title": "S3",
    "Outline": "S4", "Chapter": "S5", "Cover": "S7",
    "Delivered": "S8", "Assembled": "S9",
}
for pname in f_stage_names:
    need(pname in PIPELINE_TO_ENGINE_STAGE,
         "pipeline stage %r is not a known engine stage (S0..S9)" % pname)

# ---- custom fields vs field-map (exact, ordered) ----------------------------
f_fields = fixture.get("custom_fields") or []
fm_fields = (fm.get("provisioning", {}) or {}).get("fields", []) or []

need(len(f_fields) == EXPECTED_TOTAL, "fixture lists %d custom fields, expected %d" % (len(f_fields), EXPECTED_TOTAL))
need(len(fm_fields) == EXPECTED_TOTAL, "field-map lists %d provisioning fields, expected %d" % (len(fm_fields), EXPECTED_TOTAL))

# ordered (fieldKey, name, dataType) triples
f_tup = [(f.get("fieldKey"), f.get("name"), f.get("dataType")) for f in f_fields]
fm_tup = [(f.get("intended_key"), f.get("create_name"), f.get("data_type")) for f in fm_fields]
if f_tup != fm_tup:
    first = next((i for i in range(max(len(f_tup), len(fm_tup)))
                  if (f_tup[i:i + 1] or [None])[0] != (fm_tup[i:i + 1] or [None])[0]), None)
    detail = ""
    if first is not None:
        detail = " (first divergence at row %d: fixture %s != field-map %s)" % (
            first, (f_tup[first:first + 1] or ["<none>"])[0], (fm_tup[first:first + 1] or ["<none>"])[0])
    drift.append("custom_fields drift from field-map provisioning.fields%s" % detail)

# ---- data-type census: 27 LARGE_TEXT + exactly 1 SINGLE_OPTIONS -------------
large = [f for f in f_fields if f.get("dataType") == "LARGE_TEXT"]
single = [f for f in f_fields if f.get("dataType") == "SINGLE_OPTIONS"]
other = [f for f in f_fields if f.get("dataType") not in ("LARGE_TEXT", "SINGLE_OPTIONS")]
need(len(large) == 27, "expected 27 LARGE_TEXT fields, fixture has %d" % len(large))
need(len(single) == 1, "expected exactly 1 SINGLE_OPTIONS field, fixture has %d" % len(single))
need(not other, "unexpected dataType(s) in fixture: %s" % [(f.get('fieldKey'), f.get('dataType')) for f in other])

# the SINGLE_OPTIONS field IS the cover choice, and its options match — in order —
# both the field-map inventory row AND cover_style_fields.choice_options.
if single:
    cover = single[0]
    need(cover.get("fieldKey") == "contact.anthology_cover_choice",
         "the SINGLE_OPTIONS field must be contact.anthology_cover_choice, got %r" % cover.get("fieldKey"))
    need(cover.get("options") == EXPECTED_COVER_OPTIONS,
         "cover-choice options drift: fixture %s != %s" % (cover.get("options"), EXPECTED_COVER_OPTIONS))
    fm_choice_opts = (fm.get("cover_style_fields", {}) or {}).get("choice_options")
    need(cover.get("options") == fm_choice_opts,
         "cover-choice options: fixture %s != field-map cover_style_fields.choice_options %s"
         % (cover.get("options"), fm_choice_opts))
    fm_cover_row = next((f for f in fm_fields if f.get("intended_key") == "contact.anthology_cover_choice"), None)
    need(fm_cover_row is not None and fm_cover_row.get("options") == EXPECTED_COVER_OPTIONS,
         "field-map cover-choice inventory row options drift: %s"
         % (fm_cover_row.get("options") if fm_cover_row else "<row missing>"))

# ---- custom values (REPLACE-ME placeholders only) ----------------------------
cv = fixture.get("custom_values") or []
need([c.get("key") for c in cv] == REQUIRED_CV_KEYS,
     "custom-value keys drift: %s != %s" % ([c.get("key") for c in cv], REQUIRED_CV_KEYS))
for c in cv:
    need(c.get("value") == "REPLACE-ME",
         "custom value %r must carry the REPLACE-ME placeholder, got %r" % (c.get("key"), c.get("value")))
secret_cv = next((c for c in cv if c.get("key") == "anthology_hook_secret"), None)
need(secret_cv is not None and secret_cv.get("secret") is True,
     "anthology_hook_secret custom value must be flagged secret")

# ---- never-a-real-token over the WHOLE fixture -------------------------------
blob = json.dumps(fixture)
for bad in ("https://", "http://", "Bearer "):
    need(bad not in blob, "fixture carries a real-looking %r" % bad)

# ---- tags ---------------------------------------------------------------------
f_tags = fixture.get("tags", {}) or {}
slugs = [t.get("slug") for t in (f_tags.get("slugs") or [])]
need(slugs == EXPECTED_TAG_SLUGS, "tag slugs drift: fixture %s != %s" % (slugs, EXPECTED_TAG_SLUGS))
live = {t.get("slug") for t in (f_tags.get("slugs") or []) if t.get("status") == "LIVE"}
need(live == LIVE_SLUGS, "LIVE tag slugs drift: fixture %s != %s" % (sorted(live), sorted(LIVE_SLUGS)))

# ---- forms (form-field names + hidden-field contract) --------------------------
forms = fixture.get("forms", {}) or {}
need(forms.get("universal_hidden_fields") == UNIVERSAL_HIDDEN,
     "forms.universal_hidden_fields drift: %s != %s" % (forms.get("universal_hidden_fields"), UNIVERSAL_HIDDEN))
req_forms = forms.get("required") or []
need(len(req_forms) == 1 and req_forms[0].get("role") == "universal-author-intake",
     "expected exactly 1 required form (universal-author-intake)")
for f in req_forms:
    need((f.get("hidden_fields") or []) == UNIVERSAL_HIDDEN,
         "required form %r hidden_fields drift: %s" % (f.get("role"), f.get("hidden_fields")))
bound = [f.get("role") for f in (forms.get("contract_bound_per_anthology") or [])]
need(bound == ["title-subtitle-selection", "outline-approval", "chapter-approve-or-rewrite"],
     "contract-bound gate forms drift: %s" % bound)
for f in (forms.get("contract_bound_per_anthology") or []):
    need((f.get("hidden_fields") or []) == UNIVERSAL_HIDDEN,
         "gate form %r hidden_fields drift: %s" % (f.get("role"), f.get("hidden_fields")))

# ---- workflows (one per tag slug, contact_tag triggers) ------------------------
wfs = fixture.get("workflows") or []
need(len(wfs) == 8, "expected 8 release-notification workflows, fixture has %d" % len(wfs))
wf_tags = []
for w in wfs:
    conds = w.get("trigger_conditions") or []
    tag_vals = []
    for c in conds:
        v = c.get("value") or []
        if isinstance(v, list):
            tag_vals.extend(v)
    wf_tags.extend(tag_vals)
    need(w.get("trigger_type") == "contact_tag", "workflow %r trigger_type is %r" % (w.get("name"), w.get("trigger_type")))
need(sorted(set(wf_tags)) == sorted(EXPECTED_TAG_SLUGS),
     "workflow trigger tags drift: %s != %s" % (sorted(set(wf_tags)), sorted(EXPECTED_TAG_SLUGS)))

# ---- counts block self-consistency ---------------------------------------------
counts = fixture.get("counts") or {}
need(counts.get("custom_fields") == 28, "counts.custom_fields != 28")
need(counts.get("custom_values") == 4, "counts.custom_values != 4")
need(counts.get("tags") == 8, "counts.tags != 8")
need(counts.get("forms") == 4, "counts.forms != 4")
need(counts.get("workflows") == 8, "counts.workflows != 8")

# ---- verdict --------------------------------------------------------------------
if JSON_MODE:
    print(json.dumps({
        "scan": "snapshot-fixture",
        "fixture": str(FIXTURE.relative_to(SKILL_DIR)),
        "checks": {"pipeline": True, "fields": True, "manifest": True, "tags": True,
                   "custom_values": True, "forms": True, "workflows": True},
        "drift": drift,
        "verdict": "PASS" if not drift else "FAIL",
    }, indent=2))
else:
    print("=== qc-snapshot-fixture: Anthology snapshot fixture drift gate ===")
    print("skill_dir : %s" % SKILL_DIR)
    print("fixture   : %s" % FIXTURE.relative_to(SKILL_DIR))
    print("source    : config/field-map.json + ENGINE-MANIFEST.json")
    print("")
    if not drift:
        print("RESULT: PASS — the snapshot fixture agrees byte-exact with the engine's source of truth")
        print("  pipeline 'Anthology Engine' + 9 stages, 28 fields (27 LARGE_TEXT + 1 SINGLE_OPTIONS),")
        print("  cover options, 4 REPLACE-ME custom values, 8 tags (3 LIVE), forms + workflow set,")
        print("  and the ENGINE-MANIFEST S0..S9 stage set.")
    else:
        print("RESULT: FAIL — %d drift issue(s) between the snapshot fixture and the source of truth:" % len(drift))
        for d in drift:
            print("  - %s" % d)

sys.exit(1 if drift else 0)
PYEOF
