#!/usr/bin/env bash
# tests/unit/intake-bootstrap-pending-state.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for hardening-plan ITEM 06 — "Intake and bootstrap propagate
# precise pending state".
#
# Defects this locks shut:
#   * Step 15c seeded a `pending+<slug>@zerohumanworkforce.com` placeholder as
#     the client's contactEmail — an invented sign-in identity that
#     register-access would later refuse anyway (exit 8 after side effects).
#   * A pre-existing checkout / registered pm2 app / bound port printed
#     "bootstrap trigger skipped" and RETURNED ZERO — no inspection, no resume,
#     no pending state: a silent green.
#   * The child's exit 8 (launch-pending) and fatal exits were swallowed by an
#     unconditional `return 0`, so the final summary printed
#     "INSTALL COMPLETED CLEANLY" over a pending/failed launch.
#
# It executes the REAL functions EXTRACTED FROM install.sh (bootstrap shell,
# resume helper, final summary) against shimmed git/pm2/lsof/ps and a fake
# run-full-install.sh that records its argv and returns a chosen exit code —
# plus the REAL interview-launch.initialize() for the placeholder/conflict/
# identity-preservation contract.
#
# Fully offline/hermetic (mktemp sandbox). Exit 0 = all pass, 1 = failure.
# bash 3.2-safe: no assoc arrays, no mapfile, no ${x,,}.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
LAUNCH_PY="$REPO_ROOT/32-command-center-setup/scripts/interview-launch.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== intake-bootstrap-pending-state.test.sh (item 06) ==="

for f in "$INSTALL_SH" "$LAUNCH_PY"; do
  [ -f "$f" ] || { echo "  FAIL: required file not found: $f"; exit 1; }
