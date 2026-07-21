#!/usr/bin/env bash
# tests/unit/cinematic-forge-delivery-gate.test.sh
#
# Acceptance tests for T0-46, T0-47, T0-48, T2-29 and T2-30 (SK1-32, Skill 28).
#
#   T0-46  The output gate's contract was "safe to deliver", and EVERY argument
#          it compared against was supplied by its caller. A correctly encoded
#          video of the wrong length, the wrong aspect ratio, or missing every
#          requested overlay passed, because the caller passed in the numbers it
#          wanted checked.
#   T0-47  Captions were written to final_video_captioned.mp4 and the logo to
#          final_video_branded.mp4 — and the upload read final_video.mp4. The
#          work was performed correctly, verified correctly, and the
#          un-transformed file shipped, with every stage reporting success.
#   T0-48  The hosted check was a ranged first-byte request plus a content-type
#          match on a URL grepped out of the response body. Any reachable video
#          URL satisfied it.
#   T2-29  The documented hosting fallback for the FINAL VIDEO was an image-only
#          host, and the checklist marked that answer correct.
#   T2-30  The documented install directory (unprefixed) and the runtime helper
#          path (prefixed) could not both be right.
#
# Real ffmpeg-generated fixtures; no network, no credentials, no fleet box.
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL="$REPO_ROOT/28-cinematic-forge"
QC="$SKILL/qc-output.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== cinematic-forge-delivery-gate.test.sh ==="
echo ""

for dep in ffmpeg ffprobe jq; do
  command -v "$dep" >/dev/null 2>&1 || { echo "SKIP-IMPOSSIBLE: $dep is required to run this suite"; exit 1; }
done
[ -f "$QC" ] || { echo "FAIL: $QC not found"; exit 1; }

W="$(mktemp -d)"
trap 'rm -rf "$W" 2>/dev/null || true' EXIT

_sha() { shasum -a 256 "$1" 2>/dev/null | awk '{print $1}' || sha256sum "$1" | awk '{print $1}'; }

# Two real clips: the approved 9:16 shape, and a 16:9 one of the same length.
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:duration=2" \
  -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$W/vertical.mp4" >/dev/null 2>&1
ffmpeg -y -f lavfi -i "color=c=black:size=1920x1080:rate=30" -f lavfi -i "sine=frequency=440:duration=2" \
  -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$W/horizontal.mp4" >/dev/null 2>&1
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -t 2 "$W/silent.mp4" >/dev/null 2>&1
ffmpeg -y -f lavfi -i "color=c=black:size=1080x1920:rate=30" -f lavfi -i "sine=frequency=440:duration=5" \
  -t 5 -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$W/toolong.mp4" >/dev/null 2>&1

cat > "$W/reqs.json" <<JSON
{"approval_ref":"test-approved-2026-07-21T00:00:00Z","aspect_ratio":"9:16",
 "dimensions":"1080x1920","duration_seconds":2,"duration_tolerance_seconds":0.75,
 "requires_captions":true,"requires_logo":true}
JSON

# ===========================================================================
echo "--- T0-46: the technical mode cannot issue a delivery verdict ---"
OUT="$(bash "$QC" "$W/vertical.mp4" 2 1080x1920 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && pass "technical mode passes a valid clip (exit 0)" \
  || { fail "technical mode rejected a valid clip (exit $rc)"; printf '%s\n' "$OUT" | sed 's/^/      /'; }
printf '%s' "$OUT" | grep -q "NOT a delivery verdict" \
  && pass "technical mode states it is NOT a delivery verdict" \
  || fail "technical mode still implies the file is safe to deliver"
printf '%s' "$OUT" | grep -qi "safe to deliver" \
  && fail "technical mode printed 'safe to deliver'" \
  || pass "the phrase 'safe to deliver' appears only in the delivery mode"
bash "$QC" "$W/silent.mp4" 2 1080x1920 >/dev/null 2>&1 \
  && fail "a silent clip passed the technical mode" \
  || pass "a silent clip still fails the technical mode (exit 1)"

echo ""
echo "--- T0-46: the delivery mode refuses to certify without an approved record ---"
bash "$QC" --artifact "$W/vertical.mp4" >/dev/null 2>&1
[ $? -eq 2 ] && pass "delivery mode without --requirements is a usage failure (exit 2)" \
  || fail "delivery mode certified something with no requirements record"
