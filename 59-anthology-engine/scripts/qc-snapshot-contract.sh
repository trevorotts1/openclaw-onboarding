#!/usr/bin/env bash
# qc-snapshot-contract.sh — CI DRIFT GATE for the Anthology Convert and Flow snapshot.
# ----------------------------------------------------------------------------
# Machine-proves that the snapshot FIXTURE (config/anthology-snapshot-contract.json)
# still byte-agrees with the engine's SINGLE SOURCE OF TRUTH. This is the Skill-59
# analogue of Skill 38's qc-23-key-bodies.sh: it FAILS CI when the engine's expected
# pipeline name, stage names, field keys/types, cover-choice options, intake route,
# or credential labels DRIFT from the fixture — so a stale snapshot can never ship
# and provision-anthology-client.sh can never import a snapshot the engine no longer
# matches.
#
# CROSS-CHECKS (contract  <->  source of truth):
#   config/field-map.json (THE source of truth for pipeline + fields)
#     * pipeline.standard_pipeline_name  == contract.pipeline.name
#     * pipeline.standard_stages          == contract.pipeline.stages (position + name, in order)
#     * provisioning.fields               == contract.custom_fields.fields
#                                            (intended_key, create_name, data_type, order, count)
#     * provisioning.total_keys == 28     == contract.custom_fields.total_keys
#     * the ONE SINGLE_OPTIONS cover choice + its 4 options, in order, byte-equal
#       cover_style_fields.choice_options
#   config/engine-config.template.json
#     * intake.route_path                 == contract.intake.route_path
#     * intake.route_secret_label         == contract.intake.route_secret_label
#                                            == contract.credential_labels.intake_hook_secret_label
#     * registry_defaults.caf_pit_label / caf_location_label == contract.credential_labels.*
#
# INTERNAL CONTRACT INVARIANTS (guard the fixture's own shape):
#   * 27 LARGE_TEXT free-text keys + exactly 1 SINGLE_OPTIONS (the cover choice)
#   * cover choice options == ["Signature","Bold Editorial","Fine Art","Pure Type"], in order
#   * 8 release-tag slugs; the 3 LIVE slugs are avatar/tone/outline
#   * 4 REQUIRED location custom values (anthology_webhook_url, anthology_hook_secret,
#     producer, producer_email); anthology_hook_secret is flagged secret + never_a_real_token
#   * forms: 1 required universal-author-intake + 3 contract-bound (s3/s4/s5); universal
#     hidden fields == contact_id, anthology_id, stage
#   * rejected_mechanisms records the agency->subaccount API auto-push as REJECTED
#     (a standing guard so nobody quietly builds the cross-agency push this topology forbids)
#
# This IS a product-enforcement tool: the assertions ARE the mechanism. It reads only
# committed template files (no secret, no network) and prints structure only.
#
# EXIT CODES (SPEC 3.4 guard family): 0 = fixture agrees with the source of truth;
#   1 = DRIFT (one or more assertions failed); 2 = a required file is missing (the
#   gate went blind — treated as failure).
#
# Usage:
#   bash scripts/qc-snapshot-contract.sh            # human output
#   bash scripts/qc-snapshot-contract.sh --json     # machine output
#   bash scripts/qc-snapshot-contract.sh --skill-dir /path/to/59-anthology-engine
# ----------------------------------------------------------------------------
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --json) JSON_MODE=1; shift ;;
    -h|--help) sed -n '1,55p' "$0"; exit 0 ;;
    *) echo "qc-snapshot-contract: unknown arg: $1" >&2; exit 2 ;;
  esac
done

export SKILL_DIR JSON_MODE

python3 - <<'PYEOF'
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(os.environ["SKILL_DIR"])
JSON_MODE = os.environ.get("JSON_MODE", "0") == "1"

CONTRACT = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP = SKILL_DIR / "config" / "field-map.json"
ENGINE_CFG = SKILL_DIR / "config" / "engine-config.template.json"

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
        print(json.dumps({"scan": "snapshot-contract", "verdict": "BLIND", "reason": msg}, indent=2))
    else:
        print("=== qc-snapshot-contract: Anthology snapshot drift gate ===")
        print("RESULT: BLIND — %s. The gate cannot verify the snapshot; treating as FAIL." % msg)
    sys.exit(2)


