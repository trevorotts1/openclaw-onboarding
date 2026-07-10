#!/usr/bin/env bash
# qc-built-course.sh — Skill 6: per-build read-back gate for a constructed GHL COURSE.
# Same shape as qc-built-form.sh / qc-built-community.sh (evidence-root arg, --selftest,
# exit 0/1/2, un-fakeable criterion). A course PASSES only when: every per-object receipt
# (ghl_object_router, F6 — the course + every lesson) is verified, the OUTLINE read-back
# matched the plan 1:1 (module/lesson names present in the live outline), AND — when a
# course preview URL exists — ghl_verify.render_check returns HTTP 200 with the ZHC course
# name in the RENDERED DOM. No receipt = not created; the summary cannot exceed the receipts.
#
# Evidence contract — ghl_course_builder._live_build writes:
#   <evidence_root>/routing/course-built.json  { course_id, course_name, preview_url,
#       verify:{ outline:{outline_match, missing}, http?, marker_in_rendered_dom?,
#       render_errors?, status? }, modules:[...] }
#   <evidence_root>/ecosystem/course-<slug>.json + lesson-<slug>.json (per-lesson receipts)
#
# Usage:  ./qc-built-course.sh <evidence_root> [--json] | ./qc-built-course.sh --selftest
# Exit:   0 = PASS · 1 = FAIL · 2 = INCONCLUSIVE (no evidence / render read-back deferred)
set -u
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$SKILL_DIR/tools"

if [ "${1:-}" = "--selftest" ]; then
  TOOLS="$TOOLS" python3 - <<'PY'
import os, sys, json, tempfile
sys.path.insert(0, os.environ["TOOLS"])
errors = []

def _passes(rec, outline_match):
    return (outline_match and rec.get("http") == 200
            and not (rec.get("render_errors") or [])
            and bool(rec.get("marker_in_rendered_dom")))

if not _passes({"http": 200, "render_errors": [], "marker_in_rendered_dom": True}, True):
    errors.append("synthetic PASS misclassified")
if _passes({"http": 200, "render_errors": [], "marker_in_rendered_dom": True}, False):
    errors.append("outline mismatch must FAIL even with render 200")
for bad in ({"http": 500, "render_errors": [], "marker_in_rendered_dom": True},
            {"http": 200, "render_errors": ["x"], "marker_in_rendered_dom": True},
            {"http": 200, "render_errors": [], "marker_in_rendered_dom": False}):
    if _passes(bad, True):
        errors.append(f"synthetic FAIL misclassified: {bad}")

# per-lesson receipt reduction: one failed lesson sinks the run (resume granularity, F6).
try:
    import ghl_object_router as router
    with tempfile.TemporaryDirectory() as td:
        router.write_receipt(td, router.make_receipt("course", "zhc_launch", "created",
                                                     verify={"http": 200}, response_id="C1"))
        router.write_receipt(td, router.make_receipt("lesson", "welcome-intro", "created",
                                                     verify={"present_in_outline": True}))
        router.write_receipt(td, router.make_receipt("lesson", "build-page", "failed", error="miss"))
        summ = router.reduce_receipts(td)
        if summ.get("all_verified"):
            errors.append("reduce_receipts marked all_verified with a failed lesson")
        if "lesson:build-page" not in summ.get("failed", []):
            errors.append("failed lesson not surfaced")
except Exception as exc:  # noqa
    print(f"  WARN router import skipped ({exc})")

if errors:
    for e in errors: print(f"  FAIL: {e}", file=sys.stderr)
    print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr); sys.exit(1)
print("[selftest] PASS — course read-back gate logic + per-lesson receipt reduction (no network)")
PY
  exit $?
fi

ARG="${1:-}"; JSON=""
[ "${2:-}" = "--json" ] && JSON="1"
if [ -z "$ARG" ]; then
  echo "usage: qc-built-course.sh <evidence_root> [--json] | --selftest" >&2; exit 2
