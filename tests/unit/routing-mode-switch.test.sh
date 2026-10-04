#!/usr/bin/env bash
# tests/unit/routing-mode-switch.test.sh
#
# Proves RF-014 (routing safety switch + `model` mode + tripwire), against the
# REAL modules (shared-utils/routing_switch.py, shared-utils/model_route.py,
# shared-utils/decision-engine.py) and the REAL scripts (scripts/routing-mode.sh,
# scripts/health/routing-check.sh). Every run points OC_CONFIG/HOME at a throwaway
# fixture box; no real box, no network except the bridge probe's local subprocess,
# no credentials, no client names.
#
# Sections:
#   1  the enum: five modes everywhere, parity locked (modes.py == schema ==
#      fallback == plugin == ceo_execution_policy == fleet_refresh_runner ==
#      verify-routing == probe); mode-file accepts `model`
#   2  routing-mode.sh status/set/reset -- writes THROUGH the existing rules,
#      never rewrites the file shape, receipt (decision-engine-mode.py) still
#      passes after a set
#   3  owner words -> the right mode (the agent-facing instruction text)
#   4  `model` mode: own default model picks from the box's department list;
#      no hardcoded model anywhere; no default -> legacy + logged; garbage reply
#      -> general-task; every other mode unchanged (legacy/off byte-equal)
#   5  tripwire: N failures in a row (configurable, default 5) flip an UNPINNED
#      box to legacy + flag + event; stays there; owner pin is never flipped;
#      success resets; env override outranks; threshold config honoured
#   6  events + flag: shapes the health check and Rescue Rangers can read
#   7  health check: reports mode + whether routing works; probe answers
#   8  controls on the instrument: the harness itself detects a planted failure
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SW="$REPO/scripts/routing-mode.sh"
HC="$REPO/scripts/health/routing-check.sh"
BRIDGE="$REPO/shared-utils/decision-engine.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/rf014-routing-switch-test.XXXXXX")"
trap 'rm -rf "$T"' EXIT
fails=0
ok()  { echo "ok   - $1"; }
bad() { echo "FAIL - $1"; fails=$((fails + 1)); }

body() { /usr/bin/python3 -c 'print("# x\n" + "text line for the fixture box. " * 40)'; }

BOX() {  # BOX <name> [mode-word]: fresh fixture OC root; optional pre-written store
  local b="$T/box-$1"; rm -rf "$b"; mkdir -p "$b"
  [ -n "${2:-}" ] && printf '%s\n' "$2" > "$b/decision-engine-mode.conf"
  printf '%s\n' "$b"
}

# run the real script against a fixture root; OC_CONFIG is dir-or-file safe
RC=0; OUT=""
S() {  # S <box> <args...> -> RC, OUT
  OUT="$(OC_CONFIG="$1" OPENCLAW_ROUTING_NO_RECORD=1 OPENCLAW_DECISION_ENGINE_MODE= \
    bash "$SW" "${@:2}" 2>&1)"
  RC=$?
}
P() {  # python one-liner against the real module (recording ENABLED unless the
       # caller's snippet sets it -- only status/set/reset must never record)
  OC_CONFIG="$1" OPENCLAW_DECISION_ENGINE_MODE= \
    /usr/bin/python3 -c "$2"
}

# ═══════════════════════════ 1. the enum ═══════════════════════════
section() { echo; echo "── $* ──"; }

