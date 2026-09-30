#!/usr/bin/env bash
# tests/unit/mc-route-existing-mode.test.sh
#
# JEV-601 — the JEV-592 acceptance run found 757 of 984 extra cards came from
# existing-task messages: models ran `mc-route.sh status <task>` / `stop <task>`,
# and mc-route.sh took ANY first word as a department, so each made a card.
#
# This drives the REAL scripts/mc-route.sh against a fake Command Center (a stub
# `curl` that serves /api/workspaces, /api/tasks, /api/tasks/<id>,
# /api/tasks/<id>/messages, /api/tasks/<id>/archive and /api/tasks/ingest from
# JSON files and logs every call).
#
# Cases:
#   (a) existing status: prints the card's status, makes only GET calls, no card.
#   (b) existing status by id, and by a fuzzy title.
#   (c) existing update: adds the owner's note to that card, no card.
#   (d) existing cancel: archives that card (+ an owner note), no card; a second cancel
#       by id finds the archived card and changes nothing.
#   (e) no match / several matches: exit 3, nothing written.
#   (f) unknown first words ('status' without 'existing', 'stop', 'check', 'list',
#       a department the board does not have, no args) create nothing and exit non-zero.
#   (g) a real department still routes; a name/"dept-" alias is sent as the board's slug.
#   (h) task mode is unchanged: one ingest POST, no department check.
#   (i) CC down while checking a department: exit 1, nothing created.
#
# FAIL-FIRST: on origin/main (v25.2.20) 'existing' and every unknown word are taken
# as a department slug, so (a)-(f) each POST a card to ingest.

set -uo pipefail

PASS=0
FAIL=0
ERRORS=()
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); ERRORS+=("$1"); }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MC_ROUTE="$REPO_ROOT/scripts/mc-route.sh"
[ -f "$MC_ROUTE" ] || { echo "  FAIL: $MC_ROUTE not found"; exit 1; }

echo ""
echo "=== mc-route.sh existing mode + first-word check (JEV-601) ==="
echo ""

WORK="$(mktemp -d "${TMPDIR:-/tmp}/mc-route-existing-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/bin" "$WORK/home" "$WORK/state"

cat > "$WORK/bin/curl" <<'STUB'
#!/usr/bin/env python3
# Fake Command Center. Prints "body\n<http code>" like the real helper's -w format.
import json, os, re, sys
d = os.environ["STUB_DIR"]
args = sys.argv[1:]
method = args[args.index("-X") + 1] if "-X" in args else "GET"
url = next(a for a in args if a.startswith("http"))
body = next((open(a[1:]).read() for a in args if a.startswith("@")), "")
open(os.path.join(d, "calls.log"), "a").write("%s %s\n" % (method, url))
if os.environ.get("STUB_MODE") == "down":
    sys.exit(7)
def load(n): return json.load(open(os.path.join(d, n)))
def save(n, v): json.dump(v, open(os.path.join(d, n), "w"))
def out(v, code=200):
    sys.stdout.write(json.dumps(v) + "\n" + str(code)); sys.exit(0)
path = re.sub(r"^https?://[^/]+", "", url).split("?")[0]
tasks = load("tasks.json")
if path == "/api/workspaces" and method == "GET":
    out(load("workspaces.json"))
if path == "/api/tasks" and method == "GET":
    live = [t for t in tasks if not t.get("archived_at")]
    out({"tasks": live, "total": len(live)})
if path == "/api/tasks/ingest" and method == "POST":
    with open(os.path.join(d, "cards.jsonl"), "a") as fh: fh.write(body + "\n")
    p = json.loads(body)
    out({"ok": True, "task_id": "new-1", "workspace_id": p.get("department_slug") or "general-task",
         "resolved_by": "department_slug:%s" % p.get("department_slug") if p.get("department_slug") else "auto-route:general-task-fallback"}, 201)
m = re.match(r"^/api/tasks/([^/]+)(/messages|/archive)?$", path)
if m:
    t = next((t for t in tasks if t["id"] == m.group(1)), None)
    if not t: out({"error": "Task not found"}, 404)
    if not m.group(2) and method == "GET": out(t)
    if m.group(2) == "/messages" and method == "POST":
        with open(os.path.join(d, "notes.jsonl"), "a") as fh: fh.write(json.dumps({"task": t["id"], "body": json.loads(body)}) + "\n")
        out({"activity": {"id": "a1"}})
    if m.group(2) == "/archive" and method == "POST":
        t["archived_at"] = t.get("archived_at") or "2026-09-30T12:00:00Z"; save("tasks.json", tasks)
        out({"ok": True, "id": t["id"], "archived_at": t["archived_at"]})
out({"error": "unexpected"}, 500)
STUB
chmod +x "$WORK/bin/curl"

