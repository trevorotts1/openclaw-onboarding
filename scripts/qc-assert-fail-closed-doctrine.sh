#!/usr/bin/env bash
# =============================================================================
# qc-assert-fail-closed-doctrine.sh
#
# Asserts N40 — FAIL-CLOSED DEPENDENCY: STOP AT 2, REPORT ONCE, NEVER NARRATE
# THE HUNT — is BOTH shipped in the canonical agent doctrine AND enforced by a
# detector that actually fires.
#
# WHY THIS GATE EXISTS. An agent on a client box hit a fail-closed API and made
# thirteen tool calls in forty-nine seconds, each a differently-worded attempt at
# the same intent. Every automated guard on the fleet stayed silent because they
# all key on the ARGUMENTS — the runtime on (toolName, sha256(params)), the
# always-armed runaway guard on (toolName, argsHash, resultHash), Skill 61's D3 on
# (outcome, tool sequence, target). An agent that rewords defeats all three at
# once, and OpenClaw exposes no per-turn tool-call ceiling to fall back on.
# The agent was OBEYING doctrine: "Blockers — Research Before Giving Up" told it to
# try 5-10 methods and carried no fail-closed exception. N40 is that exception.
#
# ⛔ WHAT THIS GATE REFUSES TO BE. A previous unit test in this repo asserted that a
# safety cap was *defined* and passed green while runtime enforcement was dead.
# Checking that words appear in a markdown file would repeat exactly that mistake,
# so this gate does BOTH halves and the second is the load-bearing one:
#   DOCTRINE half  — the rule is present, un-neutered, and the section it bounds
#                    still carries its bound (a silent un-bounding is the regression
#                    that matters most, because that section CAUSED the incident).
#   ENFORCEMENT half — the SHIPPED D6 detector is RUN against an incident-shaped
#                    burst and must return a P1, and against a healthy high-volume
#                    burst and must return NOTHING. A detector that fires on
#                    everything is not a detector, so the silent control is
#                    asserted with equal weight.
#
# Exit codes:
#   0  — checked: N40 doctrine is present and un-neutered AND the D6 detector
#        fires on the incident shape while staying silent on the healthy control
#        (PASS)
#   1  — checked: the doctrine is missing/neutered, or the detector FAILED to fire
#        on the incident shape, or it fired on the healthy control (FAIL)
#   2  — usage error
#   3  — UNDETERMINED: the instrument itself is absent (AGENTS.md not found or
#        unreadable, python3 absent, or the Skill 61 detector module missing) —
#        this NEVER collapses into exit 0. An uninspectable doctrine is not a
#        clean doctrine.
#
# ⚠️ The absent-file / absent-interpreter case is NOT the same as "checked and
# found clean". Reporting a bare PASS there would be a false all-clear (an empty
# result reads as "no problem found"). This gate reports UNDETERMINED instead,
# with the reason, and exits with a DISTINCT code (3) — never 0.
#
# Doctrine resolution (first that applies wins):
#   1. an explicit path passed as $1
#   2. $SMOKE_AGENTS_MD (parity with the SMOKE_OC_CONFIG override the config gates
#      in this family use)
#   3. the repo-canonical AGENTS.md at <repo root>/AGENTS.md
#
# Wired in:
#   .github/workflows/fail-closed-doctrine-gate.yml
#   tests/unit/fail-closed-doctrine-gate.test.sh
#   Not yet wired into scripts/qc-system-integrity.sh — this is a new gate;
#   wiring it into the box-side aggregator is a separate change.
# =============================================================================

set -uo pipefail

QUIET=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DOC_ARG=""

_pass() { [ "$QUIET" = "0" ] && printf '[qc-fail-closed-doctrine] PASS  %s\n' "$*"; return 0; }
_fail() { printf '[qc-fail-closed-doctrine] FAIL  %s\n' "$*" >&2; return 0; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-fail-closed-doctrine] INFO  %s\n' "$*"; return 0; }
_undetermined() { printf '[qc-fail-closed-doctrine] UNDETERMINED  %s\n' "$*" >&2; return 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    -h|--help)
      sed -n '1,60p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --*) echo "Unknown arg: $1" >&2; exit 2 ;;
    *)
      if [ -n "$DOC_ARG" ]; then
        echo "Unknown arg: $1" >&2
        exit 2
      fi
      DOC_ARG="$1"
      shift
      ;;
  esac
done