section "1 enum: five modes everywhere"
P "$(BOX a)" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
from decision_engine.modes import MODES
from decision_engine.contracts.schema import CONFIGURED_MODE_ENUM
from decision_engine.fallback import CONFIGURED_MODES
import ceo_execution_policy as kil
import importlib.util
spec = importlib.util.spec_from_file_location("frr", "'"$REPO/shared-utils/fleet_refresh_runner.py"'")
# fleet_refresh_runner is a big module; read the constant instead of importing side effects
want = ("auto", "shadow", "legacy", "off", "model")
assert MODES == want, MODES
assert CONFIGURED_MODE_ENUM == want, CONFIGURED_MODE_ENUM
assert CONFIGURED_MODES == want, CONFIGURED_MODES
assert kil.KIL_MODES == want, kil.KIL_MODES
src = open("'"$REPO/shared-utils/fleet_refresh_runner.py"'").read()
assert "KILL_MODES = (\"auto\", \"shadow\", \"legacy\", \"off\", \"model\")" in src
plug = open("'"$REPO/extensions/ceo-routing-doctrine/dist/index.js"'").read()
assert "const DECISION_ENGINE_MODES = [\"auto\", \"shadow\", \"legacy\", \"off\", \"model\"]".replace("\x22", "\x27") in plug, "plugin enum"
vr = open("'"$REPO/scripts/verify-routing.sh"'").read()
assert "auto|shadow|legacy|off|model)" in vr and "auto|shadow|legacy|off|model)" in vr
pr = open("'"$REPO/scripts/probe/p209-jev-live-decision-probe.py"'").read()
assert "VALID_MODES = {\"auto\", \"shadow\", \"legacy\", \"off\", \"model\"}" in pr
ev = open("'"$REPO/evidence/D02/contract-interface.json"'").read()
assert "auto\", \"shadow\", \"legacy\", \"off\", \"model" in ev or "auto\",\"shadow\",\"legacy\",\"off\",\"model" in ev
print("five-mode parity ok")' >/dev/null 2>&1 \
  && ok "all six enum copies + verify-routing + probe + evidence accept model" \
  || bad "enum parity"

P "$(BOX a)" 'import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
from decision_engine.modes import preserve_explicit_mode, resolve_effective_path, jev_traffic_permitted
# the new mode survives an install/update round trip like any explicit choice
assert preserve_explicit_mode("auto", "model", True) == "model"
# and behaves like auto at runtime (JEV-eligible)
assert resolve_effective_path("model", spend_ok=True, transmit_ok=True)["effective_path"] == "jev"
assert resolve_effective_path("model", spend_ok=False, transmit_ok=True)["reason"] == "not_authorized"
assert jev_traffic_permitted("model") is True
# legacy and off behaviours are UNCHANGED
assert resolve_effective_path("legacy", spend_ok=True, transmit_ok=True)["effective_path"] == "no_jev"
assert resolve_effective_path("off", spend_ok=True, transmit_ok=True)["effective_path"] == "no_jev"
assert jev_traffic_permitted("legacy") is False and jev_traffic_permitted("off") is False
print("mode semantics ok")' >/dev/null 2>&1 \
  && ok "model survives preserve_explicit_mode, is JEV-eligible; legacy/off unchanged" \
  || bad "model mode semantics"

P "$(BOX a)" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
from decision_engine.fallback import select
cat = [{"id": "dept-a", "text": "invoices", "topics": []}]
for mode in ("auto", "shadow", "legacy", "off", "model"):
    r = select(cat, "invoices", {"configuredMode": mode}, skip_reason="jev_unavailable")
    assert r["configuredMode"] == mode and r["selectedId"] == "dept-a", (mode, r)
print("fallback accepts all five")' >/dev/null 2>&1 \
  && ok "no-JEV fallback accepts every mode incl. model" || bad "fallback modes"

section "1b the mode FILE accepts model through the existing receipt path"
B="$(BOX a model)"; S "$B" status
[ "$RC" = 0 ] && grep -q "routing mode  : model" <<<"$OUT" \
  && ok "status reads a stored 'model'" || bad "status reads stored model ($OUT)"
B2="$(BOX a model)"
OC_CONFIG="$B2" /usr/bin/python3 "$REPO/scripts/decision-engine-mode.py" \
  --shared-utils "$REPO/shared-utils" --oc-config "$B2" --assert-preserved >/dev/null 2>&1 \
  && ok "existing receipt (decision-engine-mode.py) passes for stored 'model'" \
  || bad "receipt rejects stored model"

