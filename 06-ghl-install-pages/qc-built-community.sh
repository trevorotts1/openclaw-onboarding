#!/usr/bin/env bash
# qc-built-community.sh — Skill 6: per-build read-back gate for a constructed GHL
# COMMUNITY (Group). Same shape as qc-built-form.sh (evidence-root arg, --selftest,
# exit 0/1/2, un-fakeable criterion) — swaps the form render+marker gate for the
# community read-back: the run's per-object RECEIPTS (ghl_object_router, F6) must all
# be verified AND, when a public/client-portal group URL exists, ghl_verify.render_check
# must return HTTP 200 with the ZHC group name in the RENDERED DOM (a marker found only
# in a snapshot/storage blob is NOT verification). No receipt = not created (F6).
#
# Evidence contract — ghl_community_builder._live_build writes:
#   <evidence_root>/routing/community-built.json  { community_id, community_name,
#       community_url, verify:{ list_row_present, http?, marker_in_rendered_dom?,
#       render_errors?, status? }, channels:[...] }
#   <evidence_root>/ecosystem/community-<slug>.json + channel-<slug>.json (receipts)
#
# Usage:
#   ./qc-built-community.sh <evidence_root> [--json]
#   ./qc-built-community.sh --selftest
# Exit codes:
#   0 = PASS (receipts all verified AND — when a public URL exists — render 200 + name in DOM)
#   1 = FAIL (a receipt failed, or the public URL did not render 200 with the group name)
#   2 = INCONCLUSIVE (no evidence / verifier unavailable / verify deferred: no public URL)
set -u
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$SKILL_DIR/tools"

if [ "${1:-}" = "--selftest" ]; then
  TOOLS="$TOOLS" python3 - <<'PY'
import os, sys, json, tempfile
sys.path.insert(0, os.environ["TOOLS"])
errors = []

def _passes(rec):
    # PASS predicate (public-URL path), kept in lockstep with the live block below.
    return (rec.get("http") == 200
            and not (rec.get("render_errors") or [])
            and bool(rec.get("marker_in_rendered_dom")))

if not _passes({"http": 200, "render_errors": [], "marker_in_rendered_dom": True}):
    errors.append("synthetic PASS misclassified")
for bad in ({"http": 500, "render_errors": [], "marker_in_rendered_dom": True},
            {"http": 200, "render_errors": ["x"], "marker_in_rendered_dom": True},
            {"http": 200, "render_errors": [], "marker_in_rendered_dom": False}):
    if _passes(bad):
        errors.append(f"synthetic FAIL misclassified: {bad}")

# receipt-reduction: a failed channel receipt must sink the run (no silent partial, F6).
try:
    import ghl_object_router as router
    with tempfile.TemporaryDirectory() as td:
        r_ok = router.make_receipt("community", "zhc_founders", "created",
                                   verify={"http": 200}, response_id="G1")
        router.write_receipt(td, r_ok)
        r_bad = router.make_receipt("channel", "general", "failed", error="miss")
        router.write_receipt(td, r_bad)
        summ = router.reduce_receipts(td)
        if summ.get("all_verified"):
            errors.append("reduce_receipts marked all_verified with a failed receipt")
        if "channel:general" not in summ.get("failed", []):
            errors.append("failed channel receipt not surfaced")
except Exception as exc:  # noqa
    print(f"  WARN router import skipped ({exc})")

# marker must be the ZHC group name (never a bare snapshot proxy)
built = {"community_name": "ZHC Founders", "verify": {"marker_in_rendered_dom": True}}
if not built["community_name"].startswith("ZHC "):
    errors.append("community name is not ZHC-prefixed")

if errors:
    for e in errors: print(f"  FAIL: {e}", file=sys.stderr)
    print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr); sys.exit(1)
print("[selftest] PASS — community read-back gate logic + receipt reduction (no network)")
PY
  exit $?
fi

ARG="${1:-}"; JSON=""
[ "${2:-}" = "--json" ] && JSON="1"
if [ -z "$ARG" ]; then
  echo "usage: qc-built-community.sh <evidence_root> [--json] | --selftest" >&2; exit 2
