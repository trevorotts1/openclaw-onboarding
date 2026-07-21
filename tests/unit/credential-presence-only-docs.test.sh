#!/usr/bin/env bash
# tests/unit/credential-presence-only-docs.test.sh
#
# Locks FINDING T1-03: documented verification steps printed credential
# CHARACTERS to the terminal. Every one of these steps runs inside an agent
# session, and terminal transcripts, agent logs, chat captures and shell history
# retain whatever is emitted — so a "first ten characters" check is a credential
# disclosure, not a safety measure.
#
# The eight sites this locks (all previously value-emitting):
#   07-kie-setup/INSTALL.md                               echo $KIE_API_KEY | head -c 10
#   22-book-to-persona-.../SKILL.md                       grep GOOGLE_API_KEY secrets/.env
#   22-book-to-persona-.../SKILL.md                       grep OLLAMA_API_KEY secrets/.env
#   37-zhc-closeout/SKILL.md   (security note)            ${NOTION_API_TOKEN:0:8}...
#   37-zhc-closeout/SKILL.md   (post-install checklist)   printenv KIE_API_KEY | head -c 8
#   45-design-intelligence-library/INSTALL.md             openclaw config get env.vars.KIE_API_KEY
#   05-ghl-setup/INSTALL.md                               echo $GOHIGHLEVEL_API_KEY | head -c 10
#   05-ghl-setup/EXAMPLES.md                              echo $GOHIGHLEVEL_API_KEY | head -c 10
#   05-ghl-setup/QC.md         (functional check)         "echo a masked token prefix"
#
# THIS TEST EXECUTES THE SHIPPED TEXT. It does not merely check that a variable
# NAME appears in a file: it extracts the presence-check command lines out of the
# markdown as published, runs them against a unique sentinel credential value,
# and asserts (a) the correct SET / NOT-SET verdict comes back and (b) the
# sentinel appears NOWHERE in stdout, stderr, or a process listing.
#
# Hermetic: temp dirs, stub `openclaw` on PATH, no network, no real credential.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# A value that cannot occur naturally. If any character sequence from this shows
# up in captured output, a credential leaked.
SENTINEL='ZZSENTINELCRED8f3a1c9e4b7dDONOTPRINT'