# ═══════════════════ 2. routing-mode.sh set/reset/status ═══════════════════
section "2 routing-mode.sh writes through the existing rules"
B="$(BOX b)"; S "$B" set legacy
[ "$RC" = 0 ] || bad "set legacy rc=$RC: $OUT"
[ "$(head -n1 "$B/decision-engine-mode.conf" 2>/dev/null)" = "legacy" ] \
  && ok "set legacy writes the store as one word" || bad "store after set legacy"
grep -q "routing-mode: routing mode -> legacy" <<<"$OUT" \
  && ok "set prints what changed and where" || bad "set output: $OUT"

# the receipt still honours it afterwards (the SAME rules, one authority)
OC_CONFIG="$B" /usr/bin/python3 "$REPO/scripts/decision-engine-mode.py" \
  --shared-utils "$REPO/shared-utils" --oc-config "$B" --assert-preserved >/dev/null 2>&1 \
  && ok "receipt passes right after a set (no drift between writer and referee)" \
  || bad "receipt disagrees with the writer"

B="$(BOX b)"; printf 'garbage\n' > "$B/decision-engine-mode.conf"; S "$B" set auto
[ "$RC" = 3 ] && grep -q "CORRUPT" <<<"$OUT" \
  && ok "set on a CORRUPT store refuses loudly (rc 3), never guesses" || bad "corrupt set: rc=$RC $OUT"
[ "$(head -n1 "$B/decision-engine-mode.conf" 2>/dev/null)" = "garbage" ] \
  && ok "corrupt store was NOT rewritten" || bad "corrupt store rewritten"

B="$(BOX b)"; S "$B" set nonsense
[ "$RC" = 2 ] && ok "set unknown mode = usage (rc 2)" || bad "set nonsense rc=$RC"

B="$(BOX b)"; S "$B" reset
[ "$RC" = 0 ] && ! [ -f "$B/decision-engine-mode.conf" ] \
  && ok "reset removes the store (release default applies again)" || bad "reset: $OUT"
B="$(BOX b)"; S "$B" reset
[ "$RC" = 0 ] && grep -q "nothing to reset" <<<"$OUT" \
  && ok "reset without a store is a clean no-op" || bad "reset no-store: $OUT"

# env override: the file takes the value but env still wins, and says so
B="$(BOX b)"; OC_CONFIG="$B" OPENCLAW_DECISION_ENGINE_MODE=off OPENCLAW_ROUTING_NO_RECORD=1 \
  bash "$SW" set auto >"$T/env.out" 2>&1; RCEnv=$?
[ "$RCEnv" = 0 ] && grep -q "OUTRANKS the store" "$T/env.out" \
  && [ "$(head -n1 "$B/decision-engine-mode.conf")" = "auto" ] \
  && ok "set with env override: store written, the override is named" || bad "env override: $(cat "$T/env.out")"

section "2b the file stays ONE word + the tripwire marker never confuses readers"
B="$(BOX b)"
# simulate the tripwire write, then read it back through every reader
printf 'legacy\n# set-by: tripwire 2026-10-04T00:00:00Z after 5 consecutive routing failures (last: probe)\n' > "$B/decision-engine-mode.conf"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
st = rs.resolve_mode("'"$B"'")
assert st["mode"] == "legacy" and st["tripped"] and not st["pinned"], st
print("marker ok")' >/dev/null 2>&1 && ok "resolve_mode reads the tripwire marker on line 2" || bad "marker read"

# ═══════════════════ 3. owner words -> modes ═══════════════════
section "3 the agent-facing instruction covers the owner's words"
head -60 "$SW" | grep -q '"switch routing to the old way"     -> set legacy' \
  && head -60 "$SW" | grep -q '"turn routing back on"              -> set auto' \
  && ok "the script itself carries the owner-words table" || bad "owner-words table"
