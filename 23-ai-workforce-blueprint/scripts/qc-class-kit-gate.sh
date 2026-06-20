#!/usr/bin/env bash
# ============================================================================
# Department Class-Kit ENFORCEMENT GATE  (Phase-4)
# ----------------------------------------------------------------------------
# Mechanically enforces the binding Department Class-Kit standard so no future
# department can ship as a text-only page again. Implements Gates A-D from
# DEPT-KIT-ENFORCEMENT-PLAN and the acceptance gate in DEPT-KIT-TEMPLATE.md.
#
# USAGE:
#   qc-class-kit-gate.sh <kit-folder> [<notion-page-id>]
#
#   <kit-folder>       Path to ONE department class-kit folder on disk.
#   <notion-page-id>   (optional) Notion page id for the department's sub-page.
#                      When given, Gate C (embedding) + Gate D (structure) run
#                      against the LIVE Notion page tree. Requires NOTION_API_KEY
#                      (or NOTION_TOKEN) in the environment and python3.
#                      When omitted, Gates A/B run on disk and Gate D runs its
#                      on-disk placeholder/structure checks; Gate C is SKIPPED.
#
# EXIT CODES:
#   0  PASS  — all applicable gates passed; raw counts printed.
#   1  REJECT / AUTO-FAIL — a gate failed; a clear reason is printed.
#   2  USAGE / environment error.
#
# This gate is GENERIC department documentation only. No client names anywhere.
# ============================================================================
set -u

# ---------- pretty output ----------
if [ -t 1 ]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'
else
  R=""; G=""; Y=""; B=""; Z=""
fi
red(){   printf "%s%s%s\n" "$R" "$1" "$Z"; }
green(){ printf "%s%s%s\n" "$G" "$1" "$Z"; }
yellow(){ printf "%s%s%s\n" "$Y" "$1" "$Z"; }
bold(){  printf "%s%s%s\n" "$B" "$1" "$Z"; }

FAILED=0
REASONS=()
fail(){ FAILED=1; REASONS+=("$1"); red "  ✗ $1"; }
ok(){   green "  ✓ $1"; }
info(){ printf "    %s\n" "$1"; }

# ---------- args ----------
KIT="${1:-}"
PAGE_ID="${2:-}"
if [ -z "$KIT" ]; then
  echo "usage: $(basename "$0") <kit-folder> [<notion-page-id>]" >&2
  exit 2
fi
if [ ! -d "$KIT" ]; then
  echo "ERROR: kit folder not found: $KIT" >&2
  exit 2
fi
KIT="${KIT%/}"

echo ""
bold "═══════════════════════════════════════════════════════════════════"
bold " DEPARTMENT CLASS-KIT ENFORCEMENT GATE"
bold "═══════════════════════════════════════════════════════════════════"
echo "  Kit folder : $KIT"
if [ -n "$PAGE_ID" ]; then echo "  Notion page: $PAGE_ID"; else echo "  Notion page: (none — Gate C skipped)"; fi
echo ""

# ============================================================================
# Helpers — locate artifacts that the gold exemplar keeps in subfolders.
# Deck PPTX may live in <kit>/deck/ or kit root.
# Cheatsheets may live in <kit>/infographics/ or kit root.
# ============================================================================
count_glob(){ # count files matching a glob pattern (pass the pattern QUOTED)
  # Globs internally so multi-match patterns are counted correctly and an
  # unmatched pattern yields 0 (nullglob), not the literal pattern.
  local pat="$1" n=0 f
  local _ng=0
  shopt -q nullglob && _ng=1
  shopt -s nullglob
  for f in $pat; do [ -e "$f" ] && n=$((n+1)); done
  [ "$_ng" -eq 0 ] && shopt -u nullglob
  echo "$n"
}

# locate the deck pptx
DECK=""
for cand in "$KIT/deck/"*LIGHT*.pptx "$KIT/"*LIGHT*.pptx "$KIT/deck/"*.pptx; do
  if [ -e "$cand" ]; then DECK="$cand"; break; fi
done

# locate cheatsheet dir (where cheatsheet-N-*.png live)
CHEAT_DIR=""
for d in "$KIT/infographics" "$KIT"; do
  if [ -n "$(count_glob "$d/cheatsheet-[1-4]-*.png")" ] && [ "$(count_glob "$d/cheatsheet-[1-4]-*.png")" -gt 0 ]; then
    CHEAT_DIR="$d"; break
  fi
done

