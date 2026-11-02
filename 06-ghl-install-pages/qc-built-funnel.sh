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
#   1  = FAB-QC score < 8.5 OR a hard miss OR the mandatory FAB-QC overlay did not
#        run (scorer missing/crashed) (build is NOT done)
#   2  = usage error / evidence root not found
#
# Environment:
#   QC_FUNNEL_LEGACY_EVIDENCE=1  opt-out for PRE-SEO-era evidence: a MISSING seoMeta
#                                is then a WARN instead of a hard miss. Current builds
#                                leave it unset (a missing/blank §2 SEO panel is a
#                                HARD FAIL per SOP §2.07). The opt-out is never silent: it
#                                is logged to stderr, recorded in scorecard/qc-alerts.jsonl
#                                and posted to the CC card (when CC_TASK_ID is set).
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
# S06-16: the FAB-QC overlay is MANDATORY for a funnel build. A scorer that is absent
# (e.g. a 999 box without shared-utils/fab_qc.py) means the >= 8.5 gate never ran —
# that is a FAILED build, never an exit-2 "environment" skip a caller could read past.
if [ ! -f "$SCORER" ]; then
  echo "✗ FAB-QC overlay did not run: scorer not found at $SCORER — FAILED (the overlay is mandatory for funnel builds)" >&2
  exit 1
fi

echo "═══ Skill 6 — FAB-QC build gate (funnel) ═══"
echo "evidence: $EVIDENCE"

# ── §2/§3 transcript end-state pre-gate (SEO panel + founder author + media
# folder discipline). Scores the build-recipe coverage the shared FAB scorer does
# not: a saved seoMeta that is PRESENT-BUT-INVALID is a hard build miss (HALT), and
# a MISSING seoMeta is a hard miss for a current build (the §2 panel is REQUIRED).
# Fail-closed on the gate itself too: unreadable evidence JSON and a pre-gate that
# cannot run (ghl_builder import failure) are hard misses, and the Python exit
# status is propagated — an unproved gate is never a pass. Missing media-folder
# receipts still WARN when no images were promised. QC_FUNNEL_LEGACY_EVIDENCE=1 is
# the explicit, documented opt-out that keeps pre-SEO-era evidence at WARN.
LEGACY_EVIDENCE="${QC_FUNNEL_LEGACY_EVIDENCE:-0}"
if [ "$LEGACY_EVIDENCE" = "1" ]; then
  echo "ALERT QC_FUNNEL_LEGACY_EVIDENCE=1: missing seoMeta is downgraded to WARN for this run (pre-SEO-era opt-out armed)" >&2
  mkdir -p "$EVIDENCE/scorecard"
  printf '{"alert":"legacy_seo_evidence","env":"QC_FUNNEL_LEGACY_EVIDENCE=1","ts":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$EVIDENCE/scorecard/qc-alerts.jsonl"
  if [ -n "${CC_TASK_ID:-}" ] && [ -f "$SKILL_DIR/tools/cc_board.py" ]; then
    TOOLS="$SKILL_DIR/tools" python3 -c 'import os,sys; sys.path.insert(0,os.environ["TOOLS"]); import cc_board; cc_board.post_activity(os.environ["CC_TASK_ID"],"updated","ALERT: QC_FUNNEL_LEGACY_EVIDENCE=1 downgraded the SEO hard gate",{"alert":"legacy_seo_evidence"})' >/dev/null 2>&1 || true
  fi
fi
SEO_MEDIA_FAIL=0
_seo_out="$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/seo-pregate.$$.out")"
EVIDENCE="$EVIDENCE" TOOLS="$SKILL_DIR/tools" LEGACY="$LEGACY_EVIDENCE" \
  python3 - > "$_seo_out" 2>&1 <<'PY'
import json, os, sys, glob
sys.path.insert(0, os.environ["TOOLS"])
root = os.environ["EVIDENCE"]
legacy = os.environ.get("LEGACY") == "1"
try:
    import ghl_builder as b
except Exception as exc:                 # tooling broken → the gate cannot run at all
    print(f"FAIL ghl_builder import failed ({exc}) — SEO pre-gate cannot run; "
          "an unproved gate is not a pass")
    sys.exit(3)

# S06-12: the step type comes from the ROUTE NODE (the Skill 83 / Skill 49 compiled
# route graph's page role), never from the page name. A purchase-path or thank-you
# page is scored against the PRIVACY policy (robots noindex), a marketing page against
# the full SEO gates — one policy, via ghl_builder.assert_step_seo_populated.
_PRIVATE_PURCHASE = ("checkout", "upsell", "downsell", "product_selection", "selection")
_PRIVATE_THANK_YOU = ("thank_you", "thankyou")
_MARKETING = ("landing", "sales", "sales_page", "opt_in", "optin", "registration")

def _step_type_of_role(role):
    r = "_".join(str(role).strip().lower().replace("-", "_").split())
    if r in _MARKETING:
        return "marketing"
    if r.startswith(_PRIVATE_THANK_YOU):
        return "thank_you"
    if r.startswith(_PRIVATE_PURCHASE):
        return "purchase"
    return None                                  # unknown role → caller fails closed