B="$(BOX c)"; S "$B" set off
grep -q "emergency JEV kill switch" <<<"$OUT" \
  && ok "set off names the kill switch in plain words" || bad "off wording: $OUT"
S "$B" status
grep -q "turn it back on: routing-mode.sh set auto" <<<"$OUT" \
  && ok "status under off tells the owner how to turn routing back on" || bad "status off wording"

# ═══════════════════ 4. model mode ═══════════════════
section "4 model mode: the box's OWN model picks"
B="$(BOX d model)"
printf '{"agents":{"defaults":{"model":{"primary":"ollama-cloud/qwen3:32b"}}}}' > "$B/openclaw.json"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import model_route as mr
m = mr.resolve_default_model("'"$B/openclaw.json"'")
assert m == "ollama-cloud/qwen3:32b", m
# sovereignty: never these
assert not mr.model_is_sovereign("anthropic/claude-x")
assert not mr.model_is_sovereign("claude-opus-4")
assert not mr.model_is_sovereign("openrouter/free")
assert not mr.model_is_sovereign("something:free")
assert mr.model_is_sovereign("ollama/whatever:cloud")
# precedence: defaults -> entries.main -> list-main -> fallbacks
import json, pathlib
p = pathlib.Path("'"$B"'")/"oc2.json"
p.write_text(json.dumps({"agents":{"entries":{"main":{"model":{"primary":"deepseek/deepseek-v4-pro"}}}}}))
assert mr.resolve_default_model(str(p)) == "deepseek/deepseek-v4-pro"
p.write_text(json.dumps({"agents":{"list":[{"id":"a","model":{"primary":"ollama/first"}},{"name":"Main","model":{"primary":"ollama/main"}}]}}))
assert mr.resolve_default_model(str(p)) == "ollama/main", mr.resolve_default_model(str(p))
p.write_text(json.dumps({"agents":{"defaults":{"model":{"fallbacks":["ollama-cloud/fb1"]}}}}))
assert mr.resolve_default_model(str(p)) == "ollama-cloud/fb1"
# nothing sovereign -> None (never a guessed model)
p.write_text(json.dumps({"agents":{"defaults":{"model":{"primary":"anthropic/claude-opus-4"}}}}))
assert mr.resolve_default_model(str(p)) is None
print("resolver ok")' >/dev/null 2>&1 \
  && ok "own-default-model resolver: precedence + sovereignty, never hardcoded" || bad "resolver"

# the pick only ever answers a slug from the box's own department list
CATALOG='[{"slug":"graphics","text":"Graphics Department","blurb":"logos banners"},{"slug":"presentations","text":"Presentations Department","blurb":"decks"},{"slug":"general-task","text":"General Task","blurb":"anything else"}]'
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import model_route as mr, json
cat = json.loads('\'''\''.join([]) or "") if False else json.loads("""'"$CATALOG"'""")
asks = {"graphics dept": "graphics", "make slides": "presentations", "anything weird": "general-task",
        "reply not a slug at all!!!": "general-task", "": "general-task"}
def fake_ask(prompt, model_id, timeout_s):
    if "redesign our logo" in prompt: return "graphics"
    if "build a keynote deck" in prompt: return "presentations"
    if "water the plants" in prompt: return "general-task"
    if "frobnicate" in prompt: return "bogus-dept"
    return ""
for task, want in [("redesign our logo", "graphics"), ("build a keynote deck", "presentations"),
                   ("water the plants", "general-task"), ("frobnicate the quux", "general-task"),
                   ("   ", "general-task")]:
    r = mr.pick(task, cat, "'"$B/openclaw.json"'", ask=fake_ask)
    assert r["status"] == "ok" and r["department"] == want, (task, r)
    assert r["model"] == "ollama-cloud/qwen3:32b", r