done
command -v python3 >/dev/null 2>&1 || { echo "  FAIL: python3 not on PATH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── Extract the REAL functions out of install.sh (not copies) ────────────────
EXTRACT_RC=0
extract_fn() { # extract_fn <name>
  python3 - "$INSTALL_SH" "$1" <<'INNERPY'
import re, sys
s = open(sys.argv[1]).read()
name = sys.argv[2]
i = s.find(name + "() {")
if i < 0:
    sys.stderr.write("could not find %s in install.sh\n" % name); sys.exit(3)
m = re.search(r"^\}$", s[i:], re.M)
if m is None:
    sys.stderr.write("could not find the closing } of %s\n" % name); sys.exit(3)
sys.stdout.write(s[i:i + m.end()] + "\n")
INNERPY
}
{
  extract_fn "bootstrap_command_center_shell" || EXTRACT_RC=$?
  extract_fn "_bccs_resume" || EXTRACT_RC=$?
  extract_fn "print_install_summary" || EXTRACT_RC=$?
} > "$WORK/fn.sh" 2>"$WORK/extract.err"
if [ "$EXTRACT_RC" -ne 0 ]; then
  fail "could not extract install.sh functions: $(cat "$WORK/extract.err")"
  echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1
fi
grep -q '^bootstrap_command_center_shell()' "$WORK/fn.sh" \
  && grep -q '^_bccs_resume()' "$WORK/fn.sh" \
  && grep -q '^print_install_summary()' "$WORK/fn.sh" \
  && pass "extracted the live bootstrap, resume and summary functions from install.sh" \
  || { fail "extraction incomplete"; echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1; }

# The bootstrap must no longer fabricate a placeholder identity.
if grep -q 'pending+${_bccs_slug}@zerohumanworkforce.com' "$WORK/fn.sh"; then
  fail "bootstrap still INVENTS a pending+ placeholder address"
else
  pass "bootstrap never fabricates a pending+ placeholder address"
fi
if grep -qE 'bootstrap trigger skipped' "$WORK/fn.sh"; then
  fail "bootstrap still prints a silent 'skipped' claim"
else
  pass "bootstrap has no silent 'skipped' claim left"
fi

# ── Harness: sandboxed boxes, shims, fake child installer ────────────────────
SKILLS_DIR="$WORK/skills"
CC_DIR="$WORK/box/projects/command-center"
mkdir -p "$SKILLS_DIR/32-command-center-setup/scripts" "$CC_DIR" "$WORK/bin" "$WORK/box"
LOG_FILE="$WORK/install.log"
OC_CONFIG="$WORK/box/openclaw.json"
OC_WORKSPACE_DEFAULT="$WORK/box/workspace"
mkdir -p "$OC_WORKSPACE_DEFAULT"
: > "$LOG_FILE"; : > "$OC_CONFIG"

# Fake run-full-install.sh: records argv, returns $FAKE_CHILD_RC.
cat > "$SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" > "$FAKE_CHILD_ARGS"
exit "${FAKE_CHILD_RC:-0}"
STUB
chmod +x "$SKILLS_DIR/32-command-center-setup/scripts/run-full-install.sh"
export FAKE_CHILD_ARGS="$WORK/child.args"

# Shims. Each fixture flips an env switch; defaults describe a FRESH box.
cat > "$WORK/bin/git" <<'STUB'
#!/usr/bin/env bash
# `git -C DIR remote get-url origin`
if [ "${FIX_CHECKOUT:-0}" = "1" ]; then
  echo "https://github.com/trevorotts1/blackceo-command-center.git"
else
  echo "https://example.com/not-command-center.git"
fi
STUB
cat > "$WORK/bin/pm2" <<'STUB'
#!/usr/bin/env bash
# `pm2 id <name>` — prints the id array as its LAST line.
if [ "${FIX_PM2_RUNNING:-0}" = "1" ]; then echo "[ 0 ]"; else echo "[]"; fi
STUB
cat > "$WORK/bin/lsof" <<'STUB'
#!/usr/bin/env bash
# Only report a listener when the fixture says port 4000 is bound; otherwise
# exit non-zero exactly like a real `lsof` with no match.
[ "${FIX_PORT_BOUND:-0}" = "1" ] || exit 1
echo "${FIX_PORT_PID:-99999}"
STUB
cat > "$WORK/bin/ps" <<'STUB'
#!/usr/bin/env bash
# -o command= -p PID  (ownership test) and -o comm= -p PID (display)
if [ "${FIX_PORT_OWNER:-}" = "cc" ]; then
  echo "bash /opt/cc/scripts/cc-start.sh --port 4000"
elif [ "${FIX_PORT_OWNER:-}" = "node" ]; then
  echo "/opt/homebrew/bin/next-server (v16.3.8)"
else
  echo "/usr/sbin/unrelated-daemon"
fi
STUB
chmod +x "$WORK/bin/"*
export PATH="$WORK/bin:$PATH"

note() { printf 'note: %s\n' "$1" >> "$LOG_FILE"; }
warn() { printf 'warn: %s\n' "$1" >> "$LOG_FILE"; }
success() { printf 'success: %s\n' "$1" >> "$LOG_FILE"; }
error() { printf 'error: %s\n' "$1" >> "$LOG_FILE"; }
step() { :; }

# shellcheck disable=SC1090
. "$WORK/fn.sh" || { fail "extracted functions failed to source"; echo ""; echo "  RESULT: $PASS passed, $FAIL failed"; exit 1; }

reset_box() {
  rm -f "$FAKE_CHILD_ARGS"
  : > "$LOG_FILE"
  unset FIX_CHECKOUT FIX_PM2_RUNNING FIX_PORT_BOUND FIX_PORT_PID FIX_PORT_OWNER FAKE_CHILD_RC 2>/dev/null || true
  rm -rf "$CC_DIR"; mkdir -p "$CC_DIR"
  export OPENCLAW_COMPANY_SLUG="acme" OPENCLAW_COMPANY_NAME="Acme Co" OPENCLAW_OWNER_EMAIL=""
  # The functions derive their checkout from CC_APP_DIR first — pin it to the
  # sandbox so nothing ever inspects the real machine's Command Center.
  export CC_APP_DIR="$CC_DIR"
}
run_bootstrap() { # prints the function's rc
  local rc=0
  ( bootstrap_command_center_shell ) >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
child_ran() { [ -f "$FAKE_CHILD_ARGS" ]; }
child_args() { cat "$FAKE_CHILD_ARGS" 2>/dev/null || true; }

# ── Fixture: missing intake → pending 8, no child, no install ────────────────
reset_box
OPENCLAW_COMPANY_SLUG="" OPENCLAW_COMPANY_NAME=""
rc="$(run_bootstrap)"
[ "$rc" = "8" ] && pass "missing intake -> rc 8 (pending), never 0" \
  || fail "missing intake -> rc $rc (expected 8)"
if child_ran; then fail "missing intake still invoked the child installer"
else pass "missing intake never invokes the child installer"
fi

# ── Fixture: healthy existing checkout → INSPECT + canonical RESUME ──────────
reset_box
FIX_CHECKOUT=1; export FIX_CHECKOUT
mkdir -p "$CC_DIR/.git"; printf '{"name":"cc"}\n' > "$CC_DIR/package.json"
rc="$(run_bootstrap)"
if child_ran; then pass "existing checkout triggers the canonical child (resume, not skip)"
else fail "existing checkout did not invoke the child"
fi
case "$(child_args)" in
  *--resume*) pass "existing checkout resumes with --resume (re-runs the launch gates)" ;;
  *) fail "existing checkout did NOT pass --resume: '$(child_args)'" ;;