RENDERS="$KIT/renders-light"
MICRO="$KIT/micro-infographics"

# derive role count N from the 02-The-<N>-Roles file stem
ROLE_FILE="$(ls "$KIT"/02-The-*-Roles.pdf 2>/dev/null | head -1)"
ROLE_N=""
if [ -n "$ROLE_FILE" ]; then
  base="$(basename "$ROLE_FILE")"
  ROLE_N="$(printf '%s' "$base" | sed -nE 's/^02-The-([0-9]+)-Roles\.pdf$/\1/p')"
fi

# ============================================================================
# GATE A — Kit Folder Completeness
# ============================================================================
bold "── GATE A — Kit Folder Completeness ──────────────────────────────"

# A.0 master index
if [ -s "$KIT/00-DELIVERY-PACKAGE-INDEX.md" ]; then ok "00-DELIVERY-PACKAGE-INDEX.md present"
else fail "Gate A: missing 00-DELIVERY-PACKAGE-INDEX.md"; fi

# A.1 — 8 module HTML + 8 module PDF
MOD_HTML="$(count_glob "$KIT/0[1-8]-*.html")"
MOD_PDF="$(count_glob "$KIT/0[1-8]-*.pdf")"
info "module HTML = $MOD_HTML (need 8) | module PDF = $MOD_PDF (need 8)"
[ "$MOD_HTML" -ge 8 ] && ok "8 module .html present ($MOD_HTML)" || fail "Gate A: only $MOD_HTML/8 module .html files"
[ "$MOD_PDF"  -ge 8 ] && ok "8 module .pdf present ($MOD_PDF)"   || fail "Gate A: only $MOD_PDF/8 module .pdf files"