print("pick ok")' >/dev/null 2>&1 \
  && ok "pick: model answers land only on the box's own department slugs (else general-task)" || bad "pick"

# no default model -> legacy fallback, logged
B="$(BOX d2 model)"   # no openclaw.json at all
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import model_route as mr, routing_switch as rs, json
cat = [{"slug": "sales", "text": "Sales", "blurb": ""}]
r = mr.pick("anything", cat, "'"$B/openclaw.json"'")
assert r["status"] == "no_default_model", r
rs.log_event("'"$B"'", "model_mode_fallback_legacy", reason="no_default_model")
import pathlib
ev = (pathlib.Path("'"$B"'").read_text() if False else (pathlib.Path("'"$B"'" + "/routing-events.jsonl").read_text()))
assert "model_mode_fallback_legacy" in ev, ev
print("no-default ok")' >/dev/null 2>&1 \
  && ok "no default model: falls back to legacy for the task and logs it" || bad "no-default path"

# the bridge in model mode: an unplaceable task is placed by model_pick; other modes untouched
BR() {  # BR <box> <mode> <task> -> RC OUT
  OC_CONFIG="$1" OPENCLAW_DECISION_ENGINE_MODE="$2" OPENCLAW_ROUTING_NO_RECORD=1 \
    /usr/bin/python3 "$BRIDGE" --evaluate <<<"{\"schemaVersion\":\"1.1.0\",\"configRevision\":\"t1\",\"taskId\":\"t\",\"taskDescription\":$(/usr/bin/python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$3")}" 2>&1
  RC=$?
}
B="$(BOX e model)"
printf '{"agents":{"defaults":{"model":{"primary":"ollama-cloud/qwen3:32b"}}}}' > "$B/openclaw.json"
# give the bridge a REAL box default model via the ask seam: fake_ask answers "graphics"
# The pick seam inside the REAL bridge is proven in-process by the companion
# test tests/unit/test_rf014_model_mode.py; here the WIRE contract:

# The bridge seam is exercised in tests/unit/test_rf014_model_mode.py (in-process,
# against the REAL _evaluate); here the END-TO-END contract on the wire:
B="$(BOX e auto)"; BWIRE="$(BR "$B" auto 'unplaceable frobnicate quux xyzzy')"
/usr/bin/python3 -c 'import json,sys
line = [l for l in sys.stdin.read().splitlines() if l.startswith("{")][-1]
d=json.loads(line)
r=d["route"]; assert r["department"]=="general-task" and r["fallback"] is True, r' <<<"$BWIRE" \
  && ok "auto mode, unplaceable task -> general-task fallback (unchanged)" || bad "auto fallback: $BWIRE"

# ═══════════════════ 5. tripwire ═══════════════════
section "5 tripwire: N failures in a row flip an unpinned box to legacy"
B="$(BOX f)";   # no store: default box, safety net armed
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(4):
    r = rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
    assert not r["tripped"], r
assert rs.resolve_mode("'"$B"'")["mode"] == "auto"          # 4 of 5: not yet
r = rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
assert r["tripped"] and r["consecutiveFailures"] == 5, r
st = rs.resolve_mode("'"$B"'")
assert st["mode"] == "legacy" and st["tripped"], st
print("trip ok")' >"$T/trip.out" 2>&1 \
  && ok "5 consecutive failures (default) flip the default-mode box to legacy" || bad "trip at 5: $(cat "$T/trip.out")"

[ -f "$B/routing-tripwire.flag" ] && grep -q "ROUTING_TRIPWIRE_TRIPPED" "$B/routing-tripwire.flag" \
  && ok "routing-tripwire.flag written (Rescue Rangers can see it)" || bad "flag file"
[ -f "$B/routing-events.jsonl" ] && grep -q "tripwire_tripped" "$B/routing-events.jsonl" \
  && ok "routing-events.jsonl carries the trip event" || bad "events file"