AGENTS_MD="$DOC_ARG"
[ -z "$AGENTS_MD" ] && AGENTS_MD="${SMOKE_AGENTS_MD:-}"
[ -z "$AGENTS_MD" ] && AGENTS_MD="$REPO_ROOT/AGENTS.md"

_info "doctrine: $AGENTS_MD"

if [ ! -f "$AGENTS_MD" ]; then
  _undetermined "doctrine file not found: $AGENTS_MD — the N40 invariant DID NOT RUN. This is not a pass: no doctrine was inspected."
  exit 3
fi
if [ ! -r "$AGENTS_MD" ]; then
  _undetermined "doctrine file not readable: $AGENTS_MD — the N40 invariant DID NOT RUN."
  exit 3
fi
if ! command -v python3 >/dev/null 2>&1; then
  _undetermined "python3 is not on PATH — the N40 invariant DID NOT RUN. A missing interpreter is not a clean doctrine."
  exit 3
fi

# ─── DOCTRINE half ───────────────────────────────────────────────────────────
# The python source is written to a temp file first, THEN run via a plain
# `python3 "$file" ...` command substitution — never a heredoc directly inside
# `$(...)`. bash 3.2 (macOS stock /bin/bash, 3.2.57) has a real parser bug where
# an unbalanced/multi-line `(` inside a heredoc BODY nested inside `$(...)`
# throws off its paren-matching scan for the outer command substitution
# ("unexpected EOF while looking for matching `)'" at PARSE time, before the
# script ever runs). The fleet's Macs run stock /bin/bash 3.2.57 while this
# repo's dev boxes run Homebrew bash 5.x, so a heredoc form that parses fine
# during authoring can abort on every client box. Same two-step, and the same
# reason, as scripts/qc-assert-legacy-agents-list.sh.
QC_PY_DOC="$(mktemp "${TMPDIR:-/tmp}/qc-fail-closed-doctrine.XXXXXX.py")"
cat > "$QC_PY_DOC" <<'PYEOF'
import io
import sys

path = sys.argv[1]
try:
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
except (IOError, OSError) as exc:
    print("UNDETERMINED|could not read %s (%s)" % (path, type(exc).__name__))
    sys.exit(0)

if not text.strip():
    print("UNDETERMINED|%s is empty" % path)
    sys.exit(0)

low = text.lower()

# Each requirement is (label, [accepted spellings]). A rule that can be satisfied
# by only one exact string would fail on a harmless rewording; a rule satisfied by
# any loose word would not detect neutering. These are the load-bearing CLAUSES.
required = [
    ("the FAIL_CLOSED_DEPENDENCY_V1 idempotency marker",
     ["fail_closed_dependency_v1"]),
    ("the N40 rule heading",
     ["n40 — fail-closed dependency", "n40 - fail-closed dependency"]),
    ("the 2-attempt ceiling",
     ["at most 2 attempts", "stop after at most 2", "stop at 2"]),
    ("the one-message rule",
     ["exactly one message"]),
    ("the never-narrate rule",
     ["never narrate a discovery hunt", "never narrate the hunt"]),
    ("the rewording-is-not-progress clause",
     ["rewording is not a new approach"]),
    ("the N40 bound on the Blockers section",
     ["bounded by n40"]),
    ("the N40 row in the canonical non-negotiables index",
     ["| n40 |"]),
]

missing = []
for label, spellings in required:
    if not any(s in low for s in spellings):
        missing.append(label)

if missing:
    print("FAIL|%s" % "; ".join(missing))
    sys.exit(0)

# The Blockers section must still be BOUNDED, and the bound must come FIRST
# inside that section. The incident happened because that section told the agent
# to try 5-10 methods with no fail-closed exception, so a future edit that drops
# the bound (or pushes it below the instruction) re-opens the exact hole.
#
# This is scoped to the Blockers SECTION deliberately. A whole-file
# first-occurrence comparison is wrong: other parts of the doctrine legitimately
# quote the "5-10 methods" phrase while describing the rule, and that would make
# the gate fail on correct content.
sec_start = low.find("### blockers")
if sec_start == -1:
    print("FAIL|the 'Blockers - Research Before Giving Up' section is GONE from "
          "the doctrine - N40 exists to bound it, so its removal or renaming "
          "silently un-scopes the rule and must be reviewed deliberately")
    sys.exit(0)