for f in (CONTRACT, FIELD_MAP, ENGINE_CFG):
    if not f.is_file():
        _blind("required file missing: %s" % f.name)
    try:
        json.loads(f.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _blind("%s is not valid JSON: %s" % (f.name, exc))

contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
fm = json.loads(FIELD_MAP.read_text(encoding="utf-8"))
cfg = json.loads(ENGINE_CFG.read_text(encoding="utf-8"))

drift = []


def need(cond, msg):
    if not cond:
        drift.append(msg)


# ---- pipeline (name + stages, in order) vs field-map ------------------------
c_pipe = contract.get("pipeline", {}) or {}
fm_pipe = fm.get("pipeline", {}) or {}
need(c_pipe.get("name") == fm_pipe.get("standard_pipeline_name"),
     "pipeline name: contract %r != field-map %r"
     % (c_pipe.get("name"), fm_pipe.get("standard_pipeline_name")))

c_stages = [(s.get("position"), s.get("name")) for s in (c_pipe.get("stages") or [])]
fm_stages = [(s.get("position"), s.get("name")) for s in (fm_pipe.get("standard_stages") or [])]
need(c_stages == fm_stages,
     "pipeline stages drift: contract %s != field-map %s" % (c_stages, fm_stages))
need(len(c_stages) == 9, "expected 9 pipeline stages, contract has %d" % len(c_stages))

# ---- custom fields vs field-map (exact, ordered) ----------------------------
c_fields = (contract.get("custom_fields", {}) or {}).get("fields", []) or []
fm_fields = (fm.get("provisioning", {}) or {}).get("fields", []) or []

need((contract.get("custom_fields", {}) or {}).get("total_keys") == EXPECTED_TOTAL,
     "contract custom_fields.total_keys != %d" % EXPECTED_TOTAL)
need(len(c_fields) == EXPECTED_TOTAL, "contract lists %d custom fields, expected %d" % (len(c_fields), EXPECTED_TOTAL))
need(len(fm_fields) == EXPECTED_TOTAL, "field-map lists %d provisioning fields, expected %d" % (len(fm_fields), EXPECTED_TOTAL))

# Compare the ordered (intended_key, create_name, data_type) tuples.
c_tup = [(f.get("intended_key"), f.get("create_name"), f.get("data_type")) for f in c_fields]
fm_tup = [(f.get("intended_key"), f.get("create_name"), f.get("data_type")) for f in fm_fields]
if c_tup != fm_tup:
    # find the first divergence for a precise message
    first = next((i for i in range(max(len(c_tup), len(fm_tup)))
                  if (c_tup[i:i + 1] or [None])[0] != (fm_tup[i:i + 1] or [None])[0]), None)
    detail = ""
    if first is not None:
        detail = " (first divergence at row %d: contract %s != field-map %s)" % (
            first, (c_tup[first:first + 1] or ["<none>"])[0], (fm_tup[first:first + 1] or ["<none>"])[0])
    drift.append("custom_fields drift from field-map provisioning.fields%s" % detail)

# ---- data-type census: 27 LARGE_TEXT + exactly 1 SINGLE_OPTIONS -------------
large = [f for f in c_fields if f.get("data_type") == "LARGE_TEXT"]
single = [f for f in c_fields if f.get("data_type") == "SINGLE_OPTIONS"]
other = [f for f in c_fields if f.get("data_type") not in ("LARGE_TEXT", "SINGLE_OPTIONS")]
need(len(large) == 27, "expected 27 LARGE_TEXT fields, contract has %d" % len(large))
need(len(single) == 1, "expected exactly 1 SINGLE_OPTIONS field, contract has %d" % len(single))
need(not other, "unexpected data_type(s) in contract: %s" % [(f.get('intended_key'), f.get('data_type')) for f in other])
need((contract.get("custom_fields", {}) or {}).get("free_text_data_type") == "LARGE_TEXT",
     "contract free_text_data_type must be LARGE_TEXT")

# the SINGLE_OPTIONS field IS the cover choice, and its options match — in order —
# both the field-map inventory row AND cover_style_fields.choice_options.
if single:
    cover = single[0]
    need(cover.get("intended_key") == "contact.anthology_cover_choice",
         "the SINGLE_OPTIONS field must be contact.anthology_cover_choice, got %r" % cover.get("intended_key"))
    need(cover.get("options") == EXPECTED_COVER_OPTIONS,
         "cover-choice options drift: contract %s != %s" % (cover.get("options"), EXPECTED_COVER_OPTIONS))
    fm_choice_opts = (fm.get("cover_style_fields", {}) or {}).get("choice_options")
    need(cover.get("options") == fm_choice_opts,
         "cover-choice options: contract %s != field-map cover_style_fields.choice_options %s"
         % (cover.get("options"), fm_choice_opts))
    fm_cover_row = next((f for f in fm_fields if f.get("intended_key") == "contact.anthology_cover_choice"), None)
    need(fm_cover_row is not None and fm_cover_row.get("options") == EXPECTED_COVER_OPTIONS,
         "field-map cover-choice inventory row options drift: %s"
         % (fm_cover_row.get("options") if fm_cover_row else "<row missing>"))

# ---- intake route + credential labels vs engine-config ----------------------
c_intake = contract.get("intake", {}) or {}
cfg_intake = cfg.get("intake", {}) or {}
need(c_intake.get("route_path") == cfg_intake.get("route_path"),
     "intake route_path: contract %r != engine-config %r"
     % (c_intake.get("route_path"), cfg_intake.get("route_path")))
need(c_intake.get("route_secret_label") == cfg_intake.get("route_secret_label"),
     "intake route_secret_label: contract %r != engine-config %r"
     % (c_intake.get("route_secret_label"), cfg_intake.get("route_secret_label")))

c_creds = contract.get("credential_labels", {}) or {}
need(c_creds.get("intake_hook_secret_label") == cfg_intake.get("route_secret_label"),
     "credential_labels.intake_hook_secret_label != engine-config intake.route_secret_label")
cfg_reg = cfg.get("registry_defaults", {}) or {}
need(c_creds.get("caf_pit_label") == cfg_reg.get("caf_pit_label"),
     "credential_labels.caf_pit_label: contract %r != engine-config %r"
     % (c_creds.get("caf_pit_label"), cfg_reg.get("caf_pit_label")))
need(c_creds.get("caf_location_label") == cfg_reg.get("caf_location_label"),
     "credential_labels.caf_location_label: contract %r != engine-config %r"
     % (c_creds.get("caf_location_label"), cfg_reg.get("caf_location_label")))

# ---- release-tag slugs ------------------------------------------------------
c_tags = contract.get("tags", {}) or {}
slugs = [t.get("slug") for t in (c_tags.get("slugs") or [])]
need(slugs == EXPECTED_TAG_SLUGS, "tag slugs drift: contract %s != %s" % (slugs, EXPECTED_TAG_SLUGS))
live = {t.get("slug") for t in (c_tags.get("slugs") or []) if t.get("status") == "LIVE"}
need(live == LIVE_SLUGS, "LIVE tag slugs drift: contract %s != %s" % (sorted(live), sorted(LIVE_SLUGS)))

# ---- location custom values (the REPLACE-ME fill contract) ------------------
lcv = contract.get("location_custom_values", {}) or {}
need(lcv.get("engine_reads_custom_values") is False,
     "location_custom_values.engine_reads_custom_values must be false (the engine reads none)")
cv_keys = [c.get("key") for c in (lcv.get("required") or [])]
need(cv_keys == REQUIRED_CV_KEYS, "required custom-value keys drift: %s != %s" % (cv_keys, REQUIRED_CV_KEYS))
secret_cv = next((c for c in (lcv.get("required") or []) if c.get("key") == "anthology_hook_secret"), None)
need(secret_cv is not None and secret_cv.get("secret") is True and secret_cv.get("never_a_real_token") is True,
     "anthology_hook_secret custom value must be flagged secret + never_a_real_token")

# ---- forms ------------------------------------------------------------------
forms = contract.get("forms", {}) or {}
need(forms.get("universal_hidden_fields") == UNIVERSAL_HIDDEN,
     "forms.universal_hidden_fields drift: %s != %s" % (forms.get("universal_hidden_fields"), UNIVERSAL_HIDDEN))
req_forms = forms.get("required") or []
need(len(req_forms) == 1 and req_forms[0].get("role") == "universal-author-intake",
     "expected exactly 1 required form (universal-author-intake)")
bound = [f.get("role") for f in (forms.get("contract_bound_per_anthology") or [])]
need(bound == ["title-subtitle-selection", "outline-approval", "chapter-approve-or-rewrite"],
     "contract-bound gate forms drift: %s" % bound)

# ---- rejected mechanism standing guard --------------------------------------
rejected = contract.get("rejected_mechanisms") or []
push = next((r for r in rejected if "subaccount" in str(r.get("mechanism", "")).lower()
             and "push" in str(r.get("mechanism", "")).lower()), None)
need(push is not None and str(push.get("decision", "")).upper().startswith("REJECTED"),
     "the agency->subaccount API auto-push must remain recorded as REJECTED in rejected_mechanisms")

# ---- source-template pointer present ----------------------------------------
tmpl = (contract.get("source_template_location", {}) or {}).get("template_location_id")
need(bool(tmpl), "source_template_location.template_location_id is missing")

# ---- verdict ----------------------------------------------------------------
if JSON_MODE:
    print(json.dumps({
        "scan": "snapshot-contract",
        "contract": str(CONTRACT.relative_to(SKILL_DIR)),
        "checks": {"pipeline": True, "fields": True, "labels": True, "tags": True,
                   "custom_values": True, "forms": True, "rejected_push": True},
        "drift": drift,
        "verdict": "PASS" if not drift else "FAIL",
    }, indent=2))
else:
    print("=== qc-snapshot-contract: Anthology snapshot drift gate ===")
    print("skill_dir : %s" % SKILL_DIR)
    print("contract  : %s" % CONTRACT.relative_to(SKILL_DIR))
    print("source    : config/field-map.json + config/engine-config.template.json")
    print("")
    if not drift:
        print("RESULT: PASS — the snapshot fixture agrees with the engine's source of truth")
        print("  pipeline 'Anthology Engine' + 9 stages, 28 fields (27 LARGE_TEXT + 1 SINGLE_OPTIONS),")
        print("  cover options + intake route + credential labels + 8 tags + 4 custom values + forms,")
        print("  and the agency->subaccount push remains REJECTED.")
    else:
        print("RESULT: FAIL — %d drift issue(s) between the snapshot fixture and the source of truth:" % len(drift))
        for d in drift:
            print("  - %s" % d)

sys.exit(1 if drift else 0)
PYEOF