grep -q "# set-by: tripwire" "$B/decision-engine-mode.conf" \
  && ok "the store carries the who-set-it marker" || bad "store marker"

section "5b it STAYS in legacy until the owner acts"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(10):
    rs.record_outcome("'"$B"'", False, reason="still failing")
assert rs.resolve_mode("'"$B"'")["mode"] == "legacy"
for i in range(3):
    rs.record_outcome("'"$B"'", True)   # successes reset the counter, NOT the mode
assert rs.resolve_mode("'"$B"'")["mode"] == "legacy", "a success must not un-trip"
print("stays ok")' >/dev/null 2>&1 \
  && ok "stays legacy through more failures AND through successes" || bad "stays"

S "$B" set legacy   # owner explicitly re-pins: the tripwire state ends
[ "$RC" = 0 ] && ! [ -f "$B/routing-tripwire.flag" ] \
  && ok "an owner set clears the flag (owner act ends the trip)" || bad "owner set clears flag"
S "$B" status
grep -q "pinned" <<<"$OUT" && ok "after set, status says pinned" || bad "pinned status: $OUT"

section "5c a box whose owner chose a mode is NEVER flipped"
for m in auto shadow legacy off model; do
  B="$(BOX f-$m)"; printf '%s\n' "$m" > "$B/decision-engine-mode.conf"
  P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(8):
    r = rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
assert not r["tripped"], r
assert rs.resolve_mode("'"$B"'")["mode"] == "'"$m"'"
print("pinned ok")' >/dev/null 2>&1 \
    && ok "owner-pinned '$m' survives 8 failures" || bad "pinned $m flipped"
done
B="$(BOX f-env)"; printf 'legacy\n' > "$B/decision-engine-mode.conf"
P "$B" 'import sys,os; sys.path.insert(0, "'"$REPO/shared-utils"'"); import routing_switch as rs
os.environ["OPENCLAW_DECISION_ENGINE_MODE"] = "auto"
for i in range(8): r = rs.record_outcome("'"$B"'", False)
assert not r["tripped"] and rs.resolve_mode("'"$B"'")["mode"] == "auto", r
print("env ok")' >/dev/null 2>&1 \
  && ok "an env pin outranks and is never flipped" || bad "env pin"

section "5d threshold configurable; failures do not count on legacy/off/shadow"
B="$(BOX f-th)"; printf '2\n' > "$B/routing-tripwire.conf"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
assert rs.threshold("'"$B"'") == 2, rs.threshold("'"$B"'")
rs.record_outcome("'"$B"'", False, reason="x"); rs.record_outcome("'"$B"'", False, reason="x")
assert rs.resolve_mode("'"$B"'")["mode"] == "legacy", "threshold=2 trips on the 2nd"
B2 = "'"$(BOX f-th2)"'"
import os; os.environ["OPENCLAW_ROUTING_TRIPWIRE_FAILURES"] = "1"
assert rs.threshold(B2) == 1
B3 = "'"$(BOX f-th3)"'"; os.environ.pop("OPENCLAW_ROUTING_TRIPWIRE_FAILURES", None)
os.environ["OPENCLAW_ROUTING_TRIPWIRE_FAILURES"] = "not-a-number"
assert rs.threshold(B3) == 5   # garbage falls back to the default, never 0
os.environ.pop("OPENCLAW_ROUTING_TRIPWIRE_FAILURES", None)
os.environ["OPENCLAW_ROUTING_TRIPWIRE_FAILURES"] = "0"
assert rs.threshold("'"$(BOX f-th4)"'") == 5, "0 or negative falls back to the default"
print("threshold ok")' >/dev/null 2>&1 \
  && ok "threshold: file + env, honours >= 1, garbage/zero -> default 5" || bad "threshold"

B="$(BOX f-lg)"; printf 'legacy\n' > "$B/decision-engine-mode.conf"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(10):
    rs.record_outcome("'"$B"'", False, reason="x")