# Section runs to the next heading of the same or higher level.
sec_end = len(low)
probe = sec_start
while True:
    nxt = low.find("\n#", probe + 1)
    if nxt == -1:
        break
    # only a heading at '### ' or shallower ends the section
    line_end = low.find("\n", nxt + 1)
    heading = low[nxt + 1:line_end if line_end != -1 else len(low)]
    hashes = len(heading) - len(heading.lstrip("#"))
    if hashes <= 3:
        sec_end = nxt
        break
    probe = nxt

section = low[sec_start:sec_end]
bound_at = section.find("bounded by n40")
five_ten = section.find("5-10 methods")
if bound_at == -1:
    print("FAIL|the Blockers section carries NO 'bounded by N40' notice - the "
          "unbounded 'try 5-10 methods' instruction is exactly what produced 13 "
          "reworded tool calls in 49 seconds on a client box")
    sys.exit(0)
if five_ten != -1 and bound_at > five_ten:
    print("FAIL|inside the Blockers section the 'bounded by N40' notice appears "
          "AFTER the 5-10 methods instruction - an agent reading in order hits "
          "the unbounded rule first")
    sys.exit(0)

print("PASS|N40 doctrine present: 2-attempt ceiling, one-message rule, "
      "never-narrate rule, rewording clause, Blockers bound, and index row")
PYEOF

DOC_ANALYSIS="$(python3 "$QC_PY_DOC" "$AGENTS_MD" 2>&1)"
DOC_RC=$?
rm -f "$QC_PY_DOC"

if [ "$DOC_RC" -ne 0 ]; then
  _undetermined "python3 doctrine analysis failed (rc=$DOC_RC) against $AGENTS_MD — the invariant DID NOT RUN. Output: ${DOC_ANALYSIS:-<empty>}"
  exit 3
fi
if [ -z "$DOC_ANALYSIS" ]; then
  _undetermined "python3 doctrine analysis produced no output for $AGENTS_MD — treating as instrument-absent rather than a silent pass."
  exit 3
fi

DOC_KIND="${DOC_ANALYSIS%%|*}"
DOC_DETAIL="${DOC_ANALYSIS#*|}"

case "$DOC_KIND" in
  PASS)
    _pass "$AGENTS_MD — $DOC_DETAIL"
    ;;
  FAIL)
    _fail "$AGENTS_MD — N40 doctrine is missing or neutered: $DOC_DETAIL"
    echo "REMEDY: restore the N40 section and its canonical index row in AGENTS.md." >&2
    echo "  N40 is the ONLY thing that stops a fail-closed retry loop while it is happening —" >&2
    echo "  Skill 61's D6 detector reports on a 15-minute tick, long after a client has already" >&2
    echo "  watched the agent narrate a hunt. Do NOT 'fix' this by weakening the assertion." >&2
    echo "  If the Blockers bound is what went missing: that section told an agent to try 5-10" >&2
    echo "  methods with no fail-closed exception, and that is what produced 13 reworded tool" >&2
    echo "  calls in 49 seconds on a client box. The bound is not decoration." >&2
    exit 1
    ;;
  UNDETERMINED)
    _undetermined "$DOC_DETAIL"
    exit 3
    ;;
  *)
    _undetermined "unrecognised doctrine verdict ${DOC_KIND:-<empty>} for $AGENTS_MD — refusing to call that a pass."
    exit 3
    ;;
esac

# ─── DELIVERY half ───────────────────────────────────────────────────────────
# Doctrine that never reaches a box is decoration. The repo-root AGENTS.md is the
# operator's canonical document and NOTHING copies it to a client box —
# link_shared_core_files() fans a box's OWN workspace AGENTS.md out to that box's
# other agent workspaces; it never pulls from the repo. The ONLY vehicle that puts
# new rule text on a live box is a marker-guarded injection in
# apply-fleet-standards.sh, which the update path runs on both the full pass and
# the converged fast-path.
#
# This is not hypothetical: NATIVE_SKILL_INVOCATION_V1 sits in AGENTS.md with no
# injection anywhere, so N39's text reaches no existing box. N40 must not repeat
# that. Same assertion shape as the D17 step in both-paths-delivery-guard.yml.
DELIVERY_SCRIPT="$REPO_ROOT/scripts/apply-fleet-standards.sh"
DELIVERY_MISSING=""

if [ ! -f "$DELIVERY_SCRIPT" ]; then
  _undetermined "scripts/apply-fleet-standards.sh not found — the DELIVERY half DID NOT RUN. Cannot tell whether N40 reaches a box."
  exit 3
fi