def _graph_roles(o, out):
    """page_id -> role for every route-graph node found anywhere in the evidence."""
    if isinstance(o, dict):
        nodes = o.get("nodes")
        if isinstance(nodes, list):
            for n in nodes:
                if isinstance(n, dict) and n.get("page_id") and (n.get("role") or n.get("page_role")):
                    out[str(n["page_id"])] = n.get("page_role") or n.get("role")
        for v in o.values():
            _graph_roles(v, out)
    elif isinstance(o, list):
        for v in o:
            _graph_roles(v, out)

def _walk(o, graph, role=None):
    """Yield (seoMeta, route_role|None). The role is the nearest enclosing page's
    ``page_role`` / ``route_node.{page_role,role}`` / ``page_id`` (looked up in the graph)."""
    if isinstance(o, dict):
        rn = o.get("route_node") if isinstance(o.get("route_node"), dict) else {}
        here = (o.get("page_role") or rn.get("page_role") or rn.get("role")
                or graph.get(str(o.get("page_id") or rn.get("page_id") or "")) or role)
        if "seoMeta" in o and isinstance(o["seoMeta"], dict):
            yield o["seoMeta"], here
        for v in o.values():
            yield from _walk(v, graph, here)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, graph, role)

seo_seen = 0
seo_bad = []
unreadable = []
media_seen = 0
docs = []
for fp in glob.glob(os.path.join(root, "**", "*.json"), recursive=True):
    try:
        with open(fp) as f:
            raw = f.read()
    except Exception as exc:
        unreadable.append((os.path.relpath(fp, root), f"read error: {exc}"))
        continue
    if '"folderId"' in raw or '"name_prefix"' in raw or "ensure_funnel_media_folders" in raw:
        media_seen += 1
    try:
        data = json.loads(raw)
    except Exception as exc:
        unreadable.append((os.path.relpath(fp, root), f"invalid JSON: {exc}"))
        continue
    docs.append((fp, data))

graph = {}
for _, data in docs:
    _graph_roles(data, graph)
step_counts = {}
for fp, data in docs:
    rel = os.path.relpath(fp, root)
    for meta, role in _walk(data, graph):
        seo_seen += 1
        if role is None:
            # no route node on this page: score it as a public marketing page (the
            # strictest policy) — a page can only be private by being a private NODE.
            stype = "marketing"
        else:
            stype = _step_type_of_role(role)
            if stype is None:
                seo_bad.append((rel, [f"unclassifiable route role {role!r} — step type "
                                      "must come from a known route node role"]))
                continue
        step_counts[stype] = step_counts.get(stype, 0) + 1
        # Marketing = assert_step_seo_populated's own marketing branch (identical call);
        # private steps go through the step-aware privacy gate.
        res = (b.assert_seo_populated(meta) if stype == "marketing"
               else b.assert_step_seo_populated(meta, {"step_type": stype}))
        if not res.get("ok"):
            seo_bad.append((rel, [f"[{stype}] {r}" for r in (res.get("reasons") or [])]))

if unreadable:
    for rel, why in unreadable[:5]:
        print(f"FAIL unreadable evidence {rel}: {why}")
    if len(unreadable) > 5:
        print(f"FAIL unreadable evidence: {len(unreadable) - 5} more file(s) not shown")
    sys.exit(2)                                # unreadable evidence → hard miss
if seo_bad:
    for rel, reasons in seo_bad:
        print(f"FAIL seoMeta invalid in {rel}: {reasons}")
    sys.exit(2)                                # hard miss → caller fails the build
if seo_seen:
    print(f"PASS {seo_seen} seoMeta object(s) populated (marketing: author=founder, "
          "length/keyword/canonical/lang gates ok; purchase/thank_you: robots "
          f"noindex privacy gate ok) step types={dict(sorted(step_counts.items()))}")
elif legacy:
    print("WARN no seoMeta found in evidence — §2 SEO panel end-state not "
          "demonstrated (QC_FUNNEL_LEGACY_EVIDENCE=1, pre-SEO-era evidence)")
else:
    print("FAIL no seoMeta found in evidence — §2 SEO panel end-state not "
          "demonstrated; a current build REQUIRES a populated seoMeta "
          "(QC_FUNNEL_LEGACY_EVIDENCE=1 is only for pre-SEO-era evidence)")
    sys.exit(2)                                # required metadata unproved → hard miss

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
SEO_RC=$?
SEO_PREGATE="$(cat "$_seo_out")"
rm -f "$_seo_out" 2>/dev/null || true
echo "$SEO_PREGATE"
case "$SEO_PREGATE" in *FAIL*) SEO_MEDIA_FAIL=1 ;; esac
if [ "$SEO_RC" -ne 0 ]; then
  # An exception, an import failure or a python3 that never ran leaves no FAIL line —
  # the status is the signal. The pre-gate not running is a hard miss, not a skip.
  SEO_MEDIA_FAIL=1
  echo "✗ SEO/media pre-gate exited $SEO_RC — hard miss (an unproved gate is not a pass)" >&2
fi

python3 "$SCORER" --evidence "$EVIDENCE" --kind funnel --gate $JSON
rc=$?
# Any non-zero scorer status (score < 8.5, hard miss, crash, argparse exit 2) is a
# FAILED build — never let a scorer's own exit 2 masquerade as "evidence not found".
[ "$rc" -ne 0 ] && rc=1
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