esac
case "$(child_args)" in
  *--app-dir*) pass "resume pins --app-dir to the SAME checkout" ;;
  *) fail "resume missing --app-dir: '$(child_args)'" ;;
esac

# ── Fixture: registered pm2 app ("waiting restart") → resume, preserved ─────
reset_box
FIX_PM2_RUNNING=1; export FIX_PM2_RUNNING
rc="$(run_bootstrap)"
if child_ran; then
  case "$(child_args)" in
    *--resume*) pass "waiting-restart pm2 process -> resume of the same install (board/state preserved)" ;;
    *) fail "pm2-present resume missing --resume: '$(child_args)'" ;;
  esac
else
  fail "registered pm2 process did not trigger inspection/resume"
fi
grep -q "client board and saved state preserved" "$LOG_FILE" \
  && pass "pm2-present path states that client board and saved state are preserved" \
  || fail "pm2-present path does not state state preservation"

# ── Fixture: UNRELATED listener on port 4000 → pending 8, nothing touched ───
reset_box
FIX_PORT_BOUND=1 FIX_PORT_PID=7777 FIX_PORT_OWNER=unrelated; export FIX_PORT_BOUND FIX_PORT_PID FIX_PORT_OWNER
rc="$(run_bootstrap)"
[ "$rc" = "8" ] && pass "unrelated port owner -> rc 8 (pending, never success)" \
  || fail "unrelated port owner -> rc $rc (expected 8)"
if child_ran; then fail "unrelated port owner was ADOPTED — child ran against it"
else pass "unrelated port owner left untouched (no resume, no kill, no adoption)"
fi
grep -q "UNRELATED process" "$LOG_FILE" \
  && grep -q "refusing to adopt, restart or kill" "$LOG_FILE" \
  && pass "unrelated owner is refused explicitly in the log" \
  || fail "unrelated-owner refusal not logged"

# ── Fixture: OUR process on 4000 → resume ───────────────────────────────────
reset_box
FIX_PORT_BOUND=1 FIX_PORT_PID=8888 FIX_PORT_OWNER=cc; export FIX_PORT_BOUND FIX_PORT_PID FIX_PORT_OWNER
rc="$(run_bootstrap)"
if child_ran; then
  case "$(child_args)" in
    *--resume*) pass "our own cc-start listener -> resume" ;;
    *) fail "our listener resume missing --resume: '$(child_args)'" ;;
  esac
else
  fail "our own listener did not trigger resume"
fi

# ── Fixture: placeholder intake email → passed as PENDING (no 3rd argument) ──
reset_box
FIX_CHECKOUT=1; export FIX_CHECKOUT
mkdir -p "$CC_DIR/.git"; printf '{"name":"cc"}\n' > "$CC_DIR/package.json"
OPENCLAW_OWNER_EMAIL="pending+acme@zerohumanworkforce.com" export OPENCLAW_OWNER_EMAIL
rc="$(run_bootstrap)"
case "$(child_args)" in
  *pending+*) fail "bootstrap PASSED a pending+ placeholder to the child" ;;
  *) pass "placeholder intake email is never passed as the child's contact email" ;;
esac

# ── Fixture: confirmed email → passed through ───────────────────────────────
# Fresh box (no checkout): the FULL install path passes slug + company + the
# confirmed email. (The resume path deliberately passes none — the state file
# supplies them there, which is why the placeholder case above asserts no third
# argument on that path instead.)
reset_box
OPENCLAW_OWNER_EMAIL="owner@example.com" export OPENCLAW_OWNER_EMAIL
rc="$(run_bootstrap)"
case "$(child_args)" in
  *"owner@example.com"*) pass "confirmed intake email reaches the child as contactEmail (fresh install path)" ;;
  *) fail "confirmed email not passed: '$(child_args)'" ;;
