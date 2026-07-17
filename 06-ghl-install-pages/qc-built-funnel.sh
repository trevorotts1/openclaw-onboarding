#!/usr/bin/env bash
# qc-built-funnel.sh — Skill 6: per-build FAB-QC for a constructed funnel.
#
# DISTINCT from qc-ghl-install-pages.sh (install-level QC for the skill itself).
# This is the per-BUILD, library-aware quality gate — the Skill-6 parallel of
# Skill-44's qc-built-workflow.sh. It is a SUPERSET OVERLAY on top of the canonical
# ghl_verify render gate: ghl_verify (HTTP 200 + marker) stays the hard mechanical
# floor (scored as FAB-QC dimension D3); this script adds the six library-aware
# dimensions (template fidelity, copy substance, render/soundness, persona grounding,
# flexibility honored, funnel<->automation link integrity) and the >= 8.5 verdict.
#
# Usage:
#   ./qc-built-funnel.sh <evidence_root> [--json]
#   ./qc-built-funnel.sh <slug>          # resolves working/funnels/<slug>/ if it exists
#
# Exit codes:
#   0  = FAB-QC score >= 8.5 AND no hard miss
#   1  = FAB-QC score < 8.5 OR a hard miss (build is NOT done)
#   2  = evidence root not found / scorer unavailable
#
# The shared scorer is shared-utils/fab_qc.py; the rubric is
# universal-sops/funnel-automation-build-quality-rubric.md.
set -u

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
SCORER="$REPO_ROOT/shared-utils/fab_qc.py"

ARG="${1:-}"
JSON=""
[ "${2:-}" = "--json" ] && JSON="--json"

if [ -z "$ARG" ]; then
  echo "usage: qc-built-funnel.sh <evidence_root|slug> [--json]" >&2
  exit 2
fi

# Resolve the evidence root: a path as-is, or working/funnels/<slug>/.
EVIDENCE="$ARG"
if [ ! -d "$EVIDENCE" ]; then
  for cand in "$PWD/working/funnels/$ARG" "$HOME/clawd/working/funnels/$ARG"; do
    if [ -d "$cand" ]; then EVIDENCE="$cand"; break; fi
  done
fi

if [ ! -d "$EVIDENCE" ]; then
  echo "✗ evidence root not found: $ARG" >&2
  exit 2
fi
if [ ! -f "$SCORER" ]; then
  echo "✗ FAB-QC scorer not found at $SCORER" >&2
  exit 2
fi

echo "═══ Skill 6 — FAB-QC build gate (funnel) ═══"
echo "evidence: $EVIDENCE"

# ── §2/§3 transcript end-state pre-gate (SEO panel + founder author + media
# folder discipline). Scores the build-recipe coverage the shared FAB scorer does
# not: a saved seoMeta that is PRESENT-BUT-INVALID is a hard build miss (HALT);
# missing seoMeta/media-folder receipts WARN (older evidence may predate them).
SEO_MEDIA_FAIL=0
_seo_out="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/seo-pregate.$$.out")"
EVIDENCE="$EVIDENCE" TOOLS="$SKILL_DIR/tools" python3 - > "$_seo_out" 2>&1 <<'PY'
import json, os, sys, glob
sys.path.insert(0, os.environ["TOOLS"])
root = os.environ["EVIDENCE"]
try:
    import ghl_builder as b
except Exception as exc:                       # tooling missing → can't pre-gate
    print(f"WARN ghl_builder import failed ({exc}); skipping SEO pre-gate"); sys.exit(0)

def _walk(o):
    if isinstance(o, dict):
        if "seoMeta" in o and isinstance(o["seoMeta"], dict):
            yield o["seoMeta"]
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)

seo_seen = 0
seo_bad = []
media_seen = 0
for fp in glob.glob(os.path.join(root, "**", "*.json"), recursive=True):
    try:
        with open(fp) as f:
            raw = f.read()
    except Exception:
        continue
    if '"folderId"' in raw or '"name_prefix"' in raw or "ensure_funnel_media_folders" in raw:
        media_seen += 1
    try:
        data = json.loads(raw)
    except Exception:
        continue
    for meta in _walk(data):
        seo_seen += 1
        res = b.assert_seo_populated(meta)
        if not res.get("ok"):
            seo_bad.append((os.path.relpath(fp, root), res.get("reasons")))