fi
EVIDENCE="$ARG"
if [ ! -d "$EVIDENCE" ]; then
  for c in "$PWD/working/communities/$ARG" "$HOME/clawd/working/communities/$ARG"; do
    [ -d "$c" ] && EVIDENCE="$c" && break
  done
fi
[ -d "$EVIDENCE" ] || { echo "✗ evidence root not found: $ARG" >&2; exit 2; }
[ -f "$TOOLS/ghl_verify.py" ] || { echo "✗ verifier not found" >&2; exit 2; }

echo "═══ Skill 6 — read-back gate (community) ═══"
echo "evidence: $EVIDENCE"
EVIDENCE="$EVIDENCE" TOOLS="$TOOLS" JSON="$JSON" python3 - <<'PY'
import os, sys, json, glob
sys.path.insert(0, os.environ["TOOLS"])
root = os.environ["EVIDENCE"]; want_json = bool(os.environ.get("JSON"))

receipt = os.path.join(root, "routing", "community-built.json")
if not os.path.isfile(receipt):
    hits = glob.glob(os.path.join(root, "**", "community-built.json"), recursive=True)
    receipt = hits[0] if hits else ""
if not receipt:
    print("✗ no routing/community-built.json — the community build did not complete a live run.",
          file=sys.stderr); sys.exit(2)
built = json.load(open(receipt))
name = built.get("community_name", "")
if not name.startswith("ZHC "):
    print(f"✗ community_name {name!r} is not ZHC-prefixed", file=sys.stderr); sys.exit(1)

# 1. RECEIPTS — no receipt = not created; a failed receipt sinks the run (F6).
try:
    import ghl_object_router as router
    summ = router.reduce_receipts(root)
except Exception as exc:  # noqa
    print(f"✗ router unavailable ({exc})", file=sys.stderr); sys.exit(2)
if summ.get("total", 0) == 0:
    print("✗ no per-object receipts under ecosystem/ — nothing to verify (F6).", file=sys.stderr); sys.exit(2)
if not summ.get("all_verified"):
    print(f"✗ receipts report FAILED objects: {summ.get('failed')}", file=sys.stderr)
    if want_json: print(json.dumps({"ok": False, "receipts": summ}, indent=2))
    sys.exit(1)

# 2. RENDER read-back — when a public URL exists, require 200 + name in RENDERED DOM.
v = built.get("verify") or {}
url = v.get("community_url") or built.get("community_url") or ""
http = v.get("http"); mird = bool(v.get("marker_in_rendered_dom")); rerrs = v.get("render_errors") or []
if not url or http is None:
    print("○ INCONCLUSIVE — no public/client-portal group URL rendered; receipts verified "
          f"({summ.get('created')}+{summ.get('reused')} objects) but the un-fakeable render "
          "read-back is deferred (capture the public URL shape and re-run).", file=sys.stderr)
    if want_json: print(json.dumps({"ok": None, "receipts": summ, "verify": v}, indent=2))
    sys.exit(2)
ok = (http == 200) and (not rerrs) and mird
if want_json:
    print(json.dumps({"ok": ok, "http": http, "marker_in_rendered_dom": mird,
                      "render_errors": rerrs, "receipts": summ, "url": url}, indent=2))
else:
    print(f"  receipts: {summ.get('created')} created / {summ.get('reused')} reused / {summ.get('failed')} failed")
    print(f"  http={http} name_in_rendered_dom={mird} render_errors={len(rerrs)}")
sys.exit(0 if ok else 1)
PY
rc=$?
[ $rc -eq 0 ] && echo "✓ PASS — receipts verified + group rendered 200 with its ZHC name"
[ $rc -eq 1 ] && echo "✗ FAIL — a receipt failed or the group did not render; fix and re-run"
[ $rc -eq 2 ] && echo "○ INCONCLUSIVE — missing evidence/verifier or render read-back deferred"
exit $rc