PASS=0; FAIL=0
ok()  { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# `openclaw` is not installed in CI. Stub it so the Skill 45 snippet exercises
# its real pipeline (command substitution -> tr -> sed) against the sentinel.
mkdir -p "$TMP/bin"
cat > "$TMP/bin/openclaw" <<STUB
#!/usr/bin/env bash
# Stub: mimics \`openclaw config get env.vars.<NAME>\`, echoing the configured value.
if [ -n "\${OC_STUB_VALUE:-}" ]; then printf '%s\n' "\$OC_STUB_VALUE"; else printf 'null\n'; fi
STUB
chmod +x "$TMP/bin/openclaw"
export PATH="$TMP/bin:$PATH"

echo "=== credential checks are presence-only (T1-03) ==="

# ---------------------------------------------------------------------------
# Part 1 — extract the presence-check command lines out of the shipped markdown.
# ---------------------------------------------------------------------------
SITES="$TMP/sites.tsv"
python3 - "$REPO_ROOT" "$SITES" <<'PY'
import re, sys, pathlib

root = pathlib.Path(sys.argv[1])
out  = open(sys.argv[2], "w")

FILES = [
    "07-kie-setup/INSTALL.md",
    "22-book-to-persona-coaching-leadership-system/SKILL.md",
    "37-zhc-closeout/SKILL.md",
    "45-design-intelligence-library/INSTALL.md",
    "05-ghl-setup/INSTALL.md",
    "05-ghl-setup/EXAMPLES.md",
]

# A presence check is a line that decides between SET and NOT-SET.
for rel in FILES:
    p = root / rel
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if "NOT-SET" not in line:
            continue
        s = line.strip()
        if s.startswith(">") or s.startswith("#"):     # prose / callout
            continue
        # Markdown table cell: unescape the pipes the table format requires and
        # take the fenced command out of its backticks.
        if s.startswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", s)]
            cmd = ""
            for c in cells:
                if c.startswith("`") and c.endswith("`") and "NOT-SET" in c:
                    cmd = c[1:-1]
            if not cmd:
                continue
            cmd = cmd.replace(r"\|", "|")
        else:
            m = re.findall(r"`([^`]*NOT-SET[^`]*)`", s)
            cmd = m[0] if m else s
        cmd = cmd.strip()
        if not cmd.startswith("[") and "openclaw config get" not in cmd:
            continue
        # Which variable does this line prove?
        mv = re.search(r'"([A-Z0-9_]+): NOT-SET"', cmd)
        var = mv.group(1) if mv else "?"
        out.write(f"{rel}\t{n}\t{var}\t{cmd}\n")
out.close()
PY

SITE_COUNT="$(wc -l < "$SITES" | tr -d ' ')"
if [[ "$SITE_COUNT" -ge 10 ]]; then
  ok "extracted $SITE_COUNT executable presence checks from the shipped markdown"
else
  bad "only $SITE_COUNT executable presence checks extracted — expected at least 10"
fi

# ---------------------------------------------------------------------------
# Part 2 — run every extracted check twice: credential SET to the sentinel, and
#          credential absent. Assert the verdict, and assert the sentinel never
#          reaches the output.
# ---------------------------------------------------------------------------
LEAKLOG="$TMP/all-output.txt"; : > "$LEAKLOG"

# The harness must not leak the sentinel either, or part 3 measures the harness
# instead of the documented snippets. `declare -x` is a shell BUILTIN: it puts
# the value in the environment without creating a process, so the value never
# reaches any argv. Never `env VAR=value ...` or `bash -c "export VAR=value"` —
# both put the value on a command line where `pgrep -f` can read it.
run_snippet() { # run_snippet <var> <cmd> <set|unset>
  local _v="$1" _c="$2" _mode="$3"
  (
    if [[ "$_mode" == "set" ]]; then
      declare -x "$_v=$SENTINEL"
      declare -x "OC_STUB_VALUE=$SENTINEL"
    else
      unset "$_v"; unset OC_STUB_VALUE
    fi
    bash -c "$_c" 2>&1
  )
}

while IFS=$'\t' read -r rel lineno var cmd; do
  [[ -n "$cmd" ]] || continue
  label="$rel:$lineno ($var)"

  # --- credential present -------------------------------------------------
  out_set="$(run_snippet "$var" "$cmd" set)"
  printf '%s\n' "$out_set" >> "$LEAKLOG"
  case "$out_set" in
    *"$var: SET"*) ok "$label reports SET when the credential is present" ;;
    *) bad "$label did not report SET (got: $out_set)" ;;
  esac
  case "$out_set" in
    *"$SENTINEL"*) bad "$label LEAKED the credential value into its output" ;;
    *) ok "$label emitted no character of the credential value" ;;
  esac

  # --- credential absent --------------------------------------------------
  out_unset="$(run_snippet "$var" "$cmd" unset)"
  printf '%s\n' "$out_unset" >> "$LEAKLOG"
  case "$out_unset" in
    *"$var: NOT-SET"*) ok "$label reports NOT-SET when the credential is absent" ;;
    *) bad "$label did not report NOT-SET (got: $out_unset)" ;;
  esac
done < "$SITES"

# Whole-log sweep: nothing anywhere may contain the sentinel, or any 8-character
# prefix of it (the exact "first N characters" shape this finding is about).
if grep -qF "$SENTINEL" "$LEAKLOG" 2>/dev/null; then
  bad "the sentinel value appears in the captured output log"
else
  ok "sentinel absent from every captured stdout/stderr byte"
fi
PREFIX="${SENTINEL:0:8}"
if grep -qF "$PREFIX" "$LEAKLOG" 2>/dev/null; then
  bad "an 8-character prefix of the sentinel appears in the captured output"
else
  ok "no 8-character prefix of the sentinel appears in the captured output"
fi

# ---------------------------------------------------------------------------
# Part 3 — process-listing proof. Run the checks in a loop while sampling the
#          process table for the sentinel. A value passed on a command line is
#          readable by any local user; presence checks must not do that.
# ---------------------------------------------------------------------------
RUNS=200
(
  for _ in $(seq 1 "$RUNS"); do
    while IFS=$'\t' read -r rel lineno var cmd; do
      [[ -n "$cmd" ]] || continue
      run_snippet "$var" "$cmd" set >/dev/null 2>&1
    done < "$SITES"
  done
) &
LOOP_PID=$!
HITS=0
SAMPLES=0
while kill -0 "$LOOP_PID" 2>/dev/null; do
  SAMPLES=$((SAMPLES+1))
  if pgrep -f "$SENTINEL" >/dev/null 2>&1; then HITS=$((HITS+1)); fi
  [[ $SAMPLES -ge 4000 ]] && break