if seo_bad:
    for rel, reasons in seo_bad:
        print(f"FAIL seoMeta invalid in {rel}: {reasons}")
    sys.exit(2)                                # hard miss → caller fails the build
print(f"PASS {seo_seen} seoMeta object(s) populated (author=founder, length/keyword/canonical/lang gates ok)"
      if seo_seen else
      "WARN no seoMeta found in evidence — §2 SEO panel end-state not demonstrated")

# ── §3/§4 image-delivery gate (FIX-XC-03c + FIX-IMG-09 iii) ──────────────────
# A SUCCESS images/manifest.json (>=1 record with a real https cdn_url) means the
# build PROMISED rendered images. When it exists, two checks become HARD (FAIL):
#   (a) the rendered/preview evidence must contain an <img> AND at least one of the
#       manifest cdn_urls (the un-fakeable rendered-DOM gate, mirrored from
#       ghl_verify — an image confirmed only in stored bytes is not confirmed), and
#   (b) a media-folder receipt must be present (folder discipline).
# With NO success manifest (image-less / legacy evidence) both stay WARN.
manifest_cdn_urls = []
for fp in glob.glob(os.path.join(root, "**", "images", "manifest.json"), recursive=True):
    try:
        recs = json.load(open(fp))
    except Exception:
        continue
    if isinstance(recs, list):
        for r in recs:
            if isinstance(r, dict):
                u = str(r.get("cdn_url", "")).strip()
                if u.lower().startswith("https://"):
                    manifest_cdn_urls.append(u)
manifest_present = len(manifest_cdn_urls) > 0

if manifest_present:
    # Gather all rendered/preview evidence (raw HTML + preview verify JSON).
    rendered = []
    for pat in ("**/*.html", "**/*preview*.json", "**/final-preview-verify.json"):
        for fp in glob.glob(os.path.join(root, pat), recursive=True):
            try:
                rendered.append(open(fp, encoding="utf-8", errors="replace").read())
            except Exception:
                continue
    rendered_text = "\n".join(rendered)
    has_img_tag = "<img" in rendered_text.lower()
    landed = [u for u in manifest_cdn_urls if u in rendered_text]
    if has_img_tag and landed:
        print(f"PASS rendered-<img> gate — {len(landed)}/{len(manifest_cdn_urls)} "
              "manifest cdn_url(s) present in an <img> in the rendered/preview evidence")
    else:
        missing = [u for u in manifest_cdn_urls if u not in rendered_text]
        print("FAIL images/manifest.json present with "
              f"{len(manifest_cdn_urls)} cdn_url(s) but the rendered/preview evidence "
              f"has no <img> referencing a CDN URL (has_img_tag={has_img_tag}, "
              f"landed={len(landed)}/{len(manifest_cdn_urls)}, "
              f"missing_sample={(missing[:1] or ['-'])[0]})")
    if media_seen:
        print("PASS media-folder receipt(s) present")
    else:
        print("FAIL images/manifest.json present but NO media-folder receipt "
              "(folderId/name_prefix) in evidence — §3 folder discipline not demonstrated")
else:
    print("PASS media-folder receipt(s) present" if media_seen else
          "WARN no media-folder receipt / image manifest found in evidence — "
          "§3 folder discipline not demonstrated (no images promised)")
PY
SEO_PREGATE="$(cat "$_seo_out")"
rm -f "$_seo_out" 2>/dev/null || true
echo "$SEO_PREGATE"
case "$SEO_PREGATE" in *FAIL*) SEO_MEDIA_FAIL=1 ;; esac

python3 "$SCORER" --evidence "$EVIDENCE" --kind funnel --gate $JSON
rc=$?
[ "$SEO_MEDIA_FAIL" -eq 1 ] && rc=1

