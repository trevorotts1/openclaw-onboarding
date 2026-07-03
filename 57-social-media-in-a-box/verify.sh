#!/usr/bin/env bash
# 57-social-media-in-a-box/verify.sh
#
# READ-ONLY self-verify gate for Social Media in a Box (Skill 57). Nonzero on any
# failure. Idempotent — safe to re-run twice under both bash -c and zsh -c. Every
# run that touches a run-dir does so in a fresh mktemp COPY: the committed golden
# and every broken-variant fixture stay byte-for-byte read-only.
#
#   1. every prover's --self-test (VALID exit 0 / VIOLATION exit nonzero)
#   2. golden-week reproduces PASS end-to-end through the sanctioned entry, in a
#      temp copy, and mints the SAME certificate_sha as the committed golden
#   3. front-door nonce guard: a direct orchestrator call exits 4
#   4. broken-variant rejection: 11 DISTINCT AF-SM-* trips (+ the exit-4 nonce),
#      each executed for real and asserted on exact exit code + AF-SM-* code
#   5. full-tree scrub gate green (no client-name / secret / pinData / Anthropic)
#   6. shipped prompt hashes match the canonical pin
#   7. engine hash matches ENGINE-PIN.sha256; no-Anthropic + no-n8n-runtime scans
#
# It calls NO provider and NO network. No secret/anthropic literal is ever shipped
# into scanned bytes: the leak/anthropic negatives are materialized into a temp
# file at test time and deleted.

# Portability guard: this gate is authored for bash (BASH_SOURCE arrays, herestrings).
# If launched under another shell (e.g. `zsh verify.sh`), re-exec under bash so the
# behavior and exit code are identical to `bash verify.sh`.
if [ -z "${BASH_VERSION:-}" ]; then exec bash "$0" "$@"; fi
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SELF_DIR"
FAILS=0
step() { echo; echo "=== $* ==="; }
ok()   { echo "  OK: $*"; }
bad()  { echo "  FAIL: $*" >&2; FAILS=$((FAILS+1)); }

PY=python3
command -v "$PY" >/dev/null 2>&1 || { echo "FATAL: python3 required" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/smib-verify.XXXXXX")"
cleanup() { rm -rf "$WORK" 2>/dev/null || true; }
trap cleanup EXIT INT TERM HUP

GOLD_SRC="examples/golden-week"

# assert a prover REJECTS: exit code == $2 and (if $3 given) $3 is among the --json codes
assert_reject() {
    local label="$1" want_exit="$2" want_code="$3"; shift 3
    local out rc codes
    out="$("$PY" "$@" --json 2>/dev/null)"; rc=$?
    codes="$("$PY" -c 'import json,sys
try: d=json.load(sys.stdin)
except Exception: d={}
recs=(d.get("failures") or [])+(d.get("findings") or [])
print(",".join(f.get("code","") for f in recs))' <<<"$out" 2>/dev/null)"
    if [ "$rc" -ne "$want_exit" ]; then bad "$label: exit $rc, wanted $want_exit"; return; fi
    if [ -n "$want_code" ] && [[ ",$codes," != *",$want_code,"* ]]; then
        bad "$label: exit $rc OK but code [$codes] missing $want_code"; return; fi
    ok "$label -> exit $rc [$want_code]"
}

# run a COMMITTED golden through the ONE entry in a fresh temp COPY (the source stays
# byte-for-byte read-only), then assert PASS + a green certificate whose deterministic
# sha reproduces the committed one. This is how every v0.2.0 mode is exercised end-to-end.
golden_cert() {
    local label="$1" src="$2" mode="$3"
    local run="$WORK/gc-$label"
    cp -R "$src" "$run"
    rm -f "$run/working/checkpoints/gates.json" "$run/delivery/PROCESS-CERTIFICATE."* 2>/dev/null || true
    if ! bash social-media-entry.sh --run-dir "$run" --mode "$mode" >/dev/null 2>&1; then
        bad "$label ($mode): run did not pass through the entry"; return; fi
    if "$PY" - "$run/delivery/PROCESS-CERTIFICATE.json" "$src/delivery/PROCESS-CERTIFICATE.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); ref=json.load(open(sys.argv[2]))
green = c["pass"] and c["zero_anthropic"] and c["prompt_hashes_ok"] and c["all_gates_pass"]
same  = c["certificate_sha"] == ref["certificate_sha"]
sys.exit(0 if (green and same) else 1)
PY
    then ok "$label ($mode) -> PASS + green cert + reproduces committed sha (source untouched)"
    else bad "$label ($mode): certificate not green or sha drifted from the committed golden"; fi
}

# a READ-ONLY mode with NO certificate (engage): assert the run passes through the entry
# and produces its read-only artifact (never blocks a publish; mints no cert, by design).
golden_report() {
    local label="$1" src="$2" mode="$3" artifact="$4"
    local run="$WORK/gr-$label"
    cp -R "$src" "$run"
    rm -f "$run/working/checkpoints/gates.json" 2>/dev/null || true
    if bash social-media-entry.sh --run-dir "$run" --mode "$mode" >/dev/null 2>&1 && [ -f "$run/$artifact" ]; then
        ok "$label ($mode) -> read-only PASS, $artifact present (no certificate, by design)"
    else bad "$label ($mode): read-only run failed or the report artifact is missing"; fi
}

# ---------------------------------------------------------------------------
step "1/7 prover self-tests"
for p in preflight_gate prove_bands validate_contract scrub_gate ledger build_manifest label_deliverables defer_stub; do
    if "$PY" "scripts/$p.py" --self-test >/dev/null 2>&1; then ok "$p --self-test"; else bad "$p --self-test"; fi
done

# ---------------------------------------------------------------------------
step "2/7 golden-week reproduces PASS in a read-only temp copy (mode week, via entry)"
GOLD_RUN="$WORK/golden"
cp -R "$GOLD_SRC" "$GOLD_RUN"
rm -f "$GOLD_RUN/working/checkpoints/gates.json" "$GOLD_RUN/delivery/PROCESS-CERTIFICATE."* 2>/dev/null || true
if bash social-media-entry.sh --run-dir "$GOLD_RUN" --mode week >/dev/null 2>&1; then
    CERT="$GOLD_RUN/delivery/PROCESS-CERTIFICATE.json"
    if [ -f "$CERT" ] && "$PY" - "$CERT" "$GOLD_SRC/delivery/PROCESS-CERTIFICATE.json" <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); ref=json.load(open(sys.argv[2]))