reset_board() {
  rm -f "$WORK/calls.log" "$WORK/cards.jsonl" "$WORK/notes.jsonl"
  cat > "$WORK/workspaces.json" <<'JSON'
[{"id":"ws-mkt","slug":"marketing","name":"Marketing"},
 {"id":"ws-social","slug":"dept-social-media","name":"Social Media"},
 {"id":"ws-gen","slug":"general-task","name":"General Task"}]
JSON
  cat > "$WORK/tasks.json" <<'JSON'
[{"id":"task-onb","title":"Build onboarding sequence","status":"in_progress","workspace_id":"ws-mkt","updated_at":"2026-09-29T10:00:00Z","archived_at":null},
 {"id":"task-news","title":"Write partner newsletter","status":"review","workspace_id":"ws-mkt","updated_at":"2026-09-28T10:00:00Z","archived_at":null},
 {"id":"task-post1","title":"Post holiday hours","status":"inbox","workspace_id":"ws-social","updated_at":"2026-09-27T10:00:00Z","archived_at":null},
 {"id":"task-post2","title":"Post job opening","status":"inbox","workspace_id":"ws-social","updated_at":"2026-09-26T10:00:00Z","archived_at":null},
 {"id":"task-other","title":"Other company newsletter","status":"inbox","workspace_id":"ws-foreign","updated_at":"2026-09-25T10:00:00Z","archived_at":null}]
JSON
}

OUT=""; RC=0
run() {
  OUT="$(env PATH="$WORK/bin:$PATH" HOME="$WORK/home" STUB_DIR="$WORK" STUB_MODE="${STUB_MODE:-}" \
      MC_ROUTE_STATE_DIR="$WORK/state" MC_ROUTE_MAX_RETRIES=0 \
      MC_ROUTE_INGEST_URL="http://127.0.0.1:4000/api/tasks/ingest" \
      bash "$MC_ROUTE" "$@" 2>&1)"
  RC=$?
}
cards() { [ -f "$WORK/cards.jsonl" ] && wc -l < "$WORK/cards.jsonl" | tr -d ' ' || echo 0; }
writes() { [ -f "$WORK/calls.log" ] || { echo 0; return; }; grep -vc '^GET ' "$WORK/calls.log"; }  # grep -c prints 0 itself
archived() { python3 -c 'import json,sys; print(",".join(t["id"] for t in json.load(open(sys.argv[1])) if t.get("archived_at")))' "$WORK/tasks.json"; }

echo "--- (a) existing status: read-only, no card ---"
reset_board
run existing status "Build onboarding sequence"
[ "$RC" -eq 0 ] && ok "(a) exit 0" || fail "(a) exit $RC: $OUT"
printf '%s\n' "$OUT" | grep -qx 'STATUS id=task-onb status=in_progress department=marketing updated=2026-09-29T10:00:00Z cancelled=no title="Build onboarding sequence"' \
  && ok "(a) prints the card's status line" || fail "(a) status line missing: $OUT"
[ "$(cards)" = 0 ] && ok "(a) no card made" || fail "(a) made $(cards) card(s)"
[ "$(writes)" = 0 ] && ok "(a) only GET calls (strictly read-only)" || fail "(a) non-GET calls: $(grep -v '^GET ' "$WORK/calls.log")"

echo "--- (b) status by id and by fuzzy title ---"
run existing status task-news
printf '%s\n' "$OUT" | grep -q '^STATUS id=task-news status=review ' && ok "(b) by id" || fail "(b) by id: $OUT"
run existing status "the onboarding sequence"
printf '%s\n' "$OUT" | grep -q '^STATUS id=task-onb ' && ok "(b) by fuzzy title" || fail "(b) fuzzy: $OUT"
[ "$(cards)" = 0 ] && [ "$(writes)" = 0 ] && ok "(b) still nothing written" || fail "(b) cards=$(cards) writes=$(writes)"

echo "--- (c) existing update adds the owner's note ---"
reset_board
run existing update "partner newsletter" "Make it two pages, not one."
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -qx 'UPDATED id=task-news title="Write partner newsletter"' \
  && ok "(c) prints UPDATED for the right card" || fail "(c) rc=$RC: $OUT"
note="$(python3 -c 'import json,sys; n=json.loads(open(sys.argv[1]).readline()); print(n["task"], n["body"]["sender"], n["body"]["content"])' "$WORK/notes.jsonl" 2>/dev/null)"
[ "$note" = "task-news owner Make it two pages, not one." ] && ok "(c) note posted to that card as the owner" || fail "(c) note=$note"
[ "$(cards)" = 0 ] && [ -z "$(archived)" ] && ok "(c) no card, nothing cancelled" || fail "(c) cards=$(cards) archived=$(archived)"

echo "--- (d) existing cancel cancels that card ---"
reset_board
run existing cancel "Build onboarding sequence"
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -qx 'CANCELLED id=task-onb title="Build onboarding sequence"' \
  && ok "(d) prints CANCELLED" || fail "(d) rc=$RC: $OUT"
[ "$(archived)" = "task-onb" ] && ok "(d) only that card is archived (off the board)" || fail "(d) archived=$(archived)"
grep -q 'Cancelled by the owner' "$WORK/notes.jsonl" 2>/dev/null && ok "(d) cancel note recorded on the card" || fail "(d) no cancel note"
[ "$(cards)" = 0 ] && ok "(d) no card made" || fail "(d) made $(cards) card(s)"
before="$(writes)"
run existing cancel task-onb
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q 'already cancelled' && [ "$(writes)" = "$before" ] \
  && ok "(d) cancelling again by id finds the archived card and writes nothing" || fail "(d) re-cancel rc=$RC writes=$(writes)/$before: $OUT"