grep -q 'FAIL_CLOSED_DEPENDENCY_V1' "$DELIVERY_SCRIPT" \
  || DELIVERY_MISSING="$DELIVERY_MISSING no-injection-stanza"
grep -q 'apply-fleet-standards' "$REPO_ROOT/update-skills.sh" 2>/dev/null \
  || DELIVERY_MISSING="$DELIVERY_MISSING update-skills:not-invoked"
grep -q 'apply-fleet-standards.sh' "$REPO_ROOT/install.sh" 2>/dev/null \
  || DELIVERY_MISSING="$DELIVERY_MISSING install:not-invoked"

if [ -n "$DELIVERY_MISSING" ]; then
  _fail "N40 has no delivery path to a live box:$DELIVERY_MISSING"
  echo "REMEDY: a rule in the repo's AGENTS.md reaches ZERO existing boxes on its own." >&2
  echo "  Nothing copies repo AGENTS.md to a client box — link_shared_core_files() fans the" >&2
  echo "  BOX's own workspace AGENTS.md out to that box's other agents, and never pulls from" >&2
  echo "  the repo. Add/restore the marker-guarded FAIL_CLOSED_DEPENDENCY_V1 stanza in" >&2
  echo "    scripts/apply-fleet-standards.sh   (see section 5c-N40)" >&2
  echo "  NATIVE_SKILL_INVOCATION_V1 is the cautionary case: present in AGENTS.md, injected" >&2
  echo "  by nothing, and therefore live on no box." >&2
  exit 1
fi
_pass "delivery — FAIL_CLOSED_DEPENDENCY_V1 is injected by apply-fleet-standards.sh, which both install.sh and update-skills.sh invoke"

# ─── ENFORCEMENT half ────────────────────────────────────────────────────────
# The half that actually matters. Asserting "the detector is defined" proves
# nothing; this RUNS the shipped detector and asserts on its OBSERVED verdicts,
# in BOTH directions.
DETECTOR_DIR="$REPO_ROOT/61-loop-protection-system/scripts"
if [ ! -f "$DETECTOR_DIR/loop_detectors.py" ]; then
  _undetermined "Skill 61 detector module not found at $DETECTOR_DIR/loop_detectors.py — the D6 ENFORCEMENT half DID NOT RUN. Doctrine text alone is not enforcement."
  exit 3
fi

QC_PY_ENF="$(mktemp "${TMPDIR:-/tmp}/qc-fail-closed-enforce.XXXXXX.py")"
cat > "$QC_PY_ENF" <<'PYEOF'
import sys

sys.path.insert(0, sys.argv[1])
try:
    import loop_common as C
    import loop_detectors as D
except Exception as exc:  # noqa: BLE001 - a broken import is an absent instrument
    print("UNDETERMINED|could not import the Skill 61 detectors (%s: %s)"
          % (type(exc).__name__, exc))
    sys.exit(0)

try:
    th = C.load_skill_config("thresholds.json")
    sig = C.load_signatures()
except Exception as exc:  # noqa: BLE001
    print("UNDETERMINED|could not load Skill 61 config (%s: %s)"
          % (type(exc).__name__, exc))
    sys.exit(0)

if not hasattr(D, "d6_futile_retry_burst"):
    print("FAIL|the D6 detector d6_futile_retry_burst is ABSENT from loop_detectors")
    sys.exit(0)
if "d6_futile_retry_burst" not in th:
    print("FAIL|thresholds.json carries no d6_futile_retry_burst block - the "
          "detector cannot be tuned and will raise at runtime")
    sys.exit(0)

problems = []

# (1) THE INCIDENT SHAPE. 13 calls in 49s against a fail-closed dependency, every
# call carrying DISTINCT arguments and every call SUCCEEDING at the tool layer
# (errors=0) - a curl against a refusing API exits 0. This must be a P1.
incident = [{"unit": "session:gate-incident", "tool": "exec", "calls": 13,
             "errors": 0, "failclosed": 6, "span_seconds": 49.0}]
try:
    got = D.d6_futile_retry_burst(incident, th, sig)
except Exception as exc:  # noqa: BLE001
    print("UNDETERMINED|D6 raised on the incident fixture (%s: %s)"
          % (type(exc).__name__, exc))
    sys.exit(0)
if not got:
    problems.append("D6 did NOT fire on the incident shape (13 calls / 49s / 6 "
                    "fail-closed refusals) - the guard is DEAD")
