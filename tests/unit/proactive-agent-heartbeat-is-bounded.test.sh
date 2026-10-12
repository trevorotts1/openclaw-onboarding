#!/usr/bin/env bash
# D13: the skill 18 heartbeat checklist must be bounded and report-only. The old open-ended one
# ("Diagnose & Fix", "Not allowed to answer: Nothing comes to mind", proactive work) made heartbeat runs
# wander for ~60 tool calls, hit the 600 s cap, and (Corey Sams) reach the client's chat.
# Runs the real INSTALL.md copy step into a temp HOME and checks what lands. Hermetic.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SK="$REPO/18-proactive-agent"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }

# Install exactly as INSTALL.md says: mkdir -p ~/.openclaw/skills/proactive-agent; cp -R ./upstream-original/. there.
grep -q 'cp -R ./upstream-original/\. ~/.openclaw/skills/proactive-agent/' "$SK/INSTALL.md" \
  && ok "INSTALL.md still copies upstream-original/ into the skill folder" || bad "INSTALL.md copy step changed"
mkdir -p "$T/home/.openclaw/skills/proactive-agent"
( cd "$SK" && HOME="$T/home" cp -R ./upstream-original/. "$T/home/.openclaw/skills/proactive-agent/" )
H="$T/home/.openclaw/skills/proactive-agent/assets/HEARTBEAT.md"
[ -s "$H" ] && ok "installer puts assets/HEARTBEAT.md in place" || { bad "installed HEARTBEAT.md missing"; exit 1; }

# the full recreation embeds the same text the installer ships (only the HEARTBEAT block is checked, the
# rest of that file legitimately quotes the upstream skill text)
awk '/^### BEGIN assets\/HEARTBEAT.md/{f=1;next} /^### END assets\/HEARTBEAT.md/{f=0} f' "$SK/proactive-agent-full.md" | sed '/./,$!d' > "$T/embedded"
[ -s "$T/embedded" ] || bad "could not extract the embedded HEARTBEAT block"
for f in "$H" "$T/embedded"; do
  n="$([ "$f" = "$H" ] && echo HEARTBEAT.md || echo full-recreation-block)"
  grep -q 'at most 4 shell commands' "$f" && ok "$n: command cap" || bad "$n: no command cap"
  grep -q 'Never message the owner or any client' "$f" && ok "$n: no-message rule" || bad "$n: no no-message rule"
  grep -q 'Do not investigate, diagnose, repair or edit' "$f" && ok "$n: report-only rule" || bad "$n: no report-only rule"
  if grep -q -e 'Diagnose & Fix' -e 'Not allowed to answer' -e 'Proactive Work' -e 'Proactive Surprise' -e 'Attempt fix' "$f"; then
    bad "$n: still has an open-ended section"
  else ok "$n: no open-ended section"; fi
done

diff <(sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$T/embedded") <(sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$H") >/dev/null \
  && ok "proactive-agent-full.md embeds the shipped checklist" || bad "embedded copy differs from the shipped checklist"
exit $fail
