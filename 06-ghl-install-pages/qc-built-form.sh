#!/usr/bin/env bash
# qc-built-form.sh — Skill 6: per-build render gate for a constructed native GHL FORM.
#
# DISTINCT from qc-ghl-install-pages.sh (install-level QC for the skill itself) and
# from qc-built-funnel.sh (the library-aware FAB-QC overlay for funnels). A form has
# no 12-section SACRED copy rubric, so its build gate is the MECHANICAL render floor —
# the same un-fakeable criterion the whole skill trusts: ghl_verify render_check
# returning HTTP 200 AND the zhc_ marker present in the RENDERED DOM (a marker found
# only in Firebase / raw autosave is NOT verification). This mirrors qc-built-funnel.sh
# in shape (evidence-root arg, --json passthrough, banner, exit codes) but swaps the
# funnel FAB scorer for the direct render+marker gate via tools/ghl_verify.verify_page.
#
# Evidence contract — the form builder (ghl_form_builder.build_form, live path) writes
#   <evidence_root>/routing/form-built.json
# with at least:
#   { "form_id", "form_name", "form_url",
#     "verify": { "preview_url": "<rendered form/host page URL>",
#                 "marker": "zhc_<key>  (a zhc_ token guaranteed in the rendered DOM)",
#                 "page_id": "<GHL page id or form id>" } }
# The gate loads that, calls verify_page(page, live=True), and PASSES only when
# http==200 AND render_errors==[] AND the marker is in the rendered DOM.
#
# Usage:
#   ./qc-built-form.sh <evidence_root> [--json]
#   ./qc-built-form.sh <slug>            # resolves working/forms/<slug>/ if it exists
#   ./qc-built-form.sh --selftest        # no-network structural self-check (gate logic)
#
# Exit codes:
#   0  = render_check PASS (HTTP 200 + zhc_ marker in RENDERED DOM + no render errors)
#   1  = render_check FAIL (build is NOT done) — fix the form/embed and re-run
#   2  = evidence root / form-built.json not found, or verifier unavailable
set -u

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
TOOLS="$SKILL_DIR/tools"

# ─────────────────────────────────────────────────────────────────────────────
# --selftest: prove the gate LOGIC classifies a synthetic pass/fail correctly with
# NO network and NO skill deps beyond stdlib. This is the shell's self-test rung.
# ─────────────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "--selftest" ]; then
  TOOLS="$TOOLS" python3 - <<'PY'
import os, sys, json, tempfile
sys.path.insert(0, os.environ["TOOLS"])
errors = []

# The gate's pass predicate, replicated exactly (http==200 AND no render_errors AND
# marker_in_rendered_dom). Keep in lockstep with the live-gate block below.
def _passes(rec):
    return (rec.get("http") == 200
            and not (rec.get("render_errors") or [])
            and bool(rec.get("marker_in_rendered_dom")))

# synthetic PASS
if not _passes({"http": 200, "render_errors": [], "marker_in_rendered_dom": True}):
    errors.append("synthetic PASS record misclassified as fail")
# synthetic FAILs
if _passes({"http": 500, "render_errors": [], "marker_in_rendered_dom": True}):
    errors.append("http 500 must fail")
if _passes({"http": 200, "render_errors": ["boom"], "marker_in_rendered_dom": True}):
    errors.append("render_errors must fail")
if _passes({"http": 200, "render_errors": [], "marker_in_rendered_dom": False}):
    errors.append("marker-not-in-DOM must fail (storage marker is NOT verification)")

# evidence-shape check: a well-formed form-built.json exposes verify.preview_url +
# verify.marker (+ page_id). Build one in a temp dir and re-read it.
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "routing"); os.makedirs(p)
    fb = {"form_id": "SELFTEST", "form_name": "ZHC Selftest Form",
          "verify": {"preview_url": "https://example.test/widget/form/SELFTEST",
                     "marker": "zhc_selftest_key", "page_id": "SELFTEST"}}
    with open(os.path.join(p, "form-built.json"), "w") as fh:
        json.dump(fb, fh)
    with open(os.path.join(p, "form-built.json")) as fh:
        rr = json.load(fh)
    v = rr.get("verify", {})
    if not (v.get("preview_url") and v.get("marker")):
        errors.append("form-built.json verify block missing preview_url/marker")
    if not v.get("marker", "").startswith("zhc_"):
        errors.append("marker is not a zhc_ token")

# ghl_verify must expose verify_page (the live gate) — import is soft here.
try:
    import ghl_verify  # noqa: F401
    if not hasattr(ghl_verify, "verify_page"):
        errors.append("ghl_verify.verify_page missing")
except Exception as exc:  # tooling absent in a bare checkout — WARN, do not fail selftest
    print(f"  WARN ghl_verify import skipped ({exc})")