esac
case "$(child_args)" in
  *--resume*) fail "fresh box wrongly took the --resume path" ;;
  *) pass "fresh box runs the full install path (no checkout, no pm2, port free)" ;;
esac

# ── Exit-code propagation: pending 8 and fatal must BOTH surface ─────────────
reset_box
FAKE_CHILD_RC=8; export FAKE_CHILD_RC   # fresh box: no checkout, no pm2, port free
rc="$(run_bootstrap)"
[ "$rc" = "8" ] && pass "child exit 8 propagates as 8 (launch-pending, not swallowed)" \
  || fail "child exit 8 -> bootstrap rc $rc (expected 8)"
reset_box
FAKE_CHILD_RC=3; export FAKE_CHILD_RC
rc="$(run_bootstrap)"
[ "$rc" = "3" ] && pass "fatal child exit 3 propagates as 3 (never 0)" \
  || fail "fatal child exit 3 -> rc $rc (expected 3)"
reset_box
FAKE_CHILD_RC=0; export FAKE_CHILD_RC
rc="$(run_bootstrap)"
[ "$rc" = "0" ] && pass "healthy child exit 0 propagates as 0" \
  || fail "healthy child -> rc $rc (expected 0)"
grep -q "provider turn, invitation delivery and interview completion remain three separate checks" "$LOG_FILE" \
  && pass "success wording keeps provider turn / delivery / completion as separate facts" \
  || fail "success wording no longer separates the three facts"

# ── Final summary: a pending child can NEVER print the CLEANLY claim ─────────
summary_out() { # summary_out <INSTALL_EXIT_CODE>
  INSTALL_EXIT_CODE="$1" bash -c '
    LOG_FILE="'"$LOG_FILE"'"; INSTALL_EXIT_CODE="'"$1"'"
    note(){ :; }; warn(){ :; }; success(){ :; }; error(){ :; }; step(){ :; }
    . "'"$WORK"'/fn.sh"
    print_install_summary' 2>&1
}
# empty log: nothing went wrong, but the CHILD was pending
: > "$LOG_FILE"
out="$(summary_out 8)"
printf '%s' "$out" | grep -q "INSTALL COMPLETED CLEANLY" \
  && fail "pending child (exit 8) still printed INSTALL COMPLETED CLEANLY" \
  || pass "pending child never prints INSTALL COMPLETED CLEANLY"
printf '%s' "$out" | grep -q "LAUNCH PENDING (child exit 8)" \
  && pass "summary reports COMMAND CENTER LAUNCH PENDING for exit 8" \
  || fail "summary missing the launch-pending block"
printf '%s' "$out" | grep -q "NOT complete" \
  && pass "pending summary explicitly states the interview is NOT complete" \
  || fail "pending summary does not forbid a completion claim"

# fatal child rc
out="$(summary_out 3)"
printf '%s' "$out" | grep -q "INSTALL COMPLETED CLEANLY" \
  && fail "fatal child (exit 3) still printed INSTALL COMPLETED CLEANLY" \
  || pass "fatal child never prints INSTALL COMPLETED CLEANLY"
printf '%s' "$out" | grep -q "BOOTSTRAP FAILED (exit 3)" \
  && pass "summary reports BOOTSTRAP FAILED with the fatal code" \
  || fail "summary missing the fatal block"

# clean run still earns the claim
: > "$LOG_FILE"
out="$(summary_out 0)"
printf '%s' "$out" | grep -q "INSTALL COMPLETED CLEANLY" \
  && pass "a clean child (exit 0, no errors/warnings) still earns the CLEANLY claim" \
  || fail "clean run lost the CLEANLY claim"

# warnings in the log suppress CLEANLY even with child rc 0
printf '  ⚠️  something warned\n' >> "$LOG_FILE"
out="$(summary_out 0)"
printf '%s' "$out" | grep -q "INSTALL COMPLETED CLEANLY" \
  && fail "a logged warning did not suppress the CLEANLY claim" \
  || pass "a logged warning suppresses the CLEANLY claim"