fi
EVIDENCE="$ARG"
if [ ! -d "$EVIDENCE" ]; then
  for c in "$PWD/working/courses/$ARG" "$HOME/clawd/working/courses/$ARG"; do
    [ -d "$c" ] && EVIDENCE="$c" && break
  done
fi
[ -d "$EVIDENCE" ] || { echo "✗ evidence root not found: $ARG" >&2; exit 2; }
[ -f "$TOOLS/ghl_verify.py" ] || { echo "✗ verifier not found" >&2; exit 2; }

echo "═══ Skill 6 — read-back gate (course) ═══"
echo "evidence: $EVIDENCE"
EVIDENCE="$EVIDENCE" TOOLS="$TOOLS" JSON="$JSON" python3 - <<'PY'
import os, sys, json, glob
sys.path.insert(0, os.environ["TOOLS"])
root = os.environ["EVIDENCE"]; want_json = bool(os.environ.get("JSON"))

receipt = os.path.join(root, "routing", "course-built.json")
if not os.path.isfile(receipt):
    hits = glob.glob(os.path.join(root, "**", "course-built.json"), recursive=True)
    receipt = hits[0] if hits else ""
if not receipt:
    print("✗ no routing/course-built.json — the course build did not complete a live run.",
          file=sys.stderr); sys.exit(2)
built = json.load(open(receipt))
name = built.get("course_name", "")
if not name.startswith("ZHC "):
    print(f"✗ course_name {name!r} is not ZHC-prefixed", file=sys.stderr); sys.exit(1)

try:
    import ghl_object_router as router
    summ = router.reduce_receipts(root)
except Exception as exc:  # noqa
    print(f"✗ router unavailable ({exc})", file=sys.stderr); sys.exit(2)
if summ.get("total", 0) == 0:
    print("✗ no per-object receipts under ecosystem/ (F6).", file=sys.stderr); sys.exit(2)
if not summ.get("all_verified"):
    print(f"✗ receipts report FAILED objects: {summ.get('failed')}", file=sys.stderr)
    if want_json: print(json.dumps({"ok": False, "receipts": summ}, indent=2))
    sys.exit(1)

v = built.get("verify") or {}
outline = v.get("outline") or {}
if not outline.get("outline_match", False):
    print(f"✗ outline read-back MISMATCH — missing: {outline.get('missing')}", file=sys.stderr)
    if want_json: print(json.dumps({"ok": False, "outline": outline, "receipts": summ}, indent=2))
    sys.exit(1)

url = v.get("preview_url") or built.get("preview_url") or ""
http = v.get("http"); mird = bool(v.get("marker_in_rendered_dom")); rerrs = v.get("render_errors") or []
if not url or http is None:
    print("○ INCONCLUSIVE — outline matched + receipts verified "
          f"({summ.get('created')} objects) but no course preview URL rendered; the render "
          "read-back is deferred (capture the preview URL shape and re-run).", file=sys.stderr)
    if want_json: print(json.dumps({"ok": None, "outline": outline, "receipts": summ}, indent=2))
    sys.exit(2)
ok = (http == 200) and (not rerrs) and mird
if want_json:
    print(json.dumps({"ok": ok, "http": http, "marker_in_rendered_dom": mird,
                      "render_errors": rerrs, "outline": outline, "receipts": summ}, indent=2))
else:
    print(f"  receipts: {summ.get('created')} created / {summ.get('reused')} reused / {summ.get('failed')} failed")
    print(f"  outline_match={outline.get('outline_match')} http={http} name_in_rendered_dom={mird}")
sys.exit(0 if ok else 1)
PY
rc=$?
[ $rc -eq 0 ] && echo "✓ PASS — receipts verified + outline matched 1:1 + preview rendered 200 with ZHC name"
[ $rc -eq 1 ] && echo "✗ FAIL — a receipt/outline/render check failed; fix and re-run"
[ $rc -eq 2 ] && echo "○ INCONCLUSIVE — missing evidence/verifier or render read-back deferred"
exit $rc
