#!/usr/bin/env bash
# qc-assert-legacy-agents-list.sh — v1.0.0
#
# STATIC/LIVE QC INVARIANT: fails when a box's openclaw.json still carries the
# LEGACY `agents.list` array.
#
# EVIDENCE THIS PREVENTS: the 2026.7.2-beta line REJECTS that key outright:
#
#     Gateway failed to start: Invalid config at ~/.openclaw/openclaw.json:
#     agents: Unrecognized key: "list"
#
# The gateway exits 78 (EX_CONFIG) roughly 0.4s after launch. The shipped
# LaunchAgent sets KeepAlive with ThrottleInterval=10, so launchd respawns it
# every ~11s forever — one affected box booted 701 times in 10 days. The
# crash-loop breaker then latches channel auto-start OFF and the box goes
# COMPLETELY DARK: no inbound, no outbound, 24 queued deliveries permanently
# lost on the box this was measured on.
#
# ⚠️ AND IT IS SILENT. The shipped LaunchAgent plist wrote
# StandardErrorPath = /dev/null, so the startup exception was DISCARDED. It
# survived only in /tmp/openclaw/openclaw-<date>.log — which is why ten days of
# investigation walked straight past it. (That plist defect is fixed
# separately; see platform/mac/service-selfheal/. A box provisioned before that
# fix still throws its startup errors away, so this gate must not rely on the
# gateway log to notice anything.)
#
# ⚠️ THE KEY IS ONLY FATAL ON THE NEW LINE. A box on 2026.7.1-2 runs fine WITH
# `agents.list` present. That is exactly what makes this a landmine rather than
# an outage: the box looks healthy right up to the moment a roll moves it onto
# the beta line, and then it dies silently. Detection therefore has to happen
# BEFORE the version changes, not after — see agents_list_gate() in
# update-skills.sh, which is the pre-upgrade gate this script backs.
#
# WHY KEY PRESENCE, NOT VALUE: the gateway's schema validator rejects the
# UNRECOGNIZED KEY. An empty array, a null, a populated array — all of them are
# `agents: Unrecognized key: "list"`. This gate therefore asserts on PRESENCE of
# the key and never on its contents.
#
# ⚠️ THIS SCRIPT DOES NOT MIGRATE. It is an assertion, not a fixer — the same
# split as scripts/qc-assert-provider-timeouts.sh.
#
# ⚠️ `openclaw doctor --fix` IS NOT THE MIGRATION, AND NEVER WAS. That claim is
# now DISPROVEN, measured, not assumed: on 12 boxes the config's SHA-256 was
# BYTE-IDENTICAL before and after a `doctor --fix` run. `openclaw config
# schema` on 2026.7.1 / 2026.7.1-2 reports the `agents` properties as exactly
# ["defaults","list"] — there is no `entries` key for it to migrate TO on
# either build. It also has a measured SIDE EFFECT: on one box it silently
# rewrote `agents.defaults.models` pins. A hand-edit is no better: the transform
# is `agents.list` (array) -> `agents.entries` (object keyed by each agent's
# `id`, with `id` removed from the entry body), and `additionalProperties:
# false` on `agents` makes NO config valid on both schema versions at once — so
# the transform is only ever safe performed atomically, in the exact window of
# the binary change (gateway stopped -> new binary installed -> config
# rewritten -> verified lossless -> gateway restarted). That atomic procedure
# is scripts/oc-atomic-upgrade.sh; it is performed, with a backup and a
# post-migration re-validation, by agents_list_gate() in update-skills.sh.
# Deleting the key by hand is NOT a migration: the legacy array holds agent
# definitions, and this script cannot verify where a given box's definitions
# are supposed to land in the new schema. Guessing that transform would trade a
# loud crash-loop for silent agent loss.
#
# Config resolution (first that applies wins):
#   1. an explicit path passed as $1
#   2. $SMOKE_OC_CONFIG (parity with the other config gates in this family:
#      qc-assert-provider-timeouts.sh, qc-assert-provider-capability-invariants.sh)
#   3. the LIVE box config for this platform — /data/.openclaw/openclaw.json on
#      a VPS (detected by the presence of /data/.openclaw), else
#      $HOME/.openclaw/openclaw.json. This gate is meant to run ON a box, so
#      unlike the pure-static gates the live path is a first-class source.
#   4. a repo-relative fixture path suitable for CI
#      (tests/fixtures/qc-assert-legacy-agents-list/openclaw.json). CI has no
#      live box config, so this is the LAST resort, and its absence is expected
#      to produce UNDETERMINED, not a silent skip.
#
# Exit codes:
#   0  — checked: no legacy `agents.list` key in this config (PASS)
#   1  — checked: the legacy `agents.list` key IS PRESENT (FAIL) — this box
#        will crash-loop on the 2026.7.2-beta line
#   2  — usage error
#   3  — UNDETERMINED: the instrument itself is absent (config file not found,
#        unreadable, or unparseable) — this NEVER collapses into exit 0. An
#        unreadable config is not a clean config.
#
# Usage:
#   bash scripts/qc-assert-legacy-agents-list.sh
#   bash scripts/qc-assert-legacy-agents-list.sh /path/to/openclaw.json
#   bash scripts/qc-assert-legacy-agents-list.sh --quiet
#   SMOKE_OC_CONFIG=/path/to/openclaw.json bash scripts/qc-assert-legacy-agents-list.sh
#
# Wired in:
#   - update-skills.sh agents_list_gate() implements the same detection inline
#     (it must run on the curl|bash path, where no repo checkout exists yet, so
#     it cannot source this file). Any migration triggered from that gate must
#     go through the atomic procedure in scripts/oc-atomic-upgrade.sh, NOT
#     `openclaw doctor --fix` — see the DISPROVEN note above.
#   - shared-utils/fleet_validation_harness.py check `config_schema` runs the
#     same assertion across a whole wave.

