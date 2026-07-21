#!/usr/bin/env bash
# qc-rate-artifacts.sh — DETERMINISTIC artifact self-rating / 8.5 release step.
#
# WHY THIS EXISTS (BUG B — "8.5 self-rating gate holds artifacts"):
#   The 8.5 quality gate in run-closeout.sh (generate_rate_gate) reads
#   .qualityRatings.<key>.{score,qc,note} from state. Through v12.x the ONLY
#   thing that wrote those fields was a human/agent reading a log line that said
#   "Agent must now self-rate." In any UNATTENDED closeout (the resume cron's
#   `nohup bash run-closeout.sh`, or any non-interactive fire) nothing ever wrote
#   a rating, so .qualityRatings stayed null, every artifact was HELD with the
#   "artifact NOT YET RATED" branch, and the flow-diagram + Notion closeout docs
#   were generated but never RELEASED — held silently forever with null ratings.
#
# WHAT THIS DOES:
#   Programmatically rates ONE artifact against its QUALITY-GATE.md rubric using
#   deterministic checks (no LLM, no human required) and writes a REAL rating:
#       .qualityRatings.<key> = { score:<num>, qc:"pass"|"fail", note:"...",
#                                 ratedBy:"qc-rate-artifacts", ratedAt:"<iso>" }
#   On pass it RELEASES the artifact (score >= ZHC_QUALITY_MIN, qc=pass) so
#   generate_rate_gate lets it flow to delivery. On fail it FAILS LOUD with a
#   reason in .note and qc=fail (score below the bar) so generate_rate_gate
#   regenerates / HOLDS it. It NEVER leaves the rating null.
#
#   An agent that genuinely re-rates (higher bar / subjective polish) can still
#   OVERWRITE this rating before delivery — this is the deterministic FLOOR that
#   guarantees the gate is never blocked on a missing rating. Set
#   ZHC_DISABLE_AUTO_RATE=1 to defer entirely to a human/agent rating (legacy).
#
#   CONTENT JUDGMENT (SK1-10): the deterministic checks are a reachability/
#   existence floor, NOT a quality score. Set ZHC_ARTIFACT_JUDGE_CMD to an
#   independent judge (an LLM call that prints {"score","qc","note"}); on a floor
#   PASS its real content score REPLACES the flat floor value. Unset/broken judge
#   => the floor stands (keyless, unattended boxes stay fail-safe).
#
# USAGE:
#   qc-rate-artifacts.sh --key <org_chart|flow_diagram|celebration_video|closeout_docs> [--state <path>]
#
# EXIT CODES:
#   0  → rating written (whether pass or fail — check .qualityRatings.<key>.qc)
#   2  → could not run (missing state / jq / unknown key)
#
# The rater is conservative: a missing/empty artifact scores low (fail), a
# present-and-sane artifact that passes its class QC scores >= the bar (pass).

set -u

KEY=""
# ---- platform detection ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT=""
fi
STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT:+$OC_ROOT/workspace/.workforce-build-state.json}}"
LOG_FILE="${ZHC_LOG_FILE:-${OC_ROOT:+$OC_ROOT/workspace/.zhc-closeout.log}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZHC_QUALITY_MIN="${ZHC_QUALITY_MIN:-8.5}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key)   KEY="$2"; shift 2 ;;   # org_chart|flow_diagram|celebration_video|closeout_docs
    --state) STATE_FILE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

log() {
  local level="$1"; shift
  printf '%s [%-5s] step=qc-rate %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$*"
  if [[ -n "$LOG_FILE" ]]; then
    printf '%s [%-5s] step=qc-rate %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$*" >> "$LOG_FILE" 2>/dev/null || true
  fi
}

command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not installed"; exit 2; }
[[ -n "$STATE_FILE" && -f "$STATE_FILE" ]] || { log "ERROR" "no state file at '$STATE_FILE'"; exit 2; }
[[ -n "$KEY" ]] || { log "ERROR" "--key required (org_chart|flow_diagram|closeout_docs)"; exit 2; }