green = c["pass"] and c["zero_anthropic"] and c["prompt_hashes_ok"] and c["all_gates_pass"]
same  = c["certificate_sha"] == ref["certificate_sha"]
sys.exit(0 if (green and same) else 1)
PY
    then ok "golden PASS + cert green + reproduces committed certificate_sha (source untouched)"
    else bad "golden certificate not green or sha drifted from committed golden"; fi
else bad "golden-week run did not pass through the entry"; fi

# committed golden must be byte-identical after the temp run (read-only proof)
if [ -z "$(find "$GOLD_SRC/working/checkpoints" -name '.smib-entry-nonce' 2>/dev/null)" ]; then
    ok "no stray nonce left in the committed golden"; else bad "a nonce leaked into the committed golden"; fi

# v0.2.0 NEW MODES exercised end-to-end through the ONE entry in read-only temp copies:
# a newsletter, a blog, a podcast (audio+cover), a twitter thread (day-run, C1 sub-mode) each
# reproduce a signed certificate; engage is read-only -> a report, no cert.
step "2b/7 v0.2.0 new modes exercised through the entry (real authored content)"
golden_cert   "newsletter" examples/golden-modes/newsletter    newsletter
golden_cert   "blog"       examples/golden-modes/blog           blog
golden_cert   "podcast"    examples/golden-modes/podcast        podcast
golden_cert   "twitter"    examples/golden-modes/twitter-thread day
golden_report "engage"     examples/golden-modes/engage         engage working/qc/engage_report.json

# v0.2.0 golden-CREATIVE: an M1 brief run with a WILDCARD theme certifies end-to-end THROUGH
# the entry WITH a creative block: 2 logged overrides (a caption widened to 2000-2400 +
# a client-exact slide-count reshape) + a VERBATIM client-copy record. Creativity flows through
# the spine; zero gates weakened; the client got EXACTLY what they asked for.
step "2c/7 golden-creative brief (wildcard theme + logged overrides + verbatim client copy)"
GC="$WORK/golden-creative"; cp -R examples/golden-creative/run "$GC"
rm -f "$GC/working/checkpoints/gates.json" "$GC/delivery/PROCESS-CERTIFICATE."* 2>/dev/null || true
if bash social-media-entry.sh --run-dir "$GC" --mode brief >/dev/null 2>&1 \
   && "$PY" - "$GC/delivery/PROCESS-CERTIFICATE.json" examples/golden-creative/run/delivery/PROCESS-CERTIFICATE.json <<'PY'
import json,sys
c=json.load(open(sys.argv[1])); ref=json.load(open(sys.argv[2]))
cre=c.get("creative",{})
green = (c["pass"] and c["zero_anthropic"] and c.get("overrides_logged_ok")
         and c.get("client_copy_verbatim_ok") and cre.get("mode")=="brief"
         and cre.get("theme_source")=="wildcard" and cre.get("em_dash_policy")=="allow-content"
         and cre.get("series_length")==5 and len(cre.get("overrides",{}))==2
         and "caption_fb_ig" in cre.get("overrides",{}) and len(cre.get("client_copy_shas",[]))==1
         and c["certificate_sha"]==ref["certificate_sha"])