# A.2 — compact + DELUXE PDF + DELUXE HTML  (=> 10 PDFs total)
COMPACT="$(count_glob "$KIT/*-Department-Class-Reference.pdf")"
DELUXE_PDF="$(count_glob "$KIT/*-Department-Class-Reference-DELUXE.pdf")"
DELUXE_HTML="$(count_glob "$KIT/*-Department-Class-Reference-DELUXE.html")"
TOTAL_PDF="$(count_glob "$KIT/*.pdf")"
info "compact PDF = $COMPACT | DELUXE PDF = $DELUXE_PDF | DELUXE HTML = $DELUXE_HTML | total PDFs = $TOTAL_PDF (need 10)"
[ "$COMPACT" -ge 1 ]     && ok "compact reference PDF present"      || fail "Gate A: missing compact *-Department-Class-Reference.pdf"
[ "$DELUXE_PDF" -ge 1 ]  && ok "DELUXE reference PDF present"       || fail "Gate A: missing *-Department-Class-Reference-DELUXE.pdf"
[ "$DELUXE_HTML" -ge 1 ] && ok "DELUXE HTML source present"        || fail "Gate A: missing *-Department-Class-Reference-DELUXE.html"
[ "$TOTAL_PDF" -ge 10 ]  && ok "10 PDFs total (8 modules + compact + DELUXE) = $TOTAL_PDF" || fail "Gate A: only $TOTAL_PDF/10 PDFs (need 8 modules + compact + DELUXE)"

# A.3 — primary deck PPTX exists
if [ -n "$DECK" ]; then ok "primary deck PPTX present ($(basename "$DECK"))"
else fail "Gate A: no *-LIGHT-*.pptx deck found in $KIT/deck/ or kit root"; fi

# A.4 — slide PNG count == slide PROMPT count == deck slide count (deck check is Gate B)
SLIDE_PNG="$(count_glob "$RENDERS/slide-[0-9]*.png")"
SLIDE_PROMPT="$(count_glob "$RENDERS/slide-*-PROMPT.txt")"
info "slide PNGs = $SLIDE_PNG | slide PROMPTs = $SLIDE_PROMPT"
if [ "$SLIDE_PNG" -gt 0 ] && [ "$SLIDE_PNG" -eq "$SLIDE_PROMPT" ]; then
  ok "slide PNG count == slide PROMPT count ($SLIDE_PNG)"
else
  fail "Gate A: slide PNG ($SLIDE_PNG) != slide PROMPT ($SLIDE_PROMPT), or zero renders"
fi
[ -s "$RENDERS/kie_task_ids.json" ] && ok "renders-light/kie_task_ids.json present" || fail "Gate A: missing renders-light/kie_task_ids.json"

# A.5 — speech .md + teleprompter .html
SPEECH="$(count_glob "$KIT/*SPEECH.md")"
TELE="$(count_glob "$KIT/*teleprompter.html")"
info "speech .md = $SPEECH | teleprompter .html = $TELE"
[ "$SPEECH" -ge 1 ] && ok "speech *SPEECH.md present"            || fail "Gate A: missing *SPEECH.md"
[ "$TELE" -ge 1 ]   && ok "teleprompter *teleprompter.html present" || fail "Gate A: missing *teleprompter.html"

# A.6 — 4 cheatsheet PNGs + 4 cheatsheet prompts
if [ -n "$CHEAT_DIR" ]; then
  CHEAT_PNG="$(count_glob "$CHEAT_DIR/cheatsheet-[1-4]-*.png")"
  CHEAT_PROMPT="$(count_glob "$CHEAT_DIR/cheatsheet-[1-4]-*-PROMPT.txt")"
else
  CHEAT_PNG=0; CHEAT_PROMPT=0
fi
info "cheatsheet PNGs = $CHEAT_PNG (need 4) | cheatsheet PROMPTs = $CHEAT_PROMPT (need 4)  [dir: ${CHEAT_DIR:-not found}]"
[ "$CHEAT_PNG" -ge 4 ]    && ok "4 cheatsheet PNGs present ($CHEAT_PNG)"       || fail "Gate A: only $CHEAT_PNG/4 cheatsheet PNGs"
[ "$CHEAT_PROMPT" -ge 4 ] && ok "4 cheatsheet PROMPTs present ($CHEAT_PROMPT)" || fail "Gate A: only $CHEAT_PROMPT/4 cheatsheet PROMPTs"

# A.7 — micro PNG count == micro PROMPT count (1:1) AND covers every role (>= role count)
MICRO_PNG="$(count_glob "$MICRO/*.png")"
MICRO_PROMPT="$(count_glob "$MICRO/*-PROMPT.txt")"
info "micro PNGs = $MICRO_PNG | micro PROMPTs = $MICRO_PROMPT | dept role count (N) = ${ROLE_N:-unknown}"
if [ "$MICRO_PNG" -gt 0 ] && [ "$MICRO_PNG" -eq "$MICRO_PROMPT" ]; then
  ok "micro PNG count == micro PROMPT count ($MICRO_PNG, 1:1)"
else
  fail "Gate A: micro PNG ($MICRO_PNG) != micro PROMPT ($MICRO_PROMPT), or zero micros"
fi
if [ -n "$ROLE_N" ]; then
  # canonical set = fixed concept infographics + one-per-role; must cover every role
  if [ "$MICRO_PNG" -ge "$ROLE_N" ]; then
    ok "micro count covers dept role count (micros $MICRO_PNG >= roles $ROLE_N)"
  else
    fail "Gate A: micro count ($MICRO_PNG) < dept role count ($ROLE_N) — not one micro per role"
  fi
else
  yellow "  ⚠ could not derive role count from 02-The-<N>-Roles.pdf; skipping micro>=roles check"
fi
[ -s "$MICRO/working/kie_task_ids.json" ] && ok "micro-infographics/working/kie_task_ids.json present" || fail "Gate A: missing micro-infographics/working/kie_task_ids.json"

# A.8 — brand spec + prompt master
[ -s "$KIT/BRAND-COLOR-SPEC.md" ] && ok "BRAND-COLOR-SPEC.md present" || fail "Gate A: missing BRAND-COLOR-SPEC.md"
PROMPT_MASTER="$(count_glob "$KIT/*-SLIDE-RENDER-PROMPTS.md")"
[ "$PROMPT_MASTER" -ge 1 ] && ok "*-SLIDE-RENDER-PROMPTS.md (prompt master) present" || fail "Gate A: missing *-SLIDE-RENDER-PROMPTS.md prompt master"

echo ""

# ============================================================================
# GATE B — Deck Threshold (raw unzip|grep -c)
# ============================================================================
bold "── GATE B — Deck Threshold (>= 20 slides) ────────────────────────"
DECK_SLIDES=-1
if [ -z "$DECK" ]; then
  fail "Gate B: no deck PPTX to inspect"
elif ! command -v unzip >/dev/null 2>&1; then
  fail "Gate B: 'unzip' not available — cannot verify slide count"
else
  DECK_SLIDES="$(unzip -l "$DECK" 2>/dev/null | grep -cE 'ppt/slides/slide[0-9]+\.xml')"
  bold "  RAW: unzip -l <pptx> | grep -cE 'ppt/slides/slide[0-9]+\\.xml' = $DECK_SLIDES"
  if [ "$DECK_SLIDES" -ge 20 ]; then
    ok "deck slide count $DECK_SLIDES >= 20"
  else
    fail "Gate B: deck slide count $DECK_SLIDES < 20 (REJECT)"
  fi
  # cross-check: slide PNG count == deck slide count
  if [ "$SLIDE_PNG" -ne "$DECK_SLIDES" ]; then
    fail "Gate B: slide PNG count ($SLIDE_PNG) != deck slide count ($DECK_SLIDES)"
  else
    ok "slide PNG count == deck slide count ($DECK_SLIDES)"
  fi
fi
echo ""

# ============================================================================
# GATE D (on-disk portion) — placeholder/deferral language scan
# Runs whether or not a Notion page id is supplied: scans the kit's own
# .md / .html artifacts for the failure-signature deferral language.
# ============================================================================
bold "── GATE D — Auto-Fail Language Scan (kit artifacts) ──────────────"
# Failure-signature phrases from the 33 failed text-only pages.
PLACEHOLDER_RE='go here|will be added|Phase 1b|embedded here as public-URL|queued for Phase|Add the PowerPoint'
# Scan human-authored deliverable docs (index/modules/reference), NOT build scripts.
HITS="$(grep -RInE "$PLACEHOLDER_RE" \
          "$KIT"/*.md "$KIT"/*.html 2>/dev/null | head -20)"
if [ -n "$HITS" ]; then
  fail "Gate D AUTO-FAIL: placeholder/deferral language found in kit artifacts:"
  printf '%s\n' "$HITS" | sed 's/^/      /'
else
  ok "no placeholder/deferral language in kit .md/.html artifacts"
fi
echo ""

# ============================================================================
# GATE C + GATE D (Notion) — only when a page id is supplied
# ============================================================================
if [ -n "$PAGE_ID" ]; then
  bold "── GATE C + D — Notion Page (live tree) ──────────────────────────"
  TOKEN="${NOTION_API_KEY:-${NOTION_TOKEN:-}}"
  if [ -z "$TOKEN" ]; then
    fail "Gate C/D: NOTION_API_KEY (or NOTION_TOKEN) not set in environment"
  elif ! command -v python3 >/dev/null 2>&1; then
    fail "Gate C/D: python3 not available to crawl the Notion page"
  else
    # Expected media floor = slides + micros + 4 cheatsheets + 9 PDFs + 1 PPTX
    EXP_IMAGES=$(( SLIDE_PNG + MICRO_PNG + 4 ))
    EXP_FILES=10
    EXP_MEDIA=$(( SLIDE_PNG + MICRO_PNG + 4 + 9 + 1 ))
    export NOTION_GATE_TOKEN="$TOKEN" NOTION_GATE_PAGE="$PAGE_ID"
    export NOTION_EXP_IMAGES="$EXP_IMAGES" NOTION_EXP_FILES="$EXP_FILES" NOTION_EXP_MEDIA="$EXP_MEDIA"
    NOTION_OUT="$(python3 - <<'PYEOF'
import os, sys, json, time, urllib.request, urllib.error, re

TOKEN = os.environ["NOTION_GATE_TOKEN"]
PAGE  = os.environ["NOTION_GATE_PAGE"]
EXP_IMAGES = int(os.environ["NOTION_EXP_IMAGES"])
EXP_FILES  = int(os.environ["NOTION_EXP_FILES"])
EXP_MEDIA  = int(os.environ["NOTION_EXP_MEDIA"])
NV = "2022-06-28"
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": NV, "Content-Type": "application/json"}

def api(path):
    url = f"https://api.notion.com/v1{path}"
    req = urllib.request.Request(url, headers=H, method="GET")
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 3:
                time.sleep(2 * (attempt + 1)); continue
            print(f"NOTION_ERROR {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
            sys.exit(7)
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1)); continue
            print(f"NOTION_ERROR: {e}", file=sys.stderr)
            sys.exit(7)

def block_text(b):
    t = b.get("type", "")
    rt = b.get(t, {}).get("rich_text", []) if isinstance(b.get(t), dict) else []
    return "".join(x.get("plain_text", x.get("text", {}).get("content", "")) for x in rt)

def media_src(b):
    """Return the live src/url for an image/file/pdf block, else ''."""
    t = b.get("type", "")
    obj = b.get(t, {})
    if not isinstance(obj, dict):
        return ""
    for key in ("file", "external"):
        if key in obj and isinstance(obj[key], dict):
            return obj[key].get("url", "")
    return obj.get("url", "")

counts = {}
images = files = pdfs = embeds = 0
h1_titles = []
src_blocks = 0
local_path_hits = []
placeholder_hits = []
toggle_count = 0

PLACEHOLDER_RE = re.compile(
    r"go here|will be added|Phase 1b|embedded here as public-URL|queued for Phase|Add the PowerPoint",
    re.IGNORECASE)
LOCAL_PATH_RE = re.compile(r"file:///|/Users/[^ ]+\.(png|pdf|pptx|jpg|jpeg)", re.IGNORECASE)

def walk(block_id, top=False):
    global images, files, pdfs, embeds, src_blocks, toggle_count
    cursor = None
    while True:
        suffix = f"&start_cursor={cursor}" if cursor else ""
        data = api(f"/blocks/{block_id}/children?page_size=100{suffix}")
        for b in data.get("results", []):
            t = b.get("type", "")
            counts[t] = counts.get(t, 0) + 1
            if t == "image": images += 1
            elif t == "file": files += 1
            elif t == "pdf": pdfs += 1
            elif t in ("embed", "video", "bookmark"): embeds += 1
            elif t == "toggle": toggle_count += 1
            if top and t == "heading_1":
                h1_titles.append(block_text(b).strip())
            src = media_src(b)
            if src:
                src_blocks += 1
                if LOCAL_PATH_RE.search(src):
                    local_path_hits.append(src[:80])
            txt = block_text(b)
            if txt and PLACEHOLDER_RE.search(txt):
                placeholder_hits.append(txt[:90])
            if b.get("has_children"):
                walk(b["id"], top=False)
        if data.get("has_more"):
            cursor = data.get("next_cursor")
        else:
            break

walk(PAGE, top=True)

artifact_blocks = images + files + pdfs + embeds
result = {
    "images": images, "files": files, "pdfs": pdfs, "embeds": embeds,
    "artifact_blocks": artifact_blocks, "src_blocks": src_blocks,
    "h1_count": len(h1_titles), "h1_titles": h1_titles,
    "toggles": toggle_count,
    "local_path_hits": local_path_hits, "placeholder_hits": placeholder_hits,
    "exp_images": EXP_IMAGES, "exp_files": EXP_FILES, "exp_media": EXP_MEDIA,
}
print(json.dumps(result))
PYEOF
)"
    NOTION_RC=$?
    if [ $NOTION_RC -ne 0 ] || [ -z "$NOTION_OUT" ]; then
      fail "Gate C/D: failed to crawl Notion page (rc=$NOTION_RC)"
    else
      # parse the JSON with python (portable) into shell vars
      eval "$(python3 - "$NOTION_OUT" <<'PYEOF'
import sys, json
d = json.loads(sys.argv[1])
def s(k): return str(d.get(k, 0))
print(f'N_IMAGES={s("images")}')
print(f'N_FILES={s("files")}')
print(f'N_PDFS={s("pdfs")}')
print(f'N_EMBEDS={s("embeds")}')
print(f'N_ARTIFACT={s("artifact_blocks")}')
print(f'N_SRC={s("src_blocks")}')
print(f'N_H1={s("h1_count")}')
print(f'N_TOGGLES={s("toggles")}')
print(f'N_EXP_IMAGES={s("exp_images")}')
print(f'N_EXP_FILES={s("exp_files")}')
print(f'N_EXP_MEDIA={s("exp_media")}')
print(f'N_LOCAL={len(d.get("local_path_hits",[]))}')
print(f'N_PLACEHOLD={len(d.get("placeholder_hits",[]))}')
# stash arrays for printing
import shlex
print('H1_TITLES=' + shlex.quote(" | ".join(d.get("h1_titles",[]))))
print('PLACEHOLD_SAMPLE=' + shlex.quote(" || ".join(d.get("placeholder_hits",[])[:5])))
print('LOCAL_SAMPLE=' + shlex.quote(" || ".join(d.get("local_path_hits",[])[:5])))
PYEOF
)"
      bold "  RAW Notion counts: images=$N_IMAGES files=$N_FILES pdfs(file)=$N_PDFS embeds=$N_EMBEDS artifact(image+file+pdf+embed)=$N_ARTIFACT src/url-bearing=$N_SRC H1=$N_H1 toggles=$N_TOGGLES"
      info "expected floor: images>=$N_EXP_IMAGES, files>=$N_EXP_FILES, media(image+file)>=$N_EXP_MEDIA"

      # ---- GATE D AUTO-FAILS first ----
      if [ "$N_ARTIFACT" -eq 0 ]; then
        fail "Gate D AUTO-FAIL: artifact-block count == 0 (text-only page — the exact 33-failure signature)"
      else
        ok "Gate D: artifact-block count > 0 ($N_ARTIFACT)"
      fi
      if [ "$N_PLACEHOLD" -gt 0 ]; then
        fail "Gate D AUTO-FAIL: placeholder/deferral language on the Notion page ($N_PLACEHOLD hits): $PLACEHOLD_SAMPLE"
      else
        ok "Gate D: no placeholder/deferral language on the Notion page"
      fi
      # ---- GATE D structure ----
      if [ "$N_H1" -eq 4 ]; then
        ok "Gate D: exactly 4 numbered H1 sections (H1 titles: $H1_TITLES)"
      else
        fail "Gate D: H1 count is $N_H1, must be exactly 4 (titles: $H1_TITLES)"
      fi
      # 7-section failed skeleton detection
      SKEL='Overview.*Roles.*SOP Library.*Workflow.*Visuals.*Signature Presentation.*Outputs'
      if printf '%s' "$H1_TITLES" | grep -qiE "$SKEL"; then
        fail "Gate D: detected the failed 7-section skeleton (Overview→…→Outputs)"
      fi

      # ---- GATE C embedding ----
      if [ "$N_LOCAL" -gt 0 ]; then
        fail "Gate C: $N_LOCAL block(s) carry a local-Mac path (must be public-URL / Notion-uploaded): $LOCAL_SAMPLE"
      else
        ok "Gate C: no local-Mac paths in media blocks"
      fi
      MEDIA_TOTAL=$(( N_IMAGES + N_FILES ))
      if [ "$MEDIA_TOTAL" -lt "$N_EXP_MEDIA" ]; then
        fail "Gate C: media blocks (image+file = $MEDIA_TOTAL) < expected floor ($N_EXP_MEDIA)"
      else
        ok "Gate C: media blocks (image+file = $MEDIA_TOTAL) >= floor ($N_EXP_MEDIA)"
      fi
      if [ "$N_IMAGES" -lt "$N_EXP_IMAGES" ]; then
        fail "Gate C: image blocks ($N_IMAGES) < expected (slides+micros+4 = $N_EXP_IMAGES)"
      else
        ok "Gate C: image blocks ($N_IMAGES) >= slides+micros+4 ($N_EXP_IMAGES)"
      fi
      if [ "$N_FILES" -lt "$N_EXP_FILES" ]; then
        fail "Gate C: file blocks ($N_FILES) < 10 (1 .pptx + 9 PDFs)"
      else
        ok "Gate C: file blocks ($N_FILES) >= 10 (1 .pptx + 9 PDFs)"
      fi
    fi
  fi
  echo ""
fi

# ============================================================================
# VERDICT
# ============================================================================
bold "═══════════════════════════════════════════════════════════════════"
if [ "$FAILED" -ne 0 ]; then
  red " RESULT: REJECT / AUTO-FAIL — ${#REASONS[@]} condition(s) failed:"
  for r in "${REASONS[@]}"; do red "   • $r"; done
  bold "═══════════════════════════════════════════════════════════════════"
  echo ""
  exit 1
fi

green " RESULT: PASS — all applicable gates passed."
echo ""
echo "  RAW COUNTS (passing):"
echo "    module HTML / PDF          : $MOD_HTML / $MOD_PDF"
echo "    total PDFs (8+compact+DELUXE): $TOTAL_PDF"
echo "    deck slides (unzip|grep -c): $DECK_SLIDES"
echo "    slide PNG / PROMPT         : $SLIDE_PNG / $SLIDE_PROMPT"
echo "    cheatsheet PNG / PROMPT    : $CHEAT_PNG / $CHEAT_PROMPT"
echo "    micro PNG / PROMPT         : $MICRO_PNG / $MICRO_PROMPT"
echo "    dept role count (N)        : ${ROLE_N:-unknown}  (micros >= roles required)"
if [ -n "$PAGE_ID" ]; then
  echo "    Notion images / files      : ${N_IMAGES:-?} / ${N_FILES:-?}  (artifact-blocks ${N_ARTIFACT:-?}, H1 ${N_H1:-?})"
fi
bold "═══════════════════════════════════════════════════════════════════"
echo ""
exit 0