state_get() { jq -r "$1 // empty" "$STATE_FILE" 2>/dev/null; }

# SK1-10: optional INDEPENDENT content judge. The deterministic raters below are
# a reachability/existence FLOOR (does the artifact resolve, is it a non-trivial
# image/video, does the doc have its sections) — NOT a judgment of content
# quality. The flat 8.7 is that floor, not a quality claim. When
# ZHC_ARTIFACT_JUDGE_CMD is set, a floor PASS is escalated to a REAL content
# score: the judge command is run with ZHC_JUDGE_KEY, ZHC_JUDGE_STATE and
# ZHC_JUDGE_FLOOR_NOTE in its env and MUST print one JSON object
# {"score":<num>,"qc":"pass|fail","note":"..."} on stdout. Its verdict REPLACES
# the floor rating (ratedBy:"llm-judge"). If the judge is unset, errors, or
# prints nothing parseable, the deterministic floor stands — so an unattended,
# keyless box keeps its fail-safe behavior and never blocks on a missing judge.
_llm_judge() {  # <key> <floor_score> <floor_note> -> prints "score<TAB>qc<TAB>note" or nothing
  local key="$1" floor_score="$2" floor_note="$3" out
  [[ -n "${ZHC_ARTIFACT_JUDGE_CMD:-}" ]] || return 1
  out="$(ZHC_JUDGE_KEY="$key" ZHC_JUDGE_STATE="$STATE_FILE" ZHC_JUDGE_FLOOR_NOTE="$floor_note" \
         bash -c "$ZHC_ARTIFACT_JUDGE_CMD" 2>/dev/null)" || return 1
  [[ -n "$out" ]] || return 1
  printf '%s' "$out" | jq -e 'type=="object" and has("score") and has("qc")' >/dev/null 2>&1 || return 1
  local s q n
  s="$(printf '%s' "$out" | jq -r '.score')"
  q="$(printf '%s' "$out" | jq -r '.qc')"
  n="$(printf '%s' "$out" | jq -r '.note // ""')"
  [[ "$q" == "pass" || "$q" == "fail" ]] || return 1
  [[ "$s" =~ ^[0-9]+(\.[0-9]+)?$ ]] || return 1
  printf '%s\t%s\t%s' "$s" "$q" "judge: ${n:-no-note} | floor: $floor_note"
  return 0
}

# ── T0-08 / A47: MATERIALISATION IS NOT A CONTENT JUDGMENT ───────────────────
#
# THE DEFECT. `write_rating 8.7 pass "flow_diagram: image materialized (N bytes)"`
# and the HTTP-200 branch wrote 8.7/pass straight into .qualityRatings, which
# INSTRUCTIONS.md:13 and QUALITY-GATE.md define as a 1-10 RUBRIC score. A byte
# count and an HTTP response therefore cleared the 8.5 release floor with NO
# content judgment at all, and a generic or off-brand artifact became
# deliverable to a client. The durable record could not distinguish "a judge
# read this and scored it" from "the file was larger than 10KB".
#
# THE SEPARATION (this change). Materialisation may still gate ELIGIBILITY — a
# missing, tiny or dead artifact still fails, and a present one is still
# releasable, so no currently-healthy closeout newly fails. What it may no
# longer do is CLAIM a rubric score:
#
#   .qualityRatings.<key>.contentJudged  false unless an independent judge ran
#   .qualityRatings.<key>.rubricScore    null   unless an independent judge ran
#   .qualityRatings.<key>.scoreKind      "materialization-floor" | "structural-qc"
#                                        | "content-judgment"
#   .qualityRatings.<key>.basis          what was actually measured
#   .materializationChecks.<key>         the raw measurement, kept separately
#   .contentJudgeMissing                 every key released without a judge
#
# `score` remains the ELIGIBILITY value the gate in run-closeout.sh reads. It is
# no longer presented as a rubric score when contentJudged is false.
#
# VISIBLY REPORTED, NEVER SILENT. Releasing without a content judge now logs a
# WARN naming the key and records it in .contentJudgeMissing, so an unattended
# box's missing judgment is countable instead of invisible.
#
# B15 (NOT enabled here). Making an absent judge a HARD FAILURE would fail every
# unattended closeout until a judge is configured, which is a live-fleet blast
# radius that must be measured first. It ships as OFF-BY-DEFAULT opt-in:
# ZHC_REQUIRE_CONTENT_JUDGE=1. Default 0 = today's behaviour exactly.
ZHC_REQUIRE_CONTENT_JUDGE="${ZHC_REQUIRE_CONTENT_JUDGE:-0}"