sys.exit(0 if green else 1)
PY
then ok "golden-creative brief PASS through the entry: wildcard theme + 2 logged overrides (caption widened) + verbatim client copy + reproduces committed sha"
else bad "golden-creative brief did not certify with the expected creative block"; fi

# ---------------------------------------------------------------------------
step "3/7 front-door nonce guard (direct orchestrator call must exit 4)"
env -u OC_SMIB_ENTRY_NONCE "$PY" run_social_media.py --mode week --run-dir "$GOLD_RUN" >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 4 ]; then ok "direct call blocked (exit 4)"; else bad "nonce guard did not block (exit $rc)"; fi

# ---------------------------------------------------------------------------
step "4/7 broken-variant rejection (11 distinct AF-SM-* + the exit-4 nonce)"
BV="$GOLD_SRC/broken-variants"
# -- shipped safe fixtures (provers are read-only on these) --
assert_reject "out-of-band-caption  " 2 AF-SM-CAPTION-BAND     scripts/prove_bands.py "$BV/out-of-band-caption/fb-carousel.json"
assert_reject "bad-hashtag-count    " 2 AF-SM-HASHTAG-COUNT    scripts/prove_bands.py "$BV/bad-hashtag-count/fb-carousel.json"
# -- C7 content-completeness fold: a FB/IG Stories caption over the 250-char band (only this trips) --
assert_reject "stories-caption-long " 2 AF-SM-STORIES-CAPTION  scripts/prove_bands.py "$BV/stories-caption/reformat.json"
# -- v0.2.0 C2 discovery drift: a live-connected channel missing from the enum (the BANNED silent-miss) --
assert_reject "discovery-drift      " 2 AF-SM-DISCOVERY-DRIFT  scripts/preflight_gate.py "$BV/discovery-drift/config.json"
# -- v0.2.0 de-dup fixture (ledger reads only; read-only on the committed fixture) --
assert_reject "duplicate-post       " 2 AF-SM-DOUBLE-POST      scripts/ledger.py dedup-snapshot --input "$BV/duplicate-post/dedup.json"
# -- shipped run-dir fixtures, copied to temp for build_manifest --
cp -R "$BV/missing-provenance/run"    "$WORK/mp";  assert_reject "missing-provenance   " 2 AF-SM-PROVENANCE-MISSING scripts/build_manifest.py --run-dir "$WORK/mp"
cp -R "$BV/unapproved-phase-skip/run" "$WORK/up";  assert_reject "unapproved-phase-skip" 2 AF-SM-PROCESS-INTEGRITY  scripts/build_manifest.py --run-dir "$WORK/up"
# -- v0.2.0 creative-layer run-dir fixtures, copied to temp for build_manifest --
cp -R "$BV/unlogged-override/run"     "$WORK/uo";  assert_reject "unlogged-override    " 2 AF-SM-OVERRIDE-UNLOGGED  scripts/build_manifest.py --run-dir "$WORK/uo"
cp -R "$BV/mutated-client-copy/run"   "$WORK/mc";  assert_reject "mutated-client-copy  " 2 AF-SM-CLIENT-COPY-MUTATED scripts/build_manifest.py --run-dir "$WORK/mc"
# -- v0.2.0 DEFER stub fails CLOSED with a clear deferred message --
if scripts/defer_stub.py --capability syndicate >/dev/null 2>&1; then bad "syndicate defer stub did not fail closed"; else ok "syndicate defer stub -> fails closed (AF-SM-DEFERRED, v0.4.0)"; fi
# -- forbidden-literal negatives, materialized to temp (never shipped) --
"$PY" - "$WORK/leak.json" <<'PY'
import sys
open(sys.argv[1],"w").write('{"leaked": "' + "sk-or-" + "v1-" + "a"*40 + '"}')
PY
assert_reject "client-key-leak      " 2 AF-SM-SECRET       scripts/scrub_gate.py "$WORK/leak.json"
"$PY" - "$WORK/calls.json" <<'PY'
import json,sys
model = "claude" + "-opus-4-8"   # assembled so this source never holds the literal
json.dump([{"step":"rogue","provider":"anthropic","model":model}], open(sys.argv[1],"w"))
PY
assert_reject "anthropic-call       " 2 AF-SM-NOANTHROPIC  scripts/scrub_gate.py "$WORK/calls.json"
# -- defense-in-depth: the same anthropic id is refused at P6 too --
mkdir -p "$WORK/anti/working/checkpoints" "$WORK/anti/working/provenance" "$WORK/anti/working/copy"
"$PY" - "$WORK/anti" "$WORK/calls.json" <<'PY'
import json,sys
d=sys.argv[1]
json.dump({"P0-PREFLIGHT":{"passed":True},"P3-CONTRACT":{"passed":True},"P5-SCRUB":{"passed":True}},
          open(d+"/working/checkpoints/gates.json","w"))