echo "--- (e) no match / several matches change nothing ---"
reset_board
run existing cancel "quarterly tax filing"
[ "$RC" -eq 3 ] && printf '%s\n' "$OUT" | grep -q 'NOT_FOUND' && [ "$(writes)" = 0 ] \
  && ok "(e) no match -> NOT_FOUND, exit 3, nothing written" || fail "(e) rc=$RC writes=$(writes): $OUT"
run existing cancel "post"
[ "$RC" -eq 3 ] && printf '%s\n' "$OUT" | grep -q 'AMBIGUOUS' && printf '%s\n' "$OUT" | grep -q 'id=task-post1' \
  && printf '%s\n' "$OUT" | grep -q 'id=task-post2' && [ "$(writes)" = 0 ] \
  && ok "(e) two matches -> AMBIGUOUS with both ids, nothing written" || fail "(e) rc=$RC writes=$(writes): $OUT"
run existing status "Other company newsletter"
[ "$RC" -eq 3 ] && ok "(e) another company's card is not found" || fail "(e) foreign card rc=$RC: $OUT"
reset_board
run existing stop "Build onboarding sequence"
[ "$RC" -eq 2 ] && printf '%s\n' "$OUT" | grep -q 'REFUSED' && [ ! -f "$WORK/calls.log" ] \
  && ok "(e) 'existing stop' is a usage error, no call made" || fail "(e) existing stop rc=$RC: $OUT"
run existing update "Build onboarding sequence"
[ "$RC" -eq 2 ] && [ ! -f "$WORK/calls.log" ] && ok "(e) 'existing update' without a note is a usage error" || fail "(e) update no note rc=$RC: $OUT"

echo "--- (f) unknown first words create nothing and exit non-zero ---"
reset_board
for words in "status|task-onb" "stop|Build onboarding sequence" "check|Build onboarding sequence" "list|" "legal|Legal review|review the contract" "2|" "|"; do
  IFS='|' read -r -a argv <<<"$words"
  [ "${#argv[@]}" -gt 0 ] || argv=("")
  run "${argv[@]}"
  if [ "$RC" -ne 0 ] && printf '%s\n' "$OUT" | grep -q 'mc-route: REFUSED' && printf '%s\n' "$OUT" | grep -q 'existing status' \
     && [ "$(cards)" = 0 ] && ! printf '%s\n' "$OUT" | grep -q 'ESCALATE_TO_OPERATOR'; then
    ok "(f) '${argv[0]}' -> REFUSED + usage, exit $RC, no card"
  else
    fail "(f) '${argv[0]}' -> rc=$RC cards=$(cards): $OUT"
  fi
done
run help
[ "$RC" -eq 0 ] && printf '%s\n' "$OUT" | grep -q 'existing cancel' && [ "$(cards)" = 0 ] && ok "(f) help prints usage, no card" || fail "(f) help rc=$RC"

echo "--- (g) real departments still route ---"
reset_board
run marketing "Spring campaign" "Plan the spring campaign"
slug="$(python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).readline())["department_slug"])' "$WORK/cards.jsonl" 2>/dev/null)"
[ "$RC" -eq 0 ] && [ "$(cards)" = 1 ] && [ "$slug" = marketing ] && ok "(g) 'marketing' -> one card, department_slug=marketing" || fail "(g) rc=$RC cards=$(cards) slug=$slug: $OUT"
reset_board
run social-media "Post the promo" "Post the promo on Instagram"
slug="$(python3 -c 'import json,sys; print(json.loads(open(sys.argv[1]).readline())["department_slug"])' "$WORK/cards.jsonl" 2>/dev/null)"
[ "$RC" -eq 0 ] && [ "$slug" = dept-social-media ] && ok "(g) alias 'social-media' is sent as the board slug dept-social-media" || fail "(g) alias rc=$RC slug=$slug: $OUT"

echo "--- (h) task mode unchanged ---"
reset_board
run task "Refund the Smith order" "Refund the Smith order please"
[ "$RC" -eq 0 ] && [ "$(cards)" = 1 ] && [ "$(wc -l < "$WORK/calls.log" | tr -d ' ')" = 1 ] \
  && printf '%s\n' "$OUT" | grep -q '^ROUTED ' && ok "(h) one ingest POST, no department lookup" || fail "(h) rc=$RC calls=$(cat "$WORK/calls.log"): $OUT"

echo "--- (i) Command Center down during the department check ---"
reset_board
STUB_MODE=down run marketing "Spring campaign" "Plan the spring campaign"
[ "$RC" -eq 1 ] && [ "$(cards)" = 0 ] && printf '%s\n' "$OUT" | grep -q 'nothing was created' \
  && ok "(i) exit 1, nothing created" || fail "(i) rc=$RC cards=$(cards): $OUT"

echo ""
echo "=== mc-route existing mode: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  for e in "${ERRORS[@]}"; do echo "  - $e"; done
  exit 1
fi
exit 0
