#!/usr/bin/env bash
# test-standard-placeholder.sh - STD001 acceptance tests for apply-standard-placeholder.py
# and set-company-name.py. HERMETIC: sandbox HOME, scratch OPENCLAW root, scratch build-state,
# scratch departments dir, scratch Command Center db. Touches nothing real.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="$SCRIPT_DIR/apply-standard-placeholder.py"
RENAME="$SCRIPT_DIR/set-company-name.py"
GUARD="$SCRIPT_DIR/vertical-derivation-guard.py"
PASS=0; FAIL=0
good() { PASS=$((PASS+1)); echo "PASS: $1"; }
bad()  { FAIL=$((FAIL+1)); echo "FAIL: $1" >&2; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home"; mkdir -p "$HOME"
export STANDARD_FIRST_ONBOARDING=1
unset OPENCLAW_ROOT CC_APP_DIR
ROOT="$HOME/.openclaw"; WS="$ROOT/workspace"; STATE="$WS/.workforce-build-state.json"
COMPANY="$HOME/clawd/zero-human-company/scratch-canary"; DD="$COMPANY/departments"; CC="$TMP/cc"
mkdir -p "$WS" "$DD" "$CC"

iso_ago() { python3 -c "import datetime as d,sys;print((d.datetime.now(d.timezone.utc)-d.timedelta(hours=float(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M:%SZ'))" "$1"; }
seed() { # <state-json> <hours-since-onboarding-start|none>
  printf '%s' "$1" > "$STATE"; rm -f "$WS/.onboarding-state.json"
  [ "$2" = none ] || printf '{"seededAt":"%s"}' "$(iso_ago "$2")" > "$WS/.onboarding-state.json"
}
eng() { python3 "$ENGINE" --oc-root "$ROOT" --build-state-file "$STATE" --departments-dir "$DD" --company-dir "$COMPANY" --cc-dir "$CC" "$@"; }
jget() { python3 -c "import json,sys;d=json.load(open('$STATE'));print(eval(sys.argv[1]))" "$1"; }
DONE='"standardPrebuild":{"status":"done"}'   # skips the (slow) prebuild for the logic cases

# 1. boundary on the constant
seed "{\"ownerName\":\"Pat Lee\",$DONE}" $((13*24+1)); B="$(cat "$STATE")"
OUT="$(eng --auto --apply)"; RC=$?
[ $RC -eq 3 ] && [ "$(cat "$STATE")" = "$B" ] && echo "$OUT" | grep -q NOT_DUE && good "1a: 13 days -> NOT_DUE, state unchanged" || bad "1a: rc=$RC out=$OUT"
seed "{\"ownerName\":\"Pat Lee\",$DONE}" $((14*24+1))
OUT="$(eng --auto --apply)"; RC=$?
[ $RC -eq 0 ] && [ "$OUT" = APPLIED ] && [ "$(jget "d['companyMode']")" = standard-placeholder ] && good "1b: 14 days -> APPLIED" || bad "1b: rc=$RC out=$OUT"

# 2. ineligible states
for pair in '"interviewComplete":true|INTERVIEW_COMPLETE' '"buildCompletedAt":"2026-06-20T00:00:00Z"|BUILT_COMPANY' '"buildType":"legacy"|LEGACY_FROZEN'; do
  seed "{\"ownerName\":\"Pat Lee\",${pair%%|*}}" $((60*24)); B="$(cat "$STATE")"
  OUT="$(eng --auto --apply)"; RC=$?
  [ $RC -eq 3 ] && echo "$OUT" | grep -q "${pair##*|}" && [ "$(cat "$STATE")" = "$B" ] && good "2: ${pair##*|}" || bad "2: ${pair##*|} rc=$RC out=$OUT"
done

# 3. no owner name anywhere (USER.md naming the operator is ignored)
seed "{$DONE}" $((60*24)); echo "Name: Trevor" > "$WS/USER.md"; B="$(cat "$STATE")"
OUT="$(eng --auto --apply)"; RC=$?
[ $RC -eq 2 ] && [ "$(cat "$STATE")" = "$B" ] && good "3: no owner name -> rc 2, unchanged, USER.md ignored" || bad "3: rc=$RC out=$OUT"
rm -f "$WS/USER.md"

# 4. naming: unestablished -> owner name; established -> keeps existing name
seed "{\"ownerName\":\"Pat Lee\",\"companyName\":\"Old Biz\",$DONE}" $((60*24)); eng --auto --apply >/dev/null
[ "$(jget "d['companyName']")" = "Pat Lee" ] && [ "$(jget "d['standardPlaceholder']['priorCompanyName']")" = "Old Biz" ] \
  && good "4a: unestablished company named after owner, prior saved" || bad "4a: name=$(jget "d['companyName']")"
seed "{\"ownerName\":\"Pat Lee\",\"companyName\":\"Platinum Pearls\",\"companyId\":\"c1\",\"companySlug\":\"platinum-pearls\",$DONE}" $((60*24)); eng --auto --apply >/dev/null
[ "$(jget "d['companyName']")" = "Platinum Pearls" ] && good "4b: established company keeps its name" || bad "4b: name=$(jget "d['companyName']")"

# 6. idempotent
B="$(cat "$STATE")"; OUT="$(eng --auto --apply)"; RC=$?
[ $RC -eq 0 ] && [ "$OUT" = ALREADY_ACTIVE ] && [ "$(cat "$STATE")" = "$B" ] && good "6: re-run ALREADY_ACTIVE, byte-identical" || bad "6: rc=$RC out=$OUT"

# 8. verticalPacks: explicit empty record only when absent
seed "{\"ownerName\":\"Pat Lee\",\"verticalPacks\":{\"detectedPacks\":[\"real-estate\"]},$DONE}" $((60*24)); eng --auto --apply >/dev/null
[ "$(jget "d['verticalPacks']['detectedPacks']")" = "['real-estate']" ] && good "8a: existing verticalPacks untouched" || bad "8a"
seed "{\"ownerName\":\"Pat Lee\",$DONE}" $((60*24)); eng --auto --apply >/dev/null
[ "$(jget "d['verticalPacks']['detectedPacks']")" = "[]" ] && good "8b: absent verticalPacks -> explicit empty record" || bad "8b"

# 3/5/7/9. FULL run incl. the real library-only prebuild: forced, pinned slug, listings on disk first
rm -rf "$DD"; mkdir -p "$DD/listings/some-role"
seed '{"companySlug":"blackwoman-startup","companyName":"BlackWoman Startup","interviewComplete":false,"interviewProgress":{"lastQuestionNumber":5}}' $((91*24))
PB="$(python3 -c "import json;print(json.dumps({k:v for k,v in json.load(open('$STATE')).items() if k in ('interviewComplete','interviewProgress','interviewQc','buildCompletedAt')},sort_keys=True))")"
OUT="$(eng --force --owner-name "Pat Lee" --apply 2>"$TMP/full.err")"; RC=$?
if [ $RC -eq 0 ] && [ "$OUT" = APPLIED ]; then good "full: forced apply with real prebuild rc=0"; else bad "full: rc=$RC out=$OUT $(tail -3 "$TMP/full.err")"; fi
[ "$(jget "d['companyName']")" = "Pat Lee" ] && [ "$(jget "d['standardPrebuild']['status']")" = done ] && good "full: company named Pat Lee, prebuild done" || bad "full: name/prebuild"
[ "$(jget "d['companySlug']")" = blackwoman-startup ] && good "5: pinned slug unchanged" || bad "5: slug=$(jget "d['companySlug']")"
PA="$(python3 -c "import json;print(json.dumps({k:v for k,v in json.load(open('$STATE')).items() if k in ('interviewComplete','interviewProgress','interviewQc','buildCompletedAt')},sort_keys=True))")"
[ "$PA" = "$PB" ] && ! find "$TMP" -name 'workforce-interview-answers.md' | grep -q . && good "7: interview keys byte-identical, no answers file" || bad "7: before=$PB after=$PA"
[ "$(jget "d['standardPlaceholder']['preexistingVerticalDepartments']")" = "['listings']" ] && good "9a: listings recorded as pre-existing vertical dept" || bad "9a: $(jget "d['standardPlaceholder']['preexistingVerticalDepartments']")"
python3 "$GUARD" --departments-dir "$DD" --build-state "$STATE" >/dev/null 2>&1
[ $? -eq 0 ] && good "9b: vertical guard rc 0 with placeholder active" || bad "9b: guard failed"
[ -d "$DD/listings/some-role" ] && good "full: nothing removed (listings intact)" || bad "full: listings removed"

# set-company-name.py: dry run writes nothing; --apply updates state, config, db row, only COMPANY_NAME in .env.local
mkdir -p "$COMPANY"; echo '{"name":"Old","x":1}' > "$COMPANY/company-config.json"
python3 - "$STATE" "$COMPANY" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); s.update(companyId="c1",companyRoot=sys.argv[2]); json.dump(s,open(sys.argv[1],"w"))
PY
python3 -c "
import sqlite3;c=sqlite3.connect('$TMP/cc.db');c.execute('create table companies(id text,slug text,name text)');c.execute(\"insert into companies values('c1','blackwoman-startup','Old')\");c.commit()"
printf 'DATABASE_PATH=%s\nOTHER=keep\nCOMPANY_NAME=Old\n' "$TMP/cc.db" > "$CC/.env.local"
B="$(cat "$STATE")$(cat "$COMPANY/company-config.json")$(cat "$CC/.env.local")"
python3 "$RENAME" --build-state-file "$STATE" --cc-dir "$CC" --name "New Co" >/dev/null
[ "$B" = "$(cat "$STATE")$(cat "$COMPANY/company-config.json")$(cat "$CC/.env.local")" ] && good "rename: dry run writes nothing" || bad "rename: dry run wrote"
python3 "$RENAME" --build-state-file "$STATE" --cc-dir "$CC" --name "New Co" --apply >/dev/null; RC=$?
DBN="$(python3 -c "import sqlite3;print(sqlite3.connect('$TMP/cc.db').execute('select name from companies').fetchone()[0])")"
if [ $RC -eq 0 ] && [ "$(jget "d['companyName']")" = "New Co" ] && [ "$(jget "d['companySlug']")" = blackwoman-startup ] && [ "$DBN" = "New Co" ] \
   && grep -q '"name": "New Co"' "$COMPANY/company-config.json" && grep -q '^COMPANY_NAME=New Co$' "$CC/.env.local" && grep -q '^OTHER=keep$' "$CC/.env.local"; then
  good "rename: --apply updates state, config, db row, COMPANY_NAME only (slug untouched)"
else bad "rename: --apply rc=$RC db=$DBN"; fi
python3 "$RENAME" --build-state-file "$STATE" --name "" >/dev/null 2>&1; [ $? -eq 2 ] && good "rename: bad input rc 2" || bad "rename: bad input"

echo "=============================================="
echo "test-standard-placeholder.sh: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