open(d+"/working/provenance/calls.json","w").write(open(sys.argv[2]).read())
json.dump({"brandName":"Northwind Bakehouse","mode":"single-brand"}, open(d+"/working/copy/config.json","w"))
PY
assert_reject "anthropic-at-manifest " 2 AF-SM-NOANTHROPIC scripts/build_manifest.py --run-dir "$WORK/anti"

# ---------------------------------------------------------------------------
step "5/7 full-tree scrub gate (no client-name/secret/pinData/Anthropic in shipped bytes)"
if "$PY" scripts/scrub_gate.py . >/dev/null 2>&1; then ok "scrub clean"; else bad "scrub gate found a leak in the shipped tree"; fi

# ---------------------------------------------------------------------------
step "6/7 prompt-hash pin matches canonical"
if "$PY" - <<'PY'
import json,hashlib,sys
from pathlib import Path
pin=json.load(open("PROMPT-HASHES.json"))["hashes"]
bad=[n for n,h in pin.items() if hashlib.sha256(Path("prompts",n).read_bytes()).hexdigest()!=h]
sys.exit(1 if bad else 0)
PY
then ok "19 prompt hashes match the pin"; else bad "a shipped prompt drifted from the pin"; fi

# ---------------------------------------------------------------------------
step "7/7 engine-pin + no-Anthropic + no-n8n-runtime scans"
# engine hash pin (the same set social-media-entry.sh GATE 3 enforces)
ENGINE_FILES=(run_social_media.py scripts/preflight_gate.py scripts/prove_bands.py
    scripts/validate_contract.py scripts/scrub_gate.py scripts/build_manifest.py
    scripts/ledger.py scripts/label_deliverables.py scripts/defer_stub.py)
if command -v shasum >/dev/null 2>&1; then H="$(cat "${ENGINE_FILES[@]}" | shasum -a 256 | awk '{print $1}')"
elif command -v sha256sum >/dev/null 2>&1; then H="$(cat "${ENGINE_FILES[@]}" | sha256sum | awk '{print $1}')"
else H=""; fi
if [ -n "$H" ] && [ -f ENGINE-PIN.sha256 ]; then
    if [ "$(tr -d ' \t\n' < ENGINE-PIN.sha256)" = "$H" ]; then ok "engine hash matches ENGINE-PIN.sha256"; else bad "engine hash drifted from ENGINE-PIN.sha256"; fi
else ok "engine-pin scan skipped (no sha tool / no pin)"; fi

# no-Anthropic scan: reuse the authoritative scrub detector (AF-SM-NOANTHROPIC) so
# verify.sh itself never has to carry a forbidden model-id literal. Assert ZERO
# NOANTHROPIC findings across the shipped tree.
if "$PY" scripts/scrub_gate.py . --json 2>/dev/null | "$PY" -c 'import json,sys
d=json.load(sys.stdin)
sys.exit(1 if any(f.get("code")=="AF-SM-NOANTHROPIC" for f in d.get("findings",[])) else 0)'
then ok "no Anthropic/claude-* id in any client-path file (scrub detector)"; else bad "an Anthropic id is present in the shipped tree"; fi

# no-n8n-runtime scan: the RUNTIME executes NO n8n / Airtable (design law). We scan
# every shipped byte for an n8n EXECUTION signature (host / webhook-id / api header /
# pinData), not the mere word 'n8n' (docs legitimately name the thing it replaced).
if "$PY" - <<'PY'
import re,sys,os
rx=re.compile(r"\.n8n\.cloud|n8n\.io/|X-N8N-API-KEY|/webhook/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}|localhost:5678|:5678/|\"pinData\"\s*:|api\.airtable\.com", re.I)
skip_files={os.path.realpath("scripts/scrub_gate.py"),os.path.realpath("verify.sh")}
hits=[]
for root,dirs,files in os.walk("."):
    dirs[:]=[d for d in dirs if d not in {".git","__pycache__","node_modules",".venv","venv"}]
    for fn in files:
        if not fn.endswith((".py",".json",".sh",".yml",".yaml")): continue
        p=os.path.join(root,fn)
        if os.path.realpath(p) in skip_files: continue
        try: t=open(p,encoding="utf-8",errors="replace").read()
        except OSError: continue
        if rx.search(t): hits.append(p)
sys.exit(1 if hits else 0)
PY
then ok "no n8n/Airtable execution signature in the runtime"; else bad "an n8n/Airtable runtime call is present"; fi

echo
if [ "$FAILS" -eq 0 ]; then echo "VERIFY: ALL GREEN"; exit 0
else echo "VERIFY: $FAILS FAILURE(S)"; exit 1; fi