set -uo pipefail

QUIET=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    -h|--help)
      sed -n '1,86p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --*) echo "Unknown arg: $1" >&2; exit 2 ;;
    *)
      if [ -n "$CONFIG_ARG" ]; then
        echo "Unknown arg: $1" >&2
        exit 2
      fi
      CONFIG_ARG="$1"
      shift
      ;;
  esac
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-legacy-agents-list] PASS  %s\n' "$*"; }
_fail() { printf '[qc-legacy-agents-list] FAIL  %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-legacy-agents-list] INFO  %s\n' "$*"; }
_undetermined() { printf '[qc-legacy-agents-list] UNDETERMINED  %s\n' "$*" >&2; }

FIXTURE_DEFAULT="$REPO_ROOT/tests/fixtures/qc-assert-legacy-agents-list/openclaw.json"

if [ -d "/data/.openclaw" ]; then
  LIVE_DEFAULT="/data/.openclaw/openclaw.json"
else
  LIVE_DEFAULT="$HOME/.openclaw/openclaw.json"
fi

OC_CONFIG="$CONFIG_ARG"
[ -z "$OC_CONFIG" ] && OC_CONFIG="${SMOKE_OC_CONFIG:-}"
[ -z "$OC_CONFIG" ] && [ -f "$LIVE_DEFAULT" ] && OC_CONFIG="$LIVE_DEFAULT"
[ -z "$OC_CONFIG" ] && OC_CONFIG="$FIXTURE_DEFAULT"

_info "config: $OC_CONFIG"

if [ ! -f "$OC_CONFIG" ]; then
  _undetermined "config file not found: $OC_CONFIG — the legacy agents.list invariant DID NOT RUN. This is not a pass: no config was inspected."
  exit 3
fi

# ─── Read-only single-pass analysis ──────────────────────────────────────────
# The python source is written to a temp file first, THEN run via a plain
# `python3 "$file" ...` command substitution — never a heredoc directly inside
# `$(...)`. bash 3.2 (macOS stock /bin/bash, 3.2.57) has a real parser bug where
# an unbalanced/multi-line `(` inside a heredoc BODY nested inside `$(...)`
# throws off its paren-matching scan for the outer command substitution
# ("unexpected EOF while looking for matching `)'" at PARSE time, before the
# script ever runs). The fleet's Macs run stock /bin/bash 3.2.57 while this
# repo's dev boxes run Homebrew bash 5.x, so a heredoc form that parses fine
# during authoring can abort on every client box. Same two-step, and the same
# reason, as scripts/qc-assert-config-write-chown.sh.
QC_PY_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/qc-legacy-agents-list-analysis.XXXXXX.py")"
cat > "$QC_PY_SCRIPT" <<'PYEOF'
import json
import sys