# write_materialization <materialized:true|false> <detail>
# Records WHAT WAS MEASURED, separately from any verdict about content.
write_materialization() {
  local materialized="$1" detail="$2" tmp
  tmp=$(mktemp)
  if jq \
      --arg k "$KEY" \
      --argjson m "$materialized" \
      --arg d "$detail" \
      --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '.materializationChecks = (.materializationChecks // {}) |
       .materializationChecks[$k] = {materialized:$m, detail:$d,
                                     checkedBy:"qc-rate-artifacts", checkedAt:$at}' \
      "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "failed to write .materializationChecks.$KEY"
  fi
}

# write_rating <score> <qc:pass|fail> <note> [basis-kind]
#   basis-kind: materialization-floor (default) | structural-qc
write_rating() {
  local score="$1" qc="$2" note="$3" score_kind="${4:-materialization-floor}" tmp
  # SK1-10: on a deterministic PASS, let an independent judge (if configured)
  # replace the floor with a real content score. A judge FAIL downgrades; a judge
  # PASS carries the judge's actual score. Absent/broken judge => floor stands.
  local rated_by="qc-rate-artifacts"
  local content_judged="false"
  local rubric_score="null"
  local basis="$score_kind: $note"
  if [[ "$qc" == "pass" ]]; then
    local verdict
    if verdict="$(_llm_judge "$KEY" "$score" "$note")"; then
      score="${verdict%%$'\t'*}"
      local _rest="${verdict#*$'\t'}"
      qc="${_rest%%$'\t'*}"
      note="${_rest#*$'\t'}"
      rated_by="llm-judge"
      content_judged="true"
      rubric_score="$score"
      score_kind="content-judgment"
      log "INFO" "LLM judge scored $KEY: score=$score qc=$qc"
    fi
  fi

  # A PASS with no content judgment is releasable but must never look judged.
  if [[ "$qc" == "pass" && "$content_judged" == "false" ]]; then
    if [[ "$ZHC_REQUIRE_CONTENT_JUDGE" == "1" ]]; then
      # B15 opt-in. OFF by default; enabling it is a fleet decision.
      log "ERROR" "ZHC_REQUIRE_CONTENT_JUDGE=1 and no content judge produced a verdict for $KEY — refusing to release on a $score_kind alone"
      qc="fail"; score="5.0"
      note="content judge required (ZHC_REQUIRE_CONTENT_JUDGE=1) but ZHC_ARTIFACT_JUDGE_CMD produced no verdict; $score_kind only: $note"
    else
      log "WARN" "NO CONTENT JUDGMENT for $KEY — releasing on a $score_kind alone (ZHC_ARTIFACT_JUDGE_CMD unset or produced no verdict). score=$score is an ELIGIBILITY floor, NOT a rubric score."
    fi
  fi

  tmp=$(mktemp)
  if jq \
      --arg k "$KEY" \
      --argjson score "$score" \
      --arg qc "$qc" \
      --arg note "$note" \
      --arg rb "$rated_by" \
      --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --argjson cj "$content_judged" \
      --argjson rs "$rubric_score" \
      --arg sk "$score_kind" \
      --arg basis "$basis" \
      '.qualityRatings = (.qualityRatings // {}) |
       .qualityRatings[$k] = {score:$score, qc:$qc, note:$note, ratedBy:$rb, ratedAt:$at,
                              contentJudged:$cj, rubricScore:$rs, scoreKind:$sk, basis:$basis} |
       .contentJudgeMissing = (
         if ($cj|not) and $qc == "pass"
         then (((.contentJudgeMissing // []) + [$k]) | unique)
         else ((.contentJudgeMissing // []) - [$k]) end)' \
      "$STATE_FILE" > "$tmp"; then
    mv "$tmp" "$STATE_FILE"
  else
    rm -f "$tmp"
    log "ERROR" "failed to write .qualityRatings.$KEY"
    return 2
  fi
  if [[ "$qc" == "pass" ]]; then
    if [[ "$content_judged" == "true" ]]; then
      log "INFO" "RELEASED $KEY: CONTENT-JUDGED score=$score qc=$qc (>= $ZHC_QUALITY_MIN) — $note"
    else
      log "INFO" "RELEASED $KEY: eligibility floor $score ($score_kind), NOT content-judged — $note"
    fi
  else
    log "ERROR" "FAILED $KEY: score=$score qc=$qc — $note (run-closeout will regenerate or HOLD; never silent-null)"
  fi
  return 0
}

if [[ "${ZHC_DISABLE_AUTO_RATE:-0}" == "1" ]]; then
  log "INFO" "ZHC_DISABLE_AUTO_RATE=1 — deferring to human/agent rating (no deterministic floor written)"
  exit 0
fi

# ----------------------------------------------------------------------
# FIX-S36-04: remote-asset REACHABILITY floor.
#   Before v12.14.x the raters PASSED any well-formed http(s) URL at 8.7 with
#   ZERO reachability — a 404'd / expired KIE URL scored 8.7/pass on the
#   unattended cron path and shipped a dead link to the client. This helper
#   turns the remote-URL branch into a real (still deterministic, no-LLM) floor:
#   an HTTP HEAD must return 200 + the expected content-type family + a
#   Content-Length above a minimum before the artifact may pass.
#
# remote_asset_reachable <url> <type-prefix e.g. image/> <min_bytes>
#   stdout: a short "HTTP <code>, type=<t>, len=<n>" detail string
#   return: 0 = reachable & valid   (200 + type match + size > min)
#           1 = reached but INVALID (non-200 / wrong type / too small / no size)
#           2 = COULD NOT verify    (no curl and no override, or transport error)
# Testable offline: set ZHC_ASSET_HEAD_CMD to a command that prints canned HEAD
# response headers ($ZHC_ASSET_HEAD_URL holds the requested URL) — used so the
# unit test can exercise the 200/404/tiny/type paths without live network.
remote_asset_reachable() {
  local url="$1" type_prefix="$2" min_bytes="$3"
  local headers status ctype clen detail
  if [[ -n "${ZHC_ASSET_HEAD_CMD:-}" ]]; then
    headers="$(ZHC_ASSET_HEAD_URL="$url" bash -c "$ZHC_ASSET_HEAD_CMD" 2>/dev/null)" || headers=""
  elif command -v curl >/dev/null 2>&1; then
    headers="$(curl -sSIL -m 8 "$url" 2>/dev/null)" || headers=""
  else
    echo "no curl available and no ZHC_ASSET_HEAD_CMD override"; return 2
  fi
  if [[ -z "$headers" ]]; then
    echo "no HEAD response (transport error / timeout)"; return 2
  fi
  status="$(printf '%s\n' "$headers" | grep -iE '^HTTP/' | tail -1 | awk '{print $2}' | tr -d '\r')"
  ctype="$(printf '%s\n' "$headers" | grep -iE '^content-type:' | tail -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '\r' | tr 'A-Z' 'a-z')"
  clen="$(printf '%s\n' "$headers" | grep -iE '^content-length:' | tail -1 | awk '{print $2}' | tr -d '\r')"
  detail="HTTP ${status:-?}, type=${ctype:-?}, len=${clen:-?}"
  [[ "$status" == 2* ]] || { echo "$detail (not a 2xx status)"; return 1; }
  case "$ctype" in
    "${type_prefix}"*) : ;;
    *) echo "$detail (content-type not ${type_prefix}*)"; return 1 ;;
  esac
  if [[ -n "$clen" && "$clen" =~ ^[0-9]+$ ]]; then
    if (( clen <= min_bytes )); then
      echo "$detail (Content-Length <= ${min_bytes}B — error/placeholder page)"; return 1
    fi
  else
    echo "$detail (no numeric Content-Length — cannot confirm size floor)"; return 1
  fi
  echo "$detail"; return 0
}

# ----------------------------------------------------------------------
# Per-class deterministic raters. Each returns by calling write_rating.
# Scores: PASS = 8.7 (just over the 8.5 bar — a deterministic floor, NOT a
# claim of perfection; an agent may overwrite higher). FAIL = a sub-bar score.
# ----------------------------------------------------------------------
rate_org_chart() {
  local url html_path img_path
  url=$(state_get '.infographic1Url')
  if [[ -z "$url" || "$url" == "null" ]]; then
    write_materialization false "org_chart: infographic1Url missing"
    write_rating 2.0 fail "org_chart: infographic1Url missing — no artifact to rate"; return
  fi
  img_path=$(state_get '.infographic1LocalPath')
  # Derive the html sibling of the rendered png when present.
  html_path=""
  [[ -n "$img_path" ]] && html_path="${img_path%.png}.html"
  # If url is a file:// path and we still have no html, derive from it.
  if [[ -z "$html_path" && "$url" == file://* ]]; then
    local p="${url#file://}"; html_path="${p%.png}.html"
  fi

  # The HARD requirement is the connector-tree (the #1 rubric item). Reuse the
  # existing programmatic QC. If it cannot run (no html), score conservatively.
  local qc_script="${ZHC_ORGCHART_QC_SCRIPT:-$SCRIPT_DIR/qc-assert-org-chart-connector-tree.sh}"
  if [[ ( -f "$qc_script" ) && -n "$html_path" && -f "$html_path" ]]; then
    local rc=0
    ZHC_STATE_FILE="$STATE_FILE" ZHC_LOG_FILE="$LOG_FILE" \
      bash "$qc_script" --html-path "$html_path" ${img_path:+--image-path "$img_path"} >>"${LOG_FILE:-/dev/null}" 2>&1 || rc=$?
    case "$rc" in
      0) write_materialization true "org_chart: connector-tree QC passed on $html_path"
         write_rating 9.0 pass "org_chart: connector-tree QC passed (Owner→CEO→clusters→depts; no card-grid)" structural-qc; return ;;
      1) write_rating 6.0 fail "org_chart: connector-tree QC FAILED (card-grid anti-pattern or connectors absent, rc=1)"; return ;;
      3) write_rating 4.0 fail "org_chart: NO rendered artifact (Playwright/Chromium missing, rc=3)"; return ;;
      *) write_rating 5.0 fail "org_chart: connector-tree QC could not run (rc=$rc)"; return ;;
    esac
  fi
  # No HTML to inspect but a URL exists: cannot prove connector-tree → fail loud.
  write_rating 5.0 fail "org_chart: infographic1Url set ($url) but no inspectable HTML at '${html_path:-unknown}' — cannot confirm connector-tree; HOLD"
}

rate_flow_diagram() {
  local url
  url=$(state_get '.infographic2Url')
  if [[ -z "$url" || "$url" == "null" ]]; then
    write_materialization false "flow_diagram: infographic2Url missing"
    write_rating 2.0 fail "flow_diagram: infographic2Url missing — no artifact to rate"; return
  fi
  # The flow diagram is an AI image (KIE.AI). We cannot grade aesthetics
  # deterministically, but we CAN assert the artifact actually materialized:
  #   - a usable URL/path is present, AND
  #   - if it is a local file, the file exists and is a non-trivial image
  #     (> 1 KB rules out an empty/error placeholder).
  local local_path=""
  local_path=$(state_get '.infographic2LocalPath')
  [[ -z "$local_path" && "$url" == file://* ]] && local_path="${url#file://}"
  if [[ -n "$local_path" && -f "$local_path" ]]; then
    local sz
    sz=$(wc -c < "$local_path" 2>/dev/null | tr -d '[:space:]')
    if [[ -z "$sz" || "$sz" -lt 1024 ]]; then
      write_rating 4.0 fail "flow_diagram: local file '$local_path' is ${sz:-0} bytes (< 1KB) — empty/error placeholder, not a real image"; return
    fi
    write_materialization true "flow_diagram: local image $sz bytes at $local_path"
    write_rating 8.7 pass "flow_diagram: image materialized ($sz bytes at $local_path); URL present — MATERIALISATION ONLY, no content judgment" materialization-floor; return
  fi
  if [[ "$url" =~ ^https?:// ]]; then
    # FIX-S36-04: a well-formed URL is NOT enough — HEAD it and require a live
    # 200 + image/* + a non-trivial Content-Length before releasing, so a 404'd
    # or expired KIE link can never score 8.7/pass on the unattended cron path.
    local detail rc
    detail="$(remote_asset_reachable "$url" "image/" 10240)"; rc=$?
    case "$rc" in
      0) write_materialization true "flow_diagram: remote image reachable ($detail) at $url"
         write_rating 8.7 pass "flow_diagram: remote image URL reachable ($detail) — MATERIALISATION ONLY, no content judgment; $url" materialization-floor; return ;;
      1) write_rating 4.0 fail "flow_diagram: remote image URL UNREACHABLE/invalid ($detail) at $url — dead or non-image link, HOLD"; return ;;
      *) write_rating 5.0 fail "flow_diagram: could not verify remote image URL ($detail) at $url — no reachability proof, HOLD (fail-closed)"; return ;;
    esac
  fi
  write_rating 5.0 fail "flow_diagram: infographic2Url='$url' is neither a reachable local file nor an http(s) URL — cannot confirm artifact"
}

# FIX-S36-03: deterministic rater for the celebration video. Before this the
# video ran through run_step with NO rate gate at all — a garbled/dead-link
# video shipped "8.5-certified" without any check. Same conservative floor as
# the image raters: a present, non-trivial video CONTAINER (local file > 10KB
# with a video extension, OR a remote URL that HEADs 200 + video/* + size) is a
# deterministic PASS; anything missing/tiny/unreachable FAILS loud.
rate_celebration_video() {
  local url local_path
  # Prefer the GHL public URL (what the client actually receives), fall back to
  # the raw KIE/Veo result URL.
  url=$(state_get '.ghlVideoPublicUrl')
  [[ -z "$url" || "$url" == "null" ]] && url=$(state_get '.celebrationVideoUrl')
  if [[ -z "$url" || "$url" == "null" ]]; then
    write_materialization false "celebration_video: no url in state"
    write_rating 2.0 fail "celebration_video: no ghlVideoPublicUrl/celebrationVideoUrl — no video to rate"; return
  fi

  local_path=$(state_get '.celebrationVideoLocalPath')
  [[ -z "$local_path" && "$url" == file://* ]] && local_path="${url#file://}"

  # Local file present: verify it is a non-trivial video container.
  if [[ -n "$local_path" && -f "$local_path" ]]; then
    local sz ext
    sz=$(wc -c < "$local_path" 2>/dev/null | tr -d '[:space:]')
    ext="${local_path##*.}"; ext="$(printf '%s' "$ext" | tr 'A-Z' 'a-z')"
    case "$ext" in
      mp4|mov|webm|m4v|mkv) : ;;
      *) write_rating 4.0 fail "celebration_video: local file '$local_path' is not a known video container (.$ext) — cannot confirm a real video"; return ;;
    esac
    if [[ -z "$sz" || "$sz" -lt 10240 ]]; then
      write_rating 4.0 fail "celebration_video: local file '$local_path' is ${sz:-0} bytes (< 10KB) — empty/error placeholder, not a real video"; return
    fi
    write_materialization true "celebration_video: local video $sz bytes, .$ext at $local_path"
    write_rating 8.7 pass "celebration_video: video materialized ($sz bytes, .$ext at $local_path) — MATERIALISATION ONLY, no content judgment" materialization-floor; return
  fi

  # No usable local file: the client link is remote. HEAD it (FIX-S36-04 floor).
  if [[ "$url" =~ ^https?:// ]]; then
    local detail rc
    detail="$(remote_asset_reachable "$url" "video/" 10240)"; rc=$?
    case "$rc" in
      0) write_materialization true "celebration_video: remote video reachable ($detail) at $url"
         write_rating 8.7 pass "celebration_video: remote video URL reachable ($detail) — MATERIALISATION ONLY, no content judgment; $url" materialization-floor; return ;;
      1) write_rating 4.0 fail "celebration_video: remote video URL UNREACHABLE/invalid ($detail) at $url — dead or non-video link, HOLD"; return ;;
      *) write_rating 5.0 fail "celebration_video: could not verify remote video URL ($detail) at $url — no reachability proof, HOLD (fail-closed)"; return ;;
    esac
  fi
  write_rating 5.0 fail "celebration_video: url='$url' is neither a reachable local video file nor an http(s) URL — cannot confirm artifact"
}

rate_closeout_docs() {
  local url page_id
  url=$(state_get '.notionRootPageUrl')
  page_id=$(state_get '.notionCloseoutPageId')
  if [[ -z "$url" || "$url" == "null" ]]; then
    write_materialization false "closeout_docs: notionRootPageUrl missing"
    write_rating 2.0 fail "closeout_docs: notionRootPageUrl missing — no Notion doc to rate"; return
  fi
  # The Docs rubric's load-bearing requirement is the 9 doctrine sections. The
  # notion builder records its per-leg status in .closeoutLegStatus.notion.
  local leg
  leg=$(state_get '.closeoutLegStatus.notion')
  if [[ "$leg" == failed:* ]]; then
    write_rating 4.0 fail "closeout_docs: notion leg recorded failure ($leg)"; return
  fi
  # Section completeness: the builder writes notionSectionsCreated when it can.
  local secs
  secs=$(state_get '.notionSectionsCreated')
  if [[ -n "$secs" && "$secs" =~ ^[0-9]+$ ]]; then
    if (( secs >= 9 )); then
      write_materialization true "closeout_docs: $secs/9 doctrine sections created"
      write_rating 8.7 pass "closeout_docs: notion root present + $secs/9 doctrine sections created" structural-qc; return
    fi
    write_rating 6.5 fail "closeout_docs: only $secs/9 doctrine sections created — incomplete doc, HOLD"; return
  fi
  # No section counter (older notion builder) but the leg passed and a root URL
  # exists: accept as the deterministic floor (the notion builder's own
  # idempotent section reconciliation is the substance guarantee).
  if [[ "$leg" == "pass" || "$url" =~ ^https?://(www\.)?notion\.so ]]; then
    write_materialization true "closeout_docs: notion root URL present ($url); leg=${leg:-unset}"
    write_rating 8.7 pass "closeout_docs: notion root URL present ($url); leg=${leg:-unset} — MATERIALISATION ONLY, no section count, no content judgment" materialization-floor; return
  fi
  write_rating 5.0 fail "closeout_docs: notionRootPageUrl='$url' does not look like a Notion page and leg status is '${leg:-unset}' — cannot confirm"
}

case "$KEY" in
  org_chart)          rate_org_chart ;;
  flow_diagram)       rate_flow_diagram ;;
  celebration_video)  rate_celebration_video ;;
  closeout_docs)      rate_closeout_docs ;;
  *) log "ERROR" "unknown --key '$KEY' (expected org_chart|flow_diagram|celebration_video|closeout_docs)"; exit 2 ;;
esac

exit 0