if errors:
    for e in errors:
        print(f"  FAIL: {e}", file=sys.stderr)
    print(f"[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
    sys.exit(1)
print("[selftest] PASS — render gate logic + evidence contract verified (no network)")
PY
  exit $?
fi

ARG="${1:-}"
JSON=""
[ "${2:-}" = "--json" ] && JSON="1"

if [ -z "$ARG" ]; then
  echo "usage: qc-built-form.sh <evidence_root|slug> [--json]   |   qc-built-form.sh --selftest" >&2
  exit 2
fi

# Resolve the evidence root: a path as-is, or working/forms/<slug>/.
EVIDENCE="$ARG"
if [ ! -d "$EVIDENCE" ]; then
  for cand in "$PWD/working/forms/$ARG" "$HOME/clawd/working/forms/$ARG"; do
    if [ -d "$cand" ]; then EVIDENCE="$cand"; break; fi
  done
fi

if [ ! -d "$EVIDENCE" ]; then
  echo "✗ evidence root not found: $ARG" >&2
  exit 2
fi
if [ ! -f "$TOOLS/ghl_verify.py" ]; then
  echo "✗ verifier not found at $TOOLS/ghl_verify.py" >&2
  exit 2
fi

echo "═══ Skill 6 — render gate (form) ═══"
echo "evidence: $EVIDENCE"

EVIDENCE="$EVIDENCE" TOOLS="$TOOLS" JSON="$JSON" python3 - <<'PY'
import os, sys, json, glob
sys.path.insert(0, os.environ["TOOLS"])
root = os.environ["EVIDENCE"]
want_json = bool(os.environ.get("JSON"))

# Locate the build receipt written by ghl_form_builder.build_form (live path).
receipt = os.path.join(root, "routing", "form-built.json")
if not os.path.isfile(receipt):
    hits = glob.glob(os.path.join(root, "**", "form-built.json"), recursive=True)
    receipt = hits[0] if hits else ""
if not receipt or not os.path.isfile(receipt):
    print("✗ no routing/form-built.json in evidence — the form build did not "
          "complete a live run (nothing to render-gate).", file=sys.stderr)
    sys.exit(2)

with open(receipt) as fh:
    built = json.load(fh)

v = built.get("verify") or {}
preview_url = v.get("preview_url") or built.get("preview_url") or ""
marker = v.get("marker") or built.get("marker") or ""
page_id = v.get("page_id") or built.get("page_id") or built.get("form_id") or ""

if not preview_url or not marker:
    print(f"✗ form-built.json missing verify.preview_url or verify.marker "
          f"(preview_url={preview_url!r} marker={marker!r}) — cannot render-gate.",
          file=sys.stderr)
    sys.exit(2)
if not marker.startswith("zhc_"):
    print(f"✗ marker {marker!r} is not a zhc_ token — the gate proves the "
          f"agent-built form rendered; use a zhc_ field key / container marker.",
          file=sys.stderr)
    sys.exit(1)

try:
    import ghl_verify
except Exception as exc:  # noqa: BLE001
    print(f"✗ ghl_verify unavailable ({exc})", file=sys.stderr)
    sys.exit(2)

page = {"step": "form-embed", "name": built.get("form_name", "form"),
        "page_id": page_id, "preview_url": preview_url, "marker": marker}

# LIVE render_check — the ONLY accepted pass criterion (fetcher MUST be None).
rec = ghl_verify.verify_page(page, run_dir=root, live=True)

http = rec.get("http")
mird = bool(rec.get("marker_in_rendered_dom"))
rerrs = rec.get("render_errors") or []
ok = (http == 200) and (not rerrs) and mird

if want_json:
    print(json.dumps({"ok": ok, "http": http, "marker": marker,
                      "marker_in_rendered_dom": mird, "render_errors": rerrs,
                      "preview_url": preview_url, "receipt": receipt}, indent=2))
else:
    print(f"  http={http}  marker_in_rendered_dom={mird}  render_errors={len(rerrs)}")
    for e in rerrs[:6]:
        print(f"    render_error: {e}")

sys.exit(0 if ok else 1)
PY
rc=$?

# ── U9 §7.2 — emit the QC verdict onto the Command Center card (FAIL-SOFT, opt-in).
# When CC_TASK_ID is exported (the card this build owns), post the render-gate score
# to the card so the CC QC sweep reads ONE source. The render gate is mechanical
# (pass/fail), so it maps PASS→10.0 / FAIL→0.0; rc 2 (inconclusive) posts nothing.
# Any failure here is swallowed — the build reads THIS script's exit code, not the post.
if [ -n "${CC_TASK_ID:-}" ] && [ -f "$TOOLS/cc_board.py" ]; then
  _qc_score=""; _qc_pass=""
  case "$rc" in
    0) _qc_score="10.0"; _qc_pass="1" ;;
    1) _qc_score="0.0";  _qc_pass="0" ;;
  esac
  if [ -n "$_qc_pass" ]; then
    _qc_card="$EVIDENCE/routing/form-built.json"
    python3 "$TOOLS/cc_board.py" --emit-qc --task-id "$CC_TASK_ID" \
      --gate "qc-built-form" --score "$_qc_score" --passed "$_qc_pass" \
      --scorecard "$_qc_card" >/dev/null 2>&1 || true
  fi
fi

if [ $rc -eq 0 ]; then
  echo "✓ render gate PASS — HTTP 200 + zhc_ marker in RENDERED DOM; form build is done"
elif [ $rc -eq 2 ]; then
  echo "✗ render gate INCONCLUSIVE — missing evidence/verifier (see above)"
else
  echo "✗ render gate FAIL — form did not render 200 with its zhc_ marker; fix and re-run"
fi
exit $rc
