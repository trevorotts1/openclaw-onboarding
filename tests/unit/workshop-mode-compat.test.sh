#!/usr/bin/env bash
# tests/unit/workshop-mode-compat.test.sh — CAN014 regression.
#
# OpenClaw 2026.10.5 retired Skill Workshop proposals: skills.workshop.autonomous.mode
# accepts only "off" | "auto", and a config holding "propose" is REJECTED so every CLI
# command exits 1. scripts/ensure-burn-guard.sh used to hard-code "propose" and could not
# even read such a config. This runs the REAL script + oc-schema-migrate.py against a fake
# `openclaw` that enforces the same schema rule as the 2026.10.5 binary (measured:
# `openclaw config validate --json` -> allowed ["off","auto"]) and as the older builds.
# Every case below fails on the pre-fix tree.
#   N1 new build, key unset        -> "off" written (old script wrote "propose": rejected)
#   N2 new build, file holds propose -> migrated IN THE FILE to off, one backup, config valid
#   N3 same + retired approvalPolicy/maxPending -> removed too (additionalProperties:false)
#   N4 old build (propose allowed)   -> still "propose"; an existing propose is left alone
#   N5 new build, explicit auto      -> off
#   N6 unmappable value              -> file untouched, ADVISORY, exit 0
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/ensure-burn-guard.sh"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

mkdir -p "$SB/bin"
cat > "$SB/bin/openclaw" <<'PYEOF'
#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
cfg_p = os.path.join(os.environ["HOME"], ".openclaw", "openclaw.json")
ALLOWED = ["off", "auto"] if os.environ["FAKE_BUILD"] == "new" else ["off", "auto", "propose"]
PROPS = ["autonomous", "maxSkillBytes"] if os.environ["FAKE_BUILD"] == "new" else ["autonomous", "maxSkillBytes", "approvalPolicy", "maxPending"]
cfg = json.load(open(cfg_p))
ws = cfg.get("skills", {}).get("workshop", {})
bad = [k for k in ws if k not in PROPS]
mode = ws.get("autonomous", {}).get("mode")
invalid = bool(bad) or (mode is not None and mode not in ALLOWED)
if a[:2] == ["config", "schema"]:   # answers even when the config is invalid (measured)
    print(json.dumps({"properties": {"skills": {"properties": {"workshop": {"additionalProperties": False, "properties": {
        "autonomous": {"properties": {"mode": {"anyOf": [{"type": "string", "const": m} for m in ALLOWED]}}},
        "maxSkillBytes": {}, **{k: {} for k in PROPS if k not in ("autonomous", "maxSkillBytes")}}}}}}}))
    sys.exit(0)
if invalid:                          # the 2026.10.5 behaviour: EVERY other command dies
    print("OpenClaw config is invalid\n  - skills.workshop.autonomous.mode: Invalid input", file=sys.stderr); sys.exit(1)
if a[:2] == ["config", "get"]:
    if mode is None: print("Config path is valid but unset: %s." % a[2]); sys.exit(1)
    print(json.dumps(mode)); sys.exit(0)
if a[:2] == ["config", "set"]:
    if a[3] not in ALLOWED: print("Error: Invalid input (allowed: %s)" % ALLOWED, file=sys.stderr); sys.exit(1)
    cfg.setdefault("skills", {}).setdefault("workshop", {}).setdefault("autonomous", {})["mode"] = a[3]
    json.dump(cfg, open(cfg_p, "w")); sys.exit(0)
if a[:2] == ["cron", "list"]:
    print(json.dumps({"jobs": []})); sys.exit(0)
sys.exit(0)
PYEOF
chmod +x "$SB/bin/openclaw"

# mkbox <name> <skills-json> -> HOME
mkbox() { local h="$SB/$1"; mkdir -p "$h/.openclaw"; echo "{\"skills\": $2}" > "$h/.openclaw/openclaw.json"; echo "$h"; }
run() { HOME="$1" PATH="$SB/bin:$PATH" FAKE_BUILD="$2" BURN_GUARD_WAIT_S=0 bash "$SCRIPT" > "$1/out" 2>&1; echo $? > "$1/rc"; }
ws() { python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1]+'/.openclaw/openclaw.json'))['skills'].get('workshop'), sort_keys=True))" "$1"; }
nbak() { ls "$1/.openclaw/" | grep -c 'openclaw.json.burn-guard-'; }

echo "=== workshop-mode compat (CAN014) ==="
H=$(mkbox n1 '{}'); run "$H" new
[ "$(ws "$H")" = '{"autonomous": {"mode": "off"}}' ] && grep -q "^burn-guard: mode=off," "$H/out" && ok "N1 new build, unset -> off" || bad "N1 $(ws "$H") :: $(cat "$H/out")"

H=$(mkbox n2 '{"workshop": {"autonomous": {"mode": "propose"}}}'); run "$H" new
if [ "$(ws "$H")" = '{"autonomous": {"mode": "off"}}' ] && [ "$(nbak "$H")" = "1" ] && grep -q "^burn-guard: mode=off,.*migrated: skills.workshop.autonomous.mode \"propose\" -> \"off\"" "$H/out" \
   && HOME="$H" PATH="$SB/bin:$PATH" FAKE_BUILD=new openclaw config get skills.workshop.autonomous.mode >/dev/null 2>&1; then
  ok "N2 new build, stale propose -> migrated in file, 1 backup, CLI works again"
else bad "N2 $(ws "$H") backups=$(nbak "$H") :: $(cat "$H/out")"; fi

H=$(mkbox n3 '{"workshop": {"autonomous": {"mode": "propose"}, "approvalPolicy": "x", "maxPending": 5, "maxSkillBytes": 40000}}'); run "$H" new
[ "$(ws "$H")" = '{"autonomous": {"mode": "off"}, "maxSkillBytes": 40000}' ] && ok "N3 retired approvalPolicy/maxPending removed, unrelated key kept" || bad "N3 $(ws "$H") :: $(cat "$H/out")"

H=$(mkbox n4a '{}'); run "$H" old
[ "$(ws "$H")" = '{"autonomous": {"mode": "propose"}}' ] && grep -q "^burn-guard: mode=propose," "$H/out" && ok "N4a old build, unset -> propose (unchanged behaviour)" || bad "N4a $(ws "$H") :: $(cat "$H/out")"
H=$(mkbox n4b '{"workshop": {"autonomous": {"mode": "propose"}, "approvalPolicy": "x"}}'); run "$H" old
[ "$(ws "$H")" = '{"approvalPolicy": "x", "autonomous": {"mode": "propose"}}' ] && [ "$(nbak "$H")" = "0" ] && ok "N4b old build, existing propose left alone (no write, no backup)" || bad "N4b $(ws "$H") :: $(cat "$H/out")"

H=$(mkbox n5 '{"workshop": {"autonomous": {"mode": "auto"}}}'); run "$H" new
[ "$(ws "$H")" = '{"autonomous": {"mode": "off"}}' ] && ok "N5 new build, auto -> off" || bad "N5 $(ws "$H") :: $(cat "$H/out")"

H=$(mkbox n6 '{"workshop": {"autonomous": {"mode": "bogus"}}}'); before="$(ws "$H")"; run "$H" new
[ "$(ws "$H")" = "$before" ] && [ "$(cat "$H/rc")" = "0" ] && [ "$(nbak "$H")" = "0" ] && grep -q "ADVISORY" "$H/out" && ok "N6 unmappable value -> untouched, ADVISORY, exit 0" || bad "N6 $(ws "$H") :: $(cat "$H/out")"

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