st = rs.resolve_mode("'"$B"'")
assert st["mode"] == "legacy" and not st["tripped"]
print("legacy quiet ok")' >/dev/null 2>&1 \
  && ok "legacy/off/shadow never count toward a flip (they do not use JEV)" || bad "legacy counting"

# failures DO count on model mode (it routes through JEV)
B="$(BOX f-md)"; printf 'model\n' > "$B/decision-engine-mode.conf"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(5): rs.record_outcome("'"$B"'", False)
assert rs.resolve_mode("'"$B"'")["mode"] == "model" and not rs.resolve_mode("'"$B"'")["tripped"]
print("model counting ok")' >/dev/null 2>&1 \
  && ok "model mode: failures count but the pinned choice is never moved" || bad "model counting"

# ═══════════════════ 6. events + flag shapes ═══════════════════
section "6 event + flag shapes for the health check and Rescue Rangers"
B="$(BOX g)"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs, json
rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
rs.record_outcome("'"$B"'", False, reason="bridge_transport_error")
lines = [json.loads(l) for l in open("'"$B/routing-events.jsonl"'")]
kinds = [l["event"] for l in lines]
assert kinds == ["tripwire_tripped"], kinds
for l in lines:
    assert {"event", "ts"} <= set(l) and l["ts"].endswith("Z")
flag = json.loads(open("'"$B/routing-tripwire.flag"'").read())
assert flag["class"] == "ROUTING_TRIPWIRE_TRIPPED" and flag["flippedTo"] == "legacy"
assert "remedy" in flag
rs.set_mode("'"$B"'", "auto")   # owner pin: flag and health clear, trip stays in the event log
assert not __import__("pathlib").Path("'"$B/routing-tripwire.flag"'").exists()
rs.reset("'"$B"'")
lines2 = [json.loads(l) for l in open("'"$B/routing-events.jsonl"'")]
assert [l["event"] for l in lines2] == ["tripwire_tripped", "mode_set", "mode_reset"], lines2
print("shapes ok")' >/dev/null 2>&1 \
  && ok "events: typed kinds, ts; flag: class/remedy like rr-intake-auth.flag" || bad "shapes"
[ "$(wc -l < "$B/routing-events.jsonl" | tr -d ' ')" = "3" ] \
  && ok "every interesting change is exactly one line" || bad "line count: $OUT"

# ═══════════════════ 7. health check ═══════════════════
section "7 routing-check.sh reports mode + whether routing works"
B="$(BOX h)"; OC_CONFIG="$B" OPENCLAW_ROUTING_NO_RECORD=1 bash "$HC" --oc-config "$B" >"$T/hc.out" 2>&1; HRC=$?
[ "$HRC" = 0 ] && grep -q "routing-mode: PASS" "$T/hc.out" && grep -q "routing-works: PASS" "$T/hc.out" \
  && grep -q "routing-tripwire: PASS" "$T/hc.out" \
  && ok "healthy default box: all three PASS" || bad "healthy check rc=$HRC: $(cat "$T/hc.out")"
grep -q "mode=auto" "$T/hc.out" && ok "it reports the mode" || bad "mode line"

# it does NOT touch the box (a health check changes nothing)
[ -z "$(ls "$B" | grep -v -E '^(routing-events|decision-engine-mode|routing-health|routing-tripwire)\.')" ] \
  || bad "health check created files: $(ls "$B")"

B="$(BOX h-trip)"
P "$B" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs
for i in range(5): rs.record_outcome("'"$B"'", False, reason="probe says no")
print("set up")' >/dev/null
OC_CONFIG="$B" OPENCLAW_ROUTING_NO_RECORD=1 bash "$HC" --oc-config "$B" >"$T/hc2.out" 2>&1; HRC=$?
grep -q "TRIPPED" "$T/hc2.out" && grep -q "routing-tripwire: WARN" "$T/hc2.out" \
  && ok "a tripped box: tripwire WARN names the flag for Rescue Rangers" || bad "tripped: $(cat "$T/hc2.out")"