printf '%s' '{"dimensions":"1080x1920","duration_seconds":2}' > "$W/no-approval.json"
bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/no-approval.json" >/dev/null 2>&1 \
  && fail "a requirements record with no approval reference was accepted" \
  || pass "a requirements record with no approval reference is refused"

echo ""
echo "--- T0-46: a request-WRONG but technically valid file is refused ---"
mkdir -p "$W/receipts"
SHA_H="$(_sha "$W/horizontal.mp4")"
for step in captions logo; do
  printf '{"step":"%s","output":"%s","output_sha256":"%s"}\n' "$step" "$W/horizontal.mp4" "$SHA_H" > "$W/receipts/$step.json"
done
# The 16:9 file is a perfectly valid video, fully receipted — and the WRONG shape.
bash "$QC" --artifact "$W/horizontal.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts" >/dev/null 2>&1 \
  && fail "a 16:9 file passed against an approved 9:16 requirement" \
  || pass "the approved aspect ratio/dimensions are enforced against the artifact"
# ...and the technical mode, given the caller's own numbers, happily passes it —
# which is precisely the defect T0-46 describes.
bash "$QC" "$W/horizontal.mp4" 2 1920x1080 >/dev/null 2>&1 \
  && pass "the same wrong-shape file passes TECHNICAL checks on caller-supplied numbers (the defect, now scoped to a non-delivery verdict)" \
  || fail "the technical mode could not reproduce the caller-supplied-numbers path"

SHA_L="$(_sha "$W/toolong.mp4")"
mkdir -p "$W/receipts-long"
for step in captions logo; do
  printf '{"step":"%s","output":"%s","output_sha256":"%s"}\n' "$step" "$W/toolong.mp4" "$SHA_L" > "$W/receipts-long/$step.json"
done
bash "$QC" --artifact "$W/toolong.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-long" >/dev/null 2>&1 \
  && fail "a 5s file passed against an approved 2s duration" \
  || pass "the approved duration is enforced against the artifact"

echo ""
echo "--- T0-47: an un-transformed artifact cannot be certified ---"
rm -rf "$W/receipts-none"; mkdir -p "$W/receipts-none"
OUT="$(bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-none" 2>&1)"
[ $? -ne 0 ] && pass "a requested transformation with no receipt FAILS the gate" \
  || fail "the un-transformed file was certified"
printf '%s' "$OUT" | grep -q "captions" \
  && pass "the failure names the missing transformation" \
  || fail "the failure does not say which transformation is missing"

echo "--- T0-47: a receipt for a DIFFERENT file cannot certify this one ---"
rm -rf "$W/receipts-other"; mkdir -p "$W/receipts-other"
for step in captions logo; do
  printf '{"step":"%s","output":"%s","output_sha256":"%s"}\n' "$step" "$W/horizontal.mp4" "$SHA_H" > "$W/receipts-other/$step.json"
done
bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-other" >/dev/null 2>&1 \
  && fail "a receipt whose output is a DIFFERENT file certified this artifact" \
  || pass "the receipt chain must END at the artifact being delivered"

echo "--- T0-47: the correctly transformed artifact PASSES (anti-false-positive) ---"
rm -rf "$W/receipts-ok"; mkdir -p "$W/receipts-ok"
SHA_V="$(_sha "$W/vertical.mp4")"
printf '{"step":"captions","output":"%s","output_sha256":"%s"}\n' "$W/vertical.mp4" "$SHA_V" > "$W/receipts-ok/captions.json"
printf '{"step":"logo","output":"%s","output_sha256":"%s"}\n' "$W/vertical.mp4" "$SHA_V" > "$W/receipts-ok/logo.json"
OUT="$(bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-ok" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ] && printf '%s' "$OUT" | grep -q "Safe to deliver"; then
  pass "a fully receipted, requirement-matching artifact is certified safe to deliver"
else
  fail "the correct artifact was rejected (exit $rc)"; printf '%s\n' "$OUT" | sed 's/^/      /'
fi

echo "--- T0-47: with NO overlays requested, no receipts are needed ---"
printf '%s' '{"approval_ref":"t","dimensions":"1080x1920","duration_seconds":2}' > "$W/reqs-plain.json"
bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs-plain.json" --receipts "$W/receipts-none" >/dev/null 2>&1 \
  && pass "a deliverable with no requested transformations passes without receipts" \
  || fail "a plain deliverable was rejected for missing receipts it never needed"

echo ""
echo "--- T0-48: the hosted check is bound to the returned asset identifier ---"
printf '%s' '{"url":"https://cdn.example.invalid/some/other/asset.mp4"}' > "$W/resp-no-id.json"
OUT="$(bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-ok" \
        --upload-response "$W/resp-no-id.json" 2>&1)"
[ $? -ne 0 ] && pass "an upload response with NO asset identifier fails the hosted check" \
  || fail "a URL with no asset identifier satisfied the hosted check"
printf '%s' "$OUT" | grep -q "asset identifier" \
  && pass "the failure says the response carries no asset identifier" \
  || fail "the failure does not explain what is missing"

printf '{"fileId":"asset-123","url":"file://%s","name":"%s","size":%s}' \
  "$W/horizontal.mp4" "$(basename "$W/horizontal.mp4")" "$(wc -c < "$W/horizontal.mp4" | tr -d ' ')" > "$W/resp-mismatch.json"
OUT="$(bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-ok" \
        --upload-response "$W/resp-mismatch.json" 2>&1)"
[ $? -ne 0 ] && pass "an asset whose filename does not match the artifact fails the hosted check" \
  || fail "a DIFFERENT hosted asset satisfied the hosted check"

printf '{"fileId":"asset-123","url":"https://cdn.example.invalid/x.mp4"}' > "$W/resp-nometa.json"
bash "$QC" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-ok" \
  --upload-response "$W/resp-nometa.json" >/dev/null 2>&1 \
  && fail "an upload response with no filename or size was accepted" \
  || pass "an upload response that carries nothing to match against is refused, not skipped"

echo ""
echo "--- MUTATION: remove the receipt requirement, and the un-transformed file ships again ---"
MUT="$W/qc-output.MUTATED.sh"
python3 - "$QC" "$MUT" <<'MUTPY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
# Revert to the pre-fix behaviour: the gate no longer requires a receipt chain,
# so an artifact that skipped every requested transformation is certified again.
start = s.index("ART_SHA=\"$(_sha256 \"$ARTIFACT\")\"")
end = s.index("# ── hosted verification")
open(dst, "w").write(s[:start] + 'ART_SHA="$(_sha256 "$ARTIFACT")"\n\n' + s[end:])
MUTPY
bash "$MUT" --artifact "$W/vertical.mp4" --requirements "$W/reqs.json" --receipts "$W/receipts-none" >/dev/null 2>&1 \
  && pass "MUTATION: without the receipt chain the un-transformed artifact is certified again — the T0-47 assertions are discriminating" \
  || fail "MUTATION: the mutated gate still refused — the mutation harness is broken"

echo ""
echo "--- T2-29: no document names the image host as the FINAL-VIDEO fallback ---"
for f in INSTALL.md QC.md SKILL.md; do
  P="$SKILL/$f"
  BAD=0
  while IFS= read -r line; do
    case "$line" in
      *[Ii]mg[Bb][Bb]*)
        case "$line" in
          *"reference"*|*"REFERENCE"*|*"still image"*|*"NOT imgBB"*|*"Never imgBB"*|*"not host"*|*"cannot host"*|*"does not satisfy"*|*"points the final-video fallback at imgBB"*) ;;
          *) echo "      unqualified imgBB mention in $f: $line"; BAD=1 ;;
        esac ;;
    esac
  done < "$P"
  [ "$BAD" -eq 0 ] && pass "T2-29: every imgBB mention in $f is qualified as reference-images-only" \
    || fail "T2-29: $f still presents imgBB without saying it cannot host the video"
done

echo ""
echo "--- T2-30: one canonical, PREFIXED skill directory everywhere ---"
for f in INSTALL.md QC.md SKILL.md; do
  if grep -q "skills/cinematic-forge" "$SKILL/$f"; then
    fail "T2-30: $f still names the unprefixed skills/cinematic-forge directory"
  else
    pass "T2-30: $f names only the prefixed 28-cinematic-forge directory"
  fi
done
grep -q "28-cinematic-forge" "$SKILL/INSTALL.md" \
  && pass "T2-30: INSTALL.md directs the operator to the prefixed directory" \
  || fail "T2-30: INSTALL.md does not name the prefixed directory at all"

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: the cinematic-forge delivery gate certifies the requested artifact"
exit 0