elif got[0].get("severity") != "P1":
    problems.append("D6 fired at %s on the incident shape, expected P1"
                    % got[0].get("severity"))
elif got[0].get("loop_class") != "LP-A9":
    problems.append("D6 classified the incident as %s, expected LP-A9"
                    % got[0].get("loop_class"))

# (2) THE SILENT CONTROL, asserted with equal weight. A REAL measured burst from
# the operator box's own corpus: 460 exec calls in 48.2 seconds, 35x the
# incident's volume, with nothing futile about it. A detector that fires here is
# not a detector, and a count-only design (the obvious one) fires here.
healthy = [{"unit": "session:gate-healthy", "tool": "exec", "calls": 460,
            "errors": 0, "failclosed": 0, "span_seconds": 48.2}]
try:
    quiet = D.d6_futile_retry_burst(healthy, th, sig)
except Exception as exc:  # noqa: BLE001
    print("UNDETERMINED|D6 raised on the control fixture (%s: %s)"
          % (type(exc).__name__, exc))
    sys.exit(0)
if quiet:
    problems.append("D6 FIRED on the healthy 460-call control burst (%s) - it is "
                    "counting volume instead of futility and will bury real "
                    "findings in false positives" % quiet[0].get("severity"))

# (3) THE DOCTRINE BOUNDARY. The rule permits 2 attempts; the detector must agree,
# or the written rule and the machine drift apart.
allowed = [{"unit": "session:gate-two", "tool": "exec", "calls": 2, "errors": 0,
            "failclosed": 2, "span_seconds": 4.0}]
if D.d6_futile_retry_burst(allowed, th, sig):
    problems.append("D6 fired on 2 fail-closed attempts, which N40 explicitly "
                    "ALLOWS - detector and doctrine disagree")
past = [{"unit": "session:gate-three", "tool": "exec", "calls": 3, "errors": 0,
         "failclosed": 3, "span_seconds": 7.0}]
if not D.d6_futile_retry_burst(past, th, sig):
    problems.append("D6 stayed silent on the 3rd fail-closed attempt, which N40 "
                    "forbids - the doctrine ceiling is not enforced")

if problems:
    print("FAIL|%s" % "; ".join(problems))
    sys.exit(0)

print("PASS|D6 fires P1/LP-A9 on the incident shape, stays SILENT on the real "
      "460-call healthy control, allows 2 attempts and flags the 3rd")
PYEOF

ENF_ANALYSIS="$(python3 "$QC_PY_ENF" "$DETECTOR_DIR" 2>&1)"
ENF_RC=$?
rm -f "$QC_PY_ENF"

if [ "$ENF_RC" -ne 0 ]; then
  _undetermined "python3 enforcement analysis failed (rc=$ENF_RC) — the D6 ENFORCEMENT half DID NOT RUN. Output: ${ENF_ANALYSIS:-<empty>}"
  exit 3
fi
if [ -z "$ENF_ANALYSIS" ]; then
  _undetermined "python3 enforcement analysis produced no output — treating as instrument-absent rather than a silent pass."
  exit 3
fi

ENF_KIND="${ENF_ANALYSIS%%|*}"
ENF_DETAIL="${ENF_ANALYSIS#*|}"

case "$ENF_KIND" in
  PASS)
    _pass "D6 enforcement — $ENF_DETAIL"
    _pass "N40 doctrine is shipped AND its detector demonstrably fires."
    exit 0
    ;;
  FAIL)
    _fail "D6 enforcement is broken — $ENF_DETAIL"
    echo "REMEDY: the N40 doctrine text can be perfectly present while the detector behind" >&2
    echo "  it does nothing. That combination is worse than no gate, because the repo then" >&2
    echo "  reports a covered invariant. Fix the detector in" >&2
    echo "    61-loop-protection-system/scripts/loop_detectors.py (d6_futile_retry_burst)" >&2
    echo "  and its thresholds in 61-loop-protection-system/config/thresholds.json," >&2
    echo "  then re-run. Do NOT relax the healthy-control assertion to make this pass:" >&2
    echo "  the 460-call control is REAL measured traffic, and a detector that flags it" >&2
    echo "  would fire on roughly a quarter of healthy sessions." >&2
    exit 1
    ;;
  UNDETERMINED)
    _undetermined "$ENF_DETAIL"
    exit 3
    ;;
  *)
    _undetermined "unrecognised enforcement verdict ${ENF_KIND:-<empty>} — refusing to call that a pass."
    exit 3
    ;;
esac