# ── interview-launch.initialize(): placeholder-only replacement, conflict ─────
py_probe() { # py_probe <script-body> -> prints "OK" | failure text
  python3 - "$LAUNCH_PY" "$WORK" <<INNERPY
import json, sys, importlib.util, uuid, pathlib
spec = importlib.util.spec_from_file_location("il", sys.argv[1])
il = importlib.util.module_from_spec(spec); spec.loader.exec_module(il)
work = pathlib.Path(sys.argv[2])
state = work / "state.json"
state.write_text(json.dumps({
    "companySlug": "acme", "clientSlug": "acme", "companyName": "Acme Co",
    "companyId": "c-1111", "tenantId": "t-2222", "installationId": "i-3333",
    "launchBootstrap": {"version": 1, "status": "identity-allocated"},
    "answers": {"q1": "saved-answer", "q2": 42},
}))
env = {"MC_COMPANY_ID": "c-1111", "MC_TENANT_ID": "t-2222", "MC_INSTALLATION_ID": "i-3333"}
try:
    # 1) absent email -> pending, nothing invented
    il.initialize(state, "acme", "Acme Co", "", dict(env))
    s1 = json.loads(state.read_text())
    assert not s1.get("contactEmail"), "absent email must stay absent (pending): %r" % s1.get("contactEmail")
    # 2) confirmed email replaces the placeholder/absent
    il.initialize(state, "acme", "Acme Co", "owner@example.com", dict(env))
    s2 = json.loads(state.read_text())
    assert s2["contactEmail"] == "owner@example.com", s2.get("contactEmail")
    # 3) retry with the SAME email is idempotent
    il.initialize(state, "acme", "Acme Co", "owner@example.com", dict(env))
    # 4) a pending+ placeholder can never downgrade a confirmed address
    il.initialize(state, "acme", "Acme Co", "pending+acme@zerohumanworkforce.com", dict(env))
    s4 = json.loads(state.read_text())
    assert s4["contactEmail"] == "owner@example.com", "placeholder downgraded a real address: %r" % s4.get("contactEmail")
    # 5) a DIFFERENT confirmed address is a conflict, refused
    try:
        il.initialize(state, "acme", "Acme Co", "other@example.com", dict(env))
    except ValueError as exc:
        assert "conflict" in str(exc).lower(), exc
    else:
        raise AssertionError("conflicting confirmed email was accepted")
    s5 = json.loads(state.read_text())
    assert s5["contactEmail"] == "owner@example.com", s5.get("contactEmail")
    # 6) retries preserve canonical IDs AND saved answers
    assert (s5["companyId"], s5["tenantId"], s5["installationId"]) == ("c-1111", "t-2222", "i-3333"), "canonical IDs changed"
    assert s5["answers"] == {"q1": "saved-answer", "q2": 42}, "saved answers were not preserved"
    print("OK")
except Exception as exc:
    print(type(exc).__name__ + ": " + str(exc))
    sys.exit(1)
INNERPY
}
out="$(py_probe)"
rc=$?
[ "$rc" = "0" ] && [ "$out" = "OK" ] && pass "initialize: absent->pending, placeholder-only replacement, conflict refusal, IDs+answers preserved across retries" \
  || fail "initialize contract failed: $out"

# ── Static wiring on the shipping files ──────────────────────────────────────
grep -q 'owner-email-pending' "$INSTALL_SH" 2>/dev/null || grep -q 'owner-email-pending' "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && pass "child launch gate classifies a placeholder/absent email as owner-email-pending (exit 8)" \
  || fail "child launch gate has no owner-email-pending classification"
grep -q 'cc_interview_email_pending' "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && pass "child carries the cc_interview_email_pending classifier" \
  || fail "cc_interview_email_pending missing"
grep -q 'never claim completion' "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && pass "pending branch forbids a completion claim in its own wording" \
  || fail "pending branch no longer forbids a completion claim"
grep -q 'email-pending' "$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh" \
  && pass "tunnel registration is gated on a confirmed email (no invented identity in the webhook)" \
  || fail "tunnel registration is not gated on a confirmed email"
grep -q 'INSTALL_EXIT_CODE' "$INSTALL_SH" \
  && pass "install.sh records the child outcome for the final report" \
  || fail "install.sh does not record the child outcome"

echo ""
echo "  RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