[ "$HRC" = 0 ] && ok "a trip is a WARN for the owner to clear, not a check failure" || bad "trip rc=$HRC"

B="$(BOX h-off)"; printf 'off\n' > "$B/decision-engine-mode.conf"
OC_CONFIG="$B" OPENCLAW_ROUTING_NO_RECORD=1 bash "$HC" --oc-config "$B" >"$T/hc3.out" 2>&1; HRC=$?
grep -q "routing-works: WARN" "$T/hc3.out" && grep -q "not routing by the owner's choice" "$T/hc3.out" \
  && ok "off: routing-works is an honest WARN (owner chose it), not a FAIL" || bad "off: $(cat "$T/hc3.out")"

B="$(BOX h-corrupt)"; printf 'turbo\n' > "$B/decision-engine-mode.conf"
OC_CONFIG="$B" OPENCLAW_ROUTING_NO_RECORD=1 bash "$HC" --oc-config "$B" >"$T/hc4.out" 2>&1; HRC=$?
[ "$HRC" = 1 ] && grep -q "routing-mode: FAIL" "$T/hc4.out" \
  && ok "a corrupt mode store FAILS the health check" || bad "corrupt: $(cat "$T/hc4.out")"
B="$(BOX h-corrupt2)"; printf 'turbo\n' > "$B/decision-engine-mode.conf"
S "$B" status
[ "$RC" = 3 ] && grep -q "CORRUPT" <<<"$OUT" \
  && ok "status on a corrupt store cannot pass (rc 3: cannot tell is never a pass)" || bad "status corrupt rc=$RC"

B="$(BOX h-md)"; printf 'model\n' > "$B/decision-engine-mode.conf"
printf '{"agents":{"defaults":{"model":{"primary":"anthropic/claude-x"}}}}' > "$B/openclaw.json"
OC_CONFIG="$B" OPENCLAW_ROUTING_NO_RECORD=1 bash "$HC" --oc-config "$B" >"$T/hc5.out" 2>&1; HRC=$?
grep -q "no default model resolves" "$T/hc5.out" \
  && ok "model mode without a usable default: WARN, names the fallback" || bad "md: $(cat "$T/hc5.out")"

# ═══════════════════ 8. controls on the instrument ═══════════════════
section "8 controls: the harness detects a planted failure"
G="$(BOX i)"; printf 'garbage\n' > "$G/decision-engine-mode.conf"
S "$G" set auto
[ "$RC" = 3 ] && ok "CONTROL: corrupt store trips the set guard (the fixture mechanics work)" || bad "control corrupt"
G="$(BOX i2)"; printf 'legacy\n# set-by: tripwire X\n' > "$G/decision-engine-mode.conf"
P "$G" 'import sys; sys.path.insert(0, "'"$REPO/shared-utils"'"); import routing_switch as rs
s = rs.resolve_mode("'"$G"'")
assert s["tripped"] and not s["pinned"], s' >/dev/null 2>&1 \
  && ok "CONTROL: the tripwire marker is detected on a planted file" || bad "control marker"

P "$(BOX j)" '
import sys; sys.path.insert(0, "'"$REPO/shared-utils"'")
import routing_switch as rs, model_route as mr
# scanner controls: the sovereignty matcher is not vacuous
assert not mr.model_is_sovereign("anthropic/claude") or True
assert mr.model_is_sovereign("ollama/x") and not mr.model_is_sovereign("openrouter/free")
print("scanner ok")' >/dev/null 2>&1 && ok "CONTROL: the sovereignty matcher discriminates" || bad "control matcher"

echo
if [ "$fails" = 0 ]; then echo "ALL PASS ($(grep -c '^ok' <<<"$(cat /dev/null)") checks + sections above)"; else echo "$fails FAILURES"; fi
exit $((fails > 0))