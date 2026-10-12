#!/usr/bin/env bash
# tests/unit/fleet-standards-legacy-exec-mode.test.sh
# -----------------------------------------------------------------------------
# CI guard: scripts/apply-fleet-standards.sh must TRANSLATE a legacy
# tools.exec.mode key instead of merging a combination the OpenClaw validator
# rejects and then rolling the WHOLE fleet-standards write back.
#
# THE DEFECT THIS GUARDS AGAINST (reproduced on two client Macs on 2026-09-15
# and again on 2026-09-17). apply-fleet-standards.sh deep-merges
# {"security": "full", "ask": "off"} into tools.exec. On a box whose config
# still carries the legacy tools.exec.mode key, the merged block holds mode AND
# security AND ask at once. OpenClaw rejects that:
#
#   tools.exec.mode: mode cannot be combined with security or ask in the same
#   exec object.
#
# The script printed "ERROR: openclaw config validate failed" and restored the
# backup, discarding EVERY standard it had just applied (toolSearch directory
# mode, the WhatsApp ban, the subagent ungate, plugins.allow, the lot). On every
# box carrying the legacy key, on every roll, forever.
#
# THE SCHEMA THIS IS MEASURED AGAINST (OpenClaw 2026.9.4 dist):
#   zod-schema.agent-runtime-*.mjs
#     ToolExecSchema = object(ToolExecBaseShape).strict()
#                        .superRefine(addExecPolicyModeConflictIssue)
#     addExecPolicyModeConflictIssue raises iff
#       mode !== undefined && (security !== undefined || ask !== undefined)
#   exec-approvals-core-*.mjs
#     resolveExecPolicyForMode:
#       deny -> security=deny, ask=off                 allowlist -> allowlist, off
#       ask  -> security=allowlist, ask=on-miss        auto      -> allowlist, on-miss
#       full -> security=full, ask=off
#
# WHAT THIS TEST PROVES.
#   T1  a legacy mode="full" box: the merged tools.exec carries NO mode key and
#       carries the fleet standard security=full / ask=off.
#   T2  the translation table matches resolveExecPolicyForMode EXACTLY, for all
#       five schema modes, including case/whitespace-insensitive input.
#   T3  the other standards survive a legacy-mode box (toolSearch directory
#       mode, the WhatsApp ban, the subagent ungate) -- the rollback is gone.
#   T4  an UNTRANSLATABLE mode value: we never guess and never delete it, the
#       tools.exec sub-block is skipped, and EVERY OTHER standard is still
#       applied (the "never roll back everything" contract).
#   T5  a box with no mode key is untouched by the translation and still gets
#       the standard exec ungate (no regression for the healthy majority).
#   T6  ANTI-VACUITY: the same fixture run through the PRE-FIX merge (canonical
#       deep-merged with no translation) DOES produce the forbidden
#       mode+security+ask combination. If this test cannot show the old code
#       failing, it is not measuring anything.
#   T7  the conflict-free invariant holds over every fixture: no produced
#       tools.exec ever has mode together with security or ask.
#   T8  REAL VALIDATOR (opportunistic). When an `openclaw` CLI is present AND a
#       known-good / known-bad control proves the instrument actually
#       discriminates, the produced configs are validated by the real binary.
#       If the control does not discriminate, the leg reports UNDETERMINED and
#       is skipped -- it never reports a pass it did not observe.
#
# The translation is extracted LIVE from the shipped script (from `CANONICAL = {`
# through `deep_merge(cfg, CANONICAL_TO_MERGE)`), never pasted as a frozen copy,
# so this test tracks the real source. It is exec()'d inside a minimal python
# driver against temp fixture configs. The rest of the roll (AGENTS.md
# injection, model-sovereignty repair, the live `openclaw config validate` gate,
# gateway restarts) NEVER runs. No real openclaw.json is read or written.
#
# Hermetic: its own mktemp -d sandbox, read-only over the checkout, no network,
# no fleet box, no credentials.
# Itself bash 3.2-safe: no associative arrays, no mapfile, no case modifiers.
#
# Run: bash tests/unit/fleet-standards-legacy-exec-mode.test.sh
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).
# -----------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$REPO_ROOT/scripts/apply-fleet-standards.sh"

PASS=0
FAIL=0
ok()  { printf '  ok   %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  FAIL %s\n' "$1"; FAIL=$((FAIL + 1)); }
note() { printf '  --   %s\n' "$1"; }
hdr() { printf '\n== %s ==\n' "$1"; }

if [ ! -f "$SCRIPT_UNDER_TEST" ]; then
  echo "FATAL: script under test not found: $SCRIPT_UNDER_TEST" >&2
  exit 1
fi

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX"; }
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Extract the canonical block + the legacy-exec-mode translation, live.
# -----------------------------------------------------------------------------
python3 - "$SCRIPT_UNDER_TEST" "$SANDBOX/block.py" <<'EXTRACTEOF'
import sys

src_path, out_path = sys.argv[1], sys.argv[2]
lines = open(src_path, encoding="utf-8").read().splitlines(True)

start = None
end = None
for idx, line in enumerate(lines):
    if start is None and line.rstrip("\n") == "CANONICAL = {":
        start = idx
    if start is not None and line.rstrip("\n") == "deep_merge(cfg, CANONICAL_TO_MERGE)":
        end = idx
        break

if start is None:
    sys.exit("FATAL: could not find 'CANONICAL = {' in the script under test")
if end is None:
    sys.exit("FATAL: could not find 'deep_merge(cfg, CANONICAL_TO_MERGE)' in the "
             "script under test. The legacy-exec-mode translation is MISSING or "
             "was renamed; that is the defect this guard exists to catch.")

block = "".join(lines[start:end + 1])

for needed in ("def translate_legacy_exec_mode(", "EXEC_MODE_TO_POLICY",
               "CANONICAL_TO_MERGE"):
    if needed not in block:
        sys.exit("FATAL: extracted block is missing %r" % needed)

open(out_path, "w", encoding="utf-8").write(block)
print("  extracted %d lines of live canonical+translation block" % (end - start + 1))
EXTRACTEOF
if [ $? -ne 0 ]; then
  echo "FATAL: extraction failed" >&2
  exit 1
fi

# -----------------------------------------------------------------------------
# The driver. Runs the extracted block over a fixture and reports the outcome
# as JSON on stdout.
# -----------------------------------------------------------------------------
cat > "$SANDBOX/driver.py" <<'DRIVEREOF'
import io
import json
import os
import sys
from contextlib import redirect_stdout

block_path, fixture_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
block = open(block_path, encoding="utf-8").read()
cfg = json.loads(open(fixture_path, encoding="utf-8").read())

ns = {"json": json, "os": os, "cfg": cfg}
buf = io.StringIO()

if mode == "prefix":
    # ANTI-VACUITY LEG: reproduce the PRE-FIX behaviour exactly. Same canonical
    # block, same deep_merge, but the translation is never invoked -- which is
    # what the shipped script did before this fix.
    with redirect_stdout(buf):
        exec(compile(block, "<extracted>", "exec"), ns)
    cfg = json.loads(open(fixture_path, encoding="utf-8").read())
    ns["deep_merge"](cfg, ns["CANONICAL"])
else:
    with redirect_stdout(buf):
        exec(compile(block, "<extracted>", "exec"), ns)
    cfg = ns["cfg"]

result = {"cfg": cfg, "stdout": buf.getvalue()}

if mode == "table":
    # Call the live translator directly, once per schema mode, and report what
    # it produced. This is the table check, not the merge check.
    table = {}
    for m in ["deny", "allowlist", "ask", "auto", "full", "  FULL  ", "bogus", 7, None]:
        probe = {"tools": {"exec": {"mode": m}}}
        status, detail = ns["translate_legacy_exec_mode"](probe)
        table[repr(m)] = {
            "status": status,
            "detail": detail if isinstance(detail, str) else repr(detail),
            "exec": probe["tools"]["exec"],
        }
    # and the no-mode / no-exec / non-dict shapes
    for label, probe in [
        ("no-mode", {"tools": {"exec": {"security": "full", "ask": "off"}}}),
        ("no-exec", {"tools": {}}),
        ("no-tools", {}),
        ("exec-not-a-dict", {"tools": {"exec": "full"}}),
    ]:
        status, detail = ns["translate_legacy_exec_mode"](probe)
        table[label] = {"status": status, "detail": repr(detail), "exec": None}
    result["table"] = table

json.dump(result, sys.stdout)
DRIVEREOF

# -----------------------------------------------------------------------------
# Fixtures.
# -----------------------------------------------------------------------------
cat > "$SANDBOX/fixture-legacy-full.json" <<'EOF'
{
  "tools": {
    "exec": {
      "mode": "full",
      "timeoutSeconds": 900
    }
  },
  "agents": {
    "defaults": {}
  },
  "plugins": {
    "entries": {}
  },
  "channels": {}
}
EOF

cat > "$SANDBOX/fixture-legacy-bogus.json" <<'EOF'
{
  "tools": {
    "exec": {
      "mode": "wide-open",
      "timeoutSeconds": 900
    }
  },
  "agents": {
    "defaults": {}
  },
  "plugins": {
    "entries": {}
  },
  "channels": {}
}
EOF

cat > "$SANDBOX/fixture-no-mode.json" <<'EOF'
{
  "tools": {
    "exec": {
      "timeoutSeconds": 900
    }
  },
  "agents": {
    "defaults": {}
  },
  "plugins": {
    "entries": {}
  },
  "channels": {}
}
EOF

run_driver() { # <fixture> <mode> -> JSON on stdout
  FLEET_WRITE_DEFAULTS_TOOLS=0 python3 "$SANDBOX/driver.py" \
    "$SANDBOX/block.py" "$1" "$2"
}

# jq is not guaranteed on a fleet box or a bare runner, so read JSON with a
# small python path-walker. It only ever does dict lookups along a dotted path,
# never dynamic expression evaluation, so a fixture can never become executable.
jget() { # <json-file> <dotted.path> -> the value, or __MISSING__
  python3 - "$1" "$2" <<'JGETEOF'
import json
import sys

cur = json.load(open(sys.argv[1], encoding="utf-8"))
for part in sys.argv[2].split("."):
    if isinstance(cur, dict) and part in cur:
        cur = cur[part]
    else:
        print("__MISSING__")
        sys.exit(0)
if isinstance(cur, bool):
    print("True" if cur else "False")
elif isinstance(cur, (dict, list)):
    print(json.dumps(cur, sort_keys=True))
else:
    print(cur)
JGETEOF
}

# -----------------------------------------------------------------------------
hdr "T1 -- legacy mode=\"full\": mode removed, fleet standard applied"
# -----------------------------------------------------------------------------
run_driver "$SANDBOX/fixture-legacy-full.json" merge > "$SANDBOX/out-full.json" 2>"$SANDBOX/err-full.txt"
if [ $? -ne 0 ]; then
  bad "T1: driver crashed: $(head -3 "$SANDBOX/err-full.txt")"
else
  if [ "$(jget "$SANDBOX/out-full.json" cfg.tools.exec.mode)" = "__MISSING__" ]; then
    ok "T1a: tools.exec.mode was removed"
  else
    bad "T1a: tools.exec.mode SURVIVED the merge (this is the defect)"
  fi
  if [ "$(jget "$SANDBOX/out-full.json" cfg.tools.exec.security)" = "full" ] \
     && [ "$(jget "$SANDBOX/out-full.json" cfg.tools.exec.ask)" = "off" ]; then
    ok "T1b: fleet standard security=full ask=off applied"
  else
    bad "T1b: fleet exec ungate not applied"
  fi
  if [ "$(jget "$SANDBOX/out-full.json" cfg.tools.exec.timeoutSeconds)" = "900" ]; then
    ok "T1c: unrelated per-box exec tuning (timeoutSeconds) preserved"
  else
    bad "T1c: unrelated exec keys were clobbered"
  fi
  if jget "$SANDBOX/out-full.json" stdout | grep -q 'translated'; then
    ok "T1d: the translation is announced on stdout (operator-visible)"
  else
    bad "T1d: silent translation -- no log line"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T2 -- translation table matches resolveExecPolicyForMode exactly"
# -----------------------------------------------------------------------------
run_driver "$SANDBOX/fixture-legacy-full.json" table > "$SANDBOX/out-table.json" 2>"$SANDBOX/err-table.txt"
if [ $? -ne 0 ]; then
  bad "T2: driver crashed: $(head -3 "$SANDBOX/err-table.txt")"
else
  # The expected pairs are the gateway's own resolveExecPolicyForMode switch.
  T2_RESULT="$(python3 - "$SANDBOX/out-table.json" <<'T2EOF'
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
t = d["table"]
expected = {
    "'deny'":      ("deny",      "off"),
    "'allowlist'": ("allowlist", "off"),
    "'ask'":       ("allowlist", "on-miss"),
    "'auto'":      ("allowlist", "on-miss"),
    "'full'":      ("full",      "off"),
}
problems = []
for key, (sec, ask) in expected.items():
    row = t.get(key)
    if row is None:
        problems.append("%s missing from table" % key)
        continue
    if row["status"] != "translated":
        problems.append("%s status=%s, expected translated" % (key, row["status"]))
        continue
    e = row["exec"]
    if "mode" in e:
        problems.append("%s still carries mode" % key)
    if e.get("security") != sec or e.get("ask") != ask:
        problems.append("%s -> security=%r ask=%r, expected %r/%r"
                        % (key, e.get("security"), e.get("ask"), sec, ask))

# Case / whitespace tolerance: a hand-edited config is not guaranteed tidy.
row = t.get("'  FULL  '")
if row is None or row["status"] != "translated" or row["exec"].get("security") != "full":
    problems.append("'  FULL  ' not normalised and translated")

# Untranslatable values must be left ALONE, never guessed, never deleted.
for key in ["'bogus'", "7", "None"]:
    row = t.get(key)
    if row is None:
        problems.append("%s missing from table" % key)
        continue
    if row["status"] != "untranslatable":
        problems.append("%s status=%s, expected untranslatable" % (key, row["status"]))
    if "mode" not in row["exec"]:
        problems.append("%s: an uninterpretable mode key was DELETED" % key)

for key, want in [("no-mode", "absent"), ("no-exec", "absent"),
                  ("no-tools", "absent"), ("exec-not-a-dict", "absent")]:
    row = t.get(key)
    if row is None or row["status"] != want:
        problems.append("%s status=%s, expected %s"
                        % (key, (row or {}).get("status"), want))

print("OK" if not problems else "; ".join(problems))
T2EOF
)"
  if [ "$T2_RESULT" = "OK" ]; then
    ok "T2: all five modes, case tolerance, untranslatable and absent shapes"
  else
    bad "T2: $T2_RESULT"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T3 -- the other standards survive a legacy-mode box"
# -----------------------------------------------------------------------------
if [ -s "$SANDBOX/out-full.json" ]; then
  T3_RESULT="$(python3 - "$SANDBOX/out-full.json" <<'T3EOF'
import json
import sys

cfg = json.load(open(sys.argv[1], encoding="utf-8"))["cfg"]
problems = []
ts = cfg.get("tools", {}).get("toolSearch")
if not isinstance(ts, dict) or ts.get("mode") != "directory" or ts.get("enabled") is not True:
    problems.append("tools.toolSearch not {enabled:true, mode:directory}: %r" % (ts,))
wa = cfg.get("plugins", {}).get("entries", {}).get("whatsapp")
if not isinstance(wa, dict) or wa.get("enabled") is not False:
    problems.append("WhatsApp ban not applied: %r" % (wa,))
sub = cfg.get("agents", {}).get("defaults", {}).get("subagents")
if not isinstance(sub, dict) or sub.get("allowAgents") != ["*"]:
    problems.append("subagent ungate not applied: %r" % (sub,))
tg = cfg.get("channels", {}).get("telegram", {}).get("mediaMaxMb")
if tg != 50:
    problems.append("telegram mediaMaxMb not applied: %r" % (tg,))
print("OK" if not problems else "; ".join(problems))
T3EOF
)"
  if [ "$T3_RESULT" = "OK" ]; then
    ok "T3: toolSearch, WhatsApp ban, subagent ungate, telegram cap all applied"
  else
    bad "T3: $T3_RESULT"
  fi
else
  bad "T3: no T1 output to inspect"
fi

# -----------------------------------------------------------------------------
hdr "T4 -- untranslatable mode: skip ONLY tools.exec, apply everything else"
# -----------------------------------------------------------------------------
run_driver "$SANDBOX/fixture-legacy-bogus.json" merge > "$SANDBOX/out-bogus.json" 2>"$SANDBOX/err-bogus.txt"
if [ $? -ne 0 ]; then
  bad "T4: driver crashed: $(head -3 "$SANDBOX/err-bogus.txt")"
else
  T4_RESULT="$(python3 - "$SANDBOX/out-bogus.json" <<'T4EOF'
import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
cfg, out = d["cfg"], d["stdout"]
problems = []
e = cfg.get("tools", {}).get("exec", {})
if e.get("mode") != "wide-open":
    problems.append("an uninterpretable mode was altered/deleted: %r" % (e.get("mode"),))
if "security" in e or "ask" in e:
    problems.append("security/ask were merged onto an untranslatable exec block "
                    "(this is the exact combination the validator rejects): %r" % (e,))
if "WARNING" not in out or "SKIPPED" not in out:
    problems.append("the skip was not announced on stdout")
# ...and every OTHER standard still applied. This is the contract: one bad
# sub-block must never cost the box the rest of the fleet standards.
ts = cfg.get("tools", {}).get("toolSearch")
if not isinstance(ts, dict) or ts.get("mode") != "directory":
    problems.append("toolSearch NOT applied on the skip path: %r" % (ts,))
wa = cfg.get("plugins", {}).get("entries", {}).get("whatsapp")
if not isinstance(wa, dict) or wa.get("enabled") is not False:
    problems.append("WhatsApp ban NOT applied on the skip path")
sub = cfg.get("agents", {}).get("defaults", {}).get("subagents")
if not isinstance(sub, dict) or sub.get("allowAgents") != ["*"]:
    problems.append("subagent ungate NOT applied on the skip path")
print("OK" if not problems else "; ".join(problems))
T4EOF
)"
  if [ "$T4_RESULT" = "OK" ]; then
    ok "T4: exec sub-block skipped, every other standard applied, skip announced"
  else
    bad "T4: $T4_RESULT"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T5 -- no legacy mode key: unchanged behaviour"
# -----------------------------------------------------------------------------
run_driver "$SANDBOX/fixture-no-mode.json" merge > "$SANDBOX/out-nomode.json" 2>"$SANDBOX/err-nomode.txt"
if [ $? -ne 0 ]; then
  bad "T5: driver crashed: $(head -3 "$SANDBOX/err-nomode.txt")"
else
  if [ "$(jget "$SANDBOX/out-nomode.json" cfg.tools.exec.security)" = "full" ] \
     && [ "$(jget "$SANDBOX/out-nomode.json" cfg.tools.exec.ask)" = "off" ] \
     && [ "$(jget "$SANDBOX/out-nomode.json" cfg.tools.exec.mode)" = "__MISSING__" ]; then
    ok "T5a: the healthy majority path is unchanged (security=full, ask=off)"
  else
    bad "T5a: the no-mode path regressed"
  fi
  if ! jget "$SANDBOX/out-nomode.json" stdout | grep -qE 'translated|WARNING'; then
    ok "T5b: no translation noise on a config that has no legacy key"
  else
    bad "T5b: the translation logged on a config with no mode key"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T6 -- ANTI-VACUITY: the PRE-FIX merge really does produce the conflict"
# -----------------------------------------------------------------------------
run_driver "$SANDBOX/fixture-legacy-full.json" prefix > "$SANDBOX/out-prefix.json" 2>"$SANDBOX/err-prefix.txt"
if [ $? -ne 0 ]; then
  bad "T6: driver crashed: $(head -3 "$SANDBOX/err-prefix.txt")"
else
  T6_RESULT="$(python3 - "$SANDBOX/out-prefix.json" <<'T6EOF'
import json
import sys

e = json.load(open(sys.argv[1], encoding="utf-8"))["cfg"]["tools"]["exec"]
if "mode" in e and ("security" in e or "ask" in e):
    print("OK")
else:
    print("the pre-fix merge did NOT reproduce mode+security/ask (%r) -- this "
          "test can no longer distinguish the fix from the defect" % (e,))
T6EOF
)"
  if [ "$T6_RESULT" = "OK" ]; then
    ok "T6: the old code path is still demonstrably broken, so T1/T7 mean something"
  else
    bad "T6: $T6_RESULT"
  fi
fi