done
wait "$LOOP_PID" 2>/dev/null

# The sampler must be capable of seeing a match, or a zero result proves nothing.
# Plant a control process that DOES carry the sentinel on its command line.
bash -c "sleep 3; exit 0 $SENTINEL" >/dev/null 2>&1 &
CTRL_PID=$!
CTRL_SEEN=0
for _ in $(seq 1 200); do
  if pgrep -f "$SENTINEL" >/dev/null 2>&1; then CTRL_SEEN=1; break; fi
done
kill "$CTRL_PID" >/dev/null 2>&1; wait "$CTRL_PID" 2>/dev/null

if [[ $CTRL_SEEN -eq 1 ]]; then
  ok "process-table sampler is live (it detected a deliberately planted control process)"
else
  bad "process-table sampler never fired on the control process — part 3 proves nothing"
fi
if [[ $SAMPLES -ge 10 ]]; then
  ok "process table sampled $SAMPLES times while the snippets ran"
else
  bad "process table sampled only $SAMPLES times — too few to prove anything"
fi
if [[ $HITS -eq 0 ]]; then
  ok "the credential value never appeared in a process listing (${RUNS} rounds, $SAMPLES samples)"
else
  bad "the credential value appeared in the process table $HITS time(s)"
fi

# ---------------------------------------------------------------------------
# Part 3b — the leak detector must be able to detect a leak. Replay the shapes
#           these eight sites used to carry and assert the sentinel IS caught. A
#           detector that cannot fail proves nothing about the ones that passed.
# ---------------------------------------------------------------------------
detector_fires=1
for old in 'echo $SENTINEL_VAR | head -c 10' 'printenv SENTINEL_VAR | head -c 8' 'echo "API Key: $(echo $SENTINEL_VAR | head -c 10)..."'; do
  probe="$(
    declare -x "SENTINEL_VAR=$SENTINEL"
    bash -c "$old" 2>&1
  )"
  case "$probe" in
    *"${SENTINEL:0:8}"*) : ;;                      # correctly detected as a leak
    *) detector_fires=0 ;;
  esac
done
if [[ $detector_fires -eq 1 ]]; then
  ok "the leak detector catches every pre-fix value-emitting shape (control)"
else
  bad "the leak detector did NOT catch a known-leaking shape — parts 2 and 3 prove nothing"
fi

# ---------------------------------------------------------------------------
# Part 4 — regression lock: the value-emitting shapes must not come back.
# ---------------------------------------------------------------------------
python3 - "$REPO_ROOT" <<'PY'
import sys, pathlib
root = pathlib.Path(sys.argv[1])

BANNED = [
    ("07-kie-setup/INSTALL.md",                                "echo $KIE_API_KEY | head -c"),
    ("22-book-to-persona-coaching-leadership-system/SKILL.md", "grep GOOGLE_API_KEY secrets/.env"),
    ("22-book-to-persona-coaching-leadership-system/SKILL.md", "grep OLLAMA_API_KEY secrets/.env"),
    ("37-zhc-closeout/SKILL.md",                               "${NOTION_API_TOKEN:0:8}"),
    ("37-zhc-closeout/SKILL.md",                               "printenv KIE_API_KEY | head -c"),
    ("45-design-intelligence-library/INSTALL.md",              "If you see a key"),
    ("05-ghl-setup/INSTALL.md",                                "head -c 10"),
    ("05-ghl-setup/EXAMPLES.md",                               "head -c 10"),
    ("05-ghl-setup/QC.md",                                     "masked token prefix"),
]
REQUIRED = [
    ("05-ghl-setup/QC.md", "PRESENCE-ONLY"),
    ("37-zhc-closeout/SKILL.md", "never logs a prefix"),
]

fail = 0
for rel, needle in BANNED:
    if needle in (root / rel).read_text():
        print(f"  FAIL — {rel} still contains the value-emitting shape: {needle!r}")
        fail = 1
    else:
        print(f"  ok   — {rel} no longer contains {needle!r}")
for rel, needle in REQUIRED:
    if needle in (root / rel).read_text():
        print(f"  ok   — {rel} states the presence-only rule")
    else:
        print(f"  FAIL — {rel} does not state the presence-only rule ({needle!r})")
        fail = 1
sys.exit(fail)
PY
if [[ $? -eq 0 ]]; then PASS=$((PASS+11)); else FAIL=$((FAIL+1)); fi

echo ""
echo "=== $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
exit 0
