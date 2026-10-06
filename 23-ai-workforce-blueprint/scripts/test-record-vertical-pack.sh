#!/usr/bin/env bash
# test-record-vertical-pack.sh -- record-vertical-pack.py + the phase 3b guard.
# A box built before the verticalPacks record existed fails the guard closed on
# departments its owner wants. An operator-directed declaration, recorded with
# who / when / why, is the supported way to clear it: the guard then passes and
# prints the declaration on every run. Without it -- or with an entry missing
# any provenance field -- the guard still fails. Hermetic: tmp dirs only.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$SCRIPT_DIR/vertical-derivation-guard.py"
REC="$SCRIPT_DIR/record-vertical-pack.py"
PASS=0; FAIL=0
ok()  { echo "  PASS: $*"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

DD="$TMP/departments"
for d in course-creator community-management client-coaches marketing; do mkdir -p "$DD/$d/some-role"; done
ST="$TMP/.workforce-build-state.json"
printf '{"interviewComplete": true, "industry": "financial services", "departments": {"marketing": {}}, "keep": [1, 2]}\n' > "$ST"
cp "$ST" "$TMP/original.json"
guard() { python3 "$GUARD" --departments-dir "$DD" --build-state "$ST" --out "$TMP/receipt.json" --json 2>/dev/null; }
rc_of() { guard >/dev/null; echo $?; }

[ "$(rc_of)" = 3 ] && ok "no declaration record: guard fails closed (rc 3)" || bad "expected rc 3 before recording"

python3 "$REC" --pack personal-pro-dev --by "" --reason x --state "$ST" >/dev/null 2>&1 \
  && bad "empty --by accepted" || ok "empty --by refused"
python3 "$REC" --pack no-such-pack --by T --reason x --state "$ST" >/dev/null 2>&1 \
  && bad "unknown pack accepted" || ok "unknown pack refused"
python3 "$REC" --pack personal-pro-dev --by T --reason x --state "$ST" --dry-run >/dev/null \
  && cmp -s "$ST" "$TMP/original.json" && ok "dry-run changes nothing" || bad "dry-run changed the state"

python3 "$REC" --pack personal-pro-dev --by Trevor --at 2026-09-29 \
  --reason "client wants course-creator, community-management, client-coaches" --state "$ST" >/dev/null \
  && ok "recorded" || bad "record failed"
ls "$ST".bak-record-vertical-pack-* >/dev/null 2>&1 && cmp -s "$ST".bak-record-vertical-pack-* "$TMP/original.json" \
  && ok "backup is the pre-write state" || bad "no faithful backup"
python3 - "$TMP/original.json" "$ST" <<'PY' && ok "only verticalPacks changed" || bad "other build-state keys changed"
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
b.pop("verticalPacks")
e = json.load(open(sys.argv[2]))["verticalPacks"]["detectedPacks"][0]
assert a == b, "keys differ"
assert (e["pack"], e["source"], e["by"], e["at"]) == ("personal-pro-dev", "operator-directive", "Trevor", "2026-09-29"), e
PY

out="$(guard)"; rc=$?
[ "$rc" = 0 ] && ok "guard passes with the operator declaration" || bad "guard rc=$rc after recording"
case "$out" in *OPERATOR_DECLARATION:*"by Trevor on 2026-09-29"*) ok "guard prints the declaration";; *) bad "declaration not printed";; esac
python3 -c "import json,sys; r=json.load(open(sys.argv[1])); assert r['operatorDeclarations'][0]['by']=='Trevor'" "$TMP/receipt.json" \
  && ok "receipt carries operatorDeclarations" || bad "receipt missing operatorDeclarations"

cp "$ST" "$TMP/after.json"
python3 "$REC" --pack personal-pro-dev --by Trevor --reason again --state "$ST" >/dev/null \
  && cmp -s "$ST" "$TMP/after.json" && ok "re-recording is a no-op" || bad "re-record changed the state"

# A hand-written operator entry without a reason declares nothing.
python3 - "$ST" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); del s["verticalPacks"]["detectedPacks"][0]["reason"]
json.dump(s, open(sys.argv[1], "w"))
PY
[ "$(rc_of)" = 3 ] && ok "operator entry without provenance does not declare" || bad "incomplete operator entry accepted"

echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