# -----------------------------------------------------------------------------
hdr "T7 -- conflict-free invariant over every produced config"
# -----------------------------------------------------------------------------
T7_RESULT="$(python3 - "$SANDBOX/out-full.json" "$SANDBOX/out-bogus.json" "$SANDBOX/out-nomode.json" <<'T7EOF'
import json
import sys

problems = []
for path in sys.argv[1:]:
    try:
        e = json.load(open(path, encoding="utf-8"))["cfg"].get("tools", {}).get("exec")
    except Exception as exc:
        problems.append("%s unreadable (%s)" % (path, exc))
        continue
    if not isinstance(e, dict):
        continue
    # The gateway rule, verbatim: an issue is raised iff mode is present AND at
    # least one of security / ask is present.
    if "mode" in e and ("security" in e or "ask" in e):
        problems.append("%s produced the forbidden combination: %r" % (path, e))
print("OK" if not problems else "; ".join(problems))
T7EOF
)"
if [ "$T7_RESULT" = "OK" ]; then
  ok "T7: no produced tools.exec ever carries mode together with security/ask"
else
  bad "T7: $T7_RESULT"
fi

# -----------------------------------------------------------------------------
hdr "T8 -- REAL VALIDATOR (opportunistic, control-gated)"
# -----------------------------------------------------------------------------
# A negative from this leg is only trustworthy if the instrument is proven to
# discriminate first. Known-bad must FAIL and known-good must PASS on this exact
# transport; if either control misbehaves the leg reports UNDETERMINED rather
# than a pass or a fail it did not earn.
if ! command -v openclaw >/dev/null 2>&1; then
  note "T8: no openclaw CLI on PATH (expected on a CI runner) -- UNDETERMINED, skipped."
  note "T8: the pure-python conflict rule in T7 is the always-on gate."
else
  VCFG="$SANDBOX/validate-probe.json"
  oc_validate() { # <json-string> -> rc
    printf '%s' "$1" > "$VCFG"
    OPENCLAW_CONFIG_PATH="$VCFG" OPENCLAW_CONFIG_READONLY=1 \
      openclaw config validate >/dev/null 2>&1
  }
  CTRL_OK=1
  if oc_validate '{"tools":{"exec":{"security":"full","ask":"off"}}}'; then :; else CTRL_OK=0; fi
  if oc_validate '{"tools":{"exec":{"mode":"full","security":"full","ask":"off"}}}'; then CTRL_OK=0; fi
  if [ "$CTRL_OK" != "1" ]; then
    note "T8: the known-good/known-bad control did NOT discriminate on this CLI"
    note "T8: (OPENCLAW_CONFIG_PATH may be unsupported here) -- UNDETERMINED, skipped."
  else
    ok "T8 control: the real validator discriminates good from bad on this box"
    T8_FAIL=0
    for f in "$SANDBOX/out-full.json" "$SANDBOX/out-nomode.json"; do
      [ -s "$f" ] || continue
      python3 -c '
import json, sys
json.dump(json.load(open(sys.argv[1], encoding="utf-8"))["cfg"], open(sys.argv[2], "w"))
' "$f" "$VCFG"
      if OPENCLAW_CONFIG_PATH="$VCFG" OPENCLAW_CONFIG_READONLY=1 \
           openclaw config validate >/dev/null 2>&1; then
        ok "T8: $(basename "$f") validates against the real OpenClaw schema"
      else
        bad "T8: $(basename "$f") was REJECTED by the real OpenClaw schema"
        T8_FAIL=1
      fi
    done
    # And the pre-fix output must be rejected, or the defect was never real.
    if [ -s "$SANDBOX/out-prefix.json" ]; then
      python3 -c '
import json, sys
json.dump(json.load(open(sys.argv[1], encoding="utf-8"))["cfg"], open(sys.argv[2], "w"))
' "$SANDBOX/out-prefix.json" "$VCFG"
      if OPENCLAW_CONFIG_PATH="$VCFG" OPENCLAW_CONFIG_READONLY=1 \
           openclaw config validate >/dev/null 2>&1; then
        bad "T8: the PRE-FIX config validated clean -- the defect is not reproducible here"
      else
        ok "T8: the PRE-FIX config is rejected by the real schema (defect reproduced)"
      fi
    fi
  fi
fi

# -----------------------------------------------------------------------------
printf '\n----------------------------------------\n'
printf 'fleet-standards-legacy-exec-mode: %d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