path = sys.argv[1]

try:
    with open(path, encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print('UNDETERMINED|cannot parse %s as JSON: %s' % (path, e))
    raise SystemExit(0)

if not isinstance(cfg, dict):
    print('UNDETERMINED|%s does not contain a JSON object at the top level' % path)
    raise SystemExit(0)

agents = cfg.get('agents')
if agents is None:
    print('PASS|no `agents` block at all — the legacy `agents.list` key cannot be present')
    raise SystemExit(0)

if not isinstance(agents, dict):
    # A non-object `agents` is its own schema fault, but it is NOT the fault
    # this gate is measuring. Saying PASS here would be a false all-clear.
    print('UNDETERMINED|`agents` is a %s, not an object — cannot determine whether the legacy `list` key is present' % type(agents).__name__)
    raise SystemExit(0)

if 'list' not in agents:
    print('PASS|`agents` block present (%d key(s)) and carries NO legacy `list` key' % len(agents))
    raise SystemExit(0)

val = agents['list']
if isinstance(val, list):
    shape = '%d entr(y/ies)' % len(val)
elif val is None:
    shape = 'null'
else:
    shape = 'a %s' % type(val).__name__
print('FAIL|LEGACY `agents.list` KEY IS PRESENT (%s) — the 2026.7.2-beta line rejects it with `agents: Unrecognized key: "list"` and exits 78 (EX_CONFIG) ~0.4s after start' % shape)
PYEOF
ANALYSIS="$(python3 "$QC_PY_SCRIPT" "$OC_CONFIG" 2>&1)"
PY_RC=$?
rm -f "$QC_PY_SCRIPT"
if [ "$PY_RC" -ne 0 ]; then
  # rc != 0 from the analyzer is a BROKEN INSTRUMENT, not a clean config.
  # Never let it collapse into exit 0.
  _undetermined "python3 analysis failed (rc=$PY_RC) against $OC_CONFIG — the invariant DID NOT RUN. Output: ${ANALYSIS:-<empty>}"
  exit 3
fi

if [ -z "$ANALYSIS" ]; then
  _undetermined "python3 analysis produced no output for $OC_CONFIG — treating as instrument-absent rather than a silent pass."
  exit 3
fi

KIND="${ANALYSIS%%|*}"
DETAIL="${ANALYSIS#*|}"

case "$KIND" in
  PASS)
    _pass "$OC_CONFIG — $DETAIL"
    exit 0
    ;;
  FAIL)
    _fail "$OC_CONFIG — $DETAIL"
    echo "REMEDY: a hand-edit and \`openclaw doctor --fix\` are NOT migrations here --" >&2
    echo "  measured on 12 boxes, doctor --fix left the config's SHA-256 BYTE-IDENTICAL," >&2
    echo "  because \`agents.entries\` is not even an accepted key on the build that" >&2
    echo "  still needs this fix (schema reports [\"defaults\",\"list\"] only), and it has" >&2
    echo "  a measured SIDE EFFECT of rewriting agents.defaults.models on one box." >&2
    echo "  The only safe path is the ATOMIC procedure, run in the SAME window as the" >&2
    echo "  binary change (gateway stopped -> new binary -> config rewritten+verified ->" >&2
    echo "  gateway restarted):" >&2
    echo "    bash scripts/oc-atomic-upgrade.sh --upgrade   # or --dry-run to preview first" >&2
    echo "  DO NOT hand-delete or hand-edit the key. The correct transform is" >&2
    echo "  \`agents.list\` (array) -> \`agents.entries\` (object keyed by each agent's" >&2
    echo "  \`id\`, id removed from the entry body) and it must land in that same upgrade" >&2
    echo "  window: done early, against the still-installed build, it is silently" >&2
    echo "  normalized straight back out within about a minute by a live process that" >&2
    echo "  rewrites this file -- trading this loud crash-loop for silent agent loss." >&2
    exit 1
    ;;
  UNDETERMINED)
    _undetermined "$DETAIL"
    exit 3
    ;;
  *)
    _undetermined "unrecognised analyzer verdict ${KIND:-<empty>} for $OC_CONFIG — refusing to call that a pass."
    exit 3
    ;;
esac