# ── U24/B-U10 — GitHub archival receipt gate. Always on (not flag-gated): it
# is a no-op (applicable=false) for every evidence root that never used the
# VERCEL_EMBED path, and per the D6/B-D2 ratified non-blocking doctrine it
# NEVER fails a build over a transient archive failure (an honest FAILED
# receipt stays open for `ghl_github_reconcile.py --retry` / the scheduled
# maintenance-window sweep) — it only flags total SILENCE: a VERCEL_EMBED
# deploy with NO archive receipt at all. Also prints GitHub token presence by
# NAME only (never a value).
ARCHIVE_GATE="$SKILL_DIR/tools/ghl_archive_receipt_gate.py"
if [ -f "$ARCHIVE_GATE" ]; then
  python3 "$ARCHIVE_GATE" --evidence-root "$EVIDENCE" --gate
  [ $? -ne 0 ] && rc=1
fi

# ── U25/B-U11 — Page-QC v2: the semantic scorer FAB-QC cannot be (six dimensions,
# client's own judge model via model_router's qc role, 8.5, SKIP-not-fabricate).
# Runs AFTER FAB-QC on the SAME evidence tree, producing scorecard/page-qc.json.
# Additive + flag-gated: PAGE_QC_ENABLED=1 turns it on; unset -> this block is a
# no-op (scorer file stays inert — the revert path). Does NOT flip $rc: the
# both-gates enforcement (FAB-QC PASS + Page-QC PASS required for review->done) is
# B-U12/U26's job at the Command Center review gate, not this per-build wrapper.
PAGE_QC="$REPO_ROOT/shared-utils/page_qc.py"
if [ "${PAGE_QC_ENABLED:-0}" = "1" ] && [ -f "$PAGE_QC" ]; then
  mkdir -p "$EVIDENCE/scorecard"
  _pqc_json="$EVIDENCE/scorecard/page-qc.json"
  python3 "$PAGE_QC" --evidence "$EVIDENCE" --json ${CC_TASK_ID:+--task-id "$CC_TASK_ID"} \
    >"$_pqc_json" 2>"$_pqc_json.err" || true
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$_pqc_json" >/dev/null 2>&1; then
    _pqc_verdict="$(python3 -c "import json; print(json.load(open('$_pqc_json')).get('verdict','?'))" 2>/dev/null)"
    echo "$_pqc_verdict (scorecard/page-qc.json)"
  else
    echo "Page-QC v2: scorer produced no valid JSON — see scorecard/page-qc.json.err"
  fi
  rm -f "$_pqc_json.err" 2>/dev/null || true
fi

# ── U9 §7.2 — emit the QC verdict onto the Command Center card (FAIL-SOFT, opt-in).
# When CC_TASK_ID is exported, post the FAB-QC score to the card so the CC QC sweep
# reads ONE source (no re-scoring drift). The numeric 0-10 'score' is read from a
# read-only --json re-score of the same evidence; the PASS/FAIL verdict comes from
# rc (which folds in the SEO/media hard-miss, not just the weighted mean). Any
# failure here is swallowed — the build reads THIS script's exit code, not the post.
if [ -n "${CC_TASK_ID:-}" ] && [ -f "$SKILL_DIR/tools/cc_board.py" ]; then
  _qc_json="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/fabqc.$$.json")"
  python3 "$SCORER" --evidence "$EVIDENCE" --kind funnel --json >"$_qc_json" 2>/dev/null || true
  _qc_pass=0; [ $rc -eq 0 ] && _qc_pass=1
  python3 "$SKILL_DIR/tools/cc_board.py" --emit-qc --task-id "$CC_TASK_ID" \
    --gate "qc-built-funnel" --passed "$_qc_pass" --scorecard "$_qc_json" >/dev/null 2>&1 || true
  rm -f "$_qc_json" 2>/dev/null || true
fi

if [ $rc -eq 0 ]; then
  echo "✓ FAB-QC PASS (>= 8.5) — funnel build is done"
else
  echo "✗ FAB-QC FAIL (< 8.5 or hard miss) — funnel build is NOT done; fix the lowest dimension and re-run"
fi
exit $rc
