# Broken variant — anthropic-call  → AF-SM-NOANTHROPIC

A provenance record (or any client-path artifact) that names an Anthropic model
id (a `claude-*` / `anthropic/claude-*` id, an `sk-ant`-style key, an
`@anthropic-ai` SDK import, or the Anthropic API-key env var). Client runtime
NEVER uses Anthropic (G-NOANTHROPIC), so the scrub gate (P5-SCRUB) fail-closes
with `AF-SM-NOANTHROPIC` (exit 2), no certificate is issued, and the publisher
never runs. Defense-in-depth: if a scrubbed provenance somehow reached P6,
`build_manifest.py`'s zero-Anthropic proof catches the same id and refuses to
sign — also `AF-SM-NOANTHROPIC` (see verify.sh step 4 `anthropic-at-manifest`).

## Why no fixture file is shipped here

Fleet rule: we do not ship a forbidden model-id literal into scanned bytes.
`verify.sh` **materializes** an offending provenance call into a read-only temp
file at test time, runs `scrub_gate.py` on it, asserts exit 2 + `AF-SM-NOANTHROPIC`,
and deletes it. Reproduce the shape manually:

```
tmp=$(mktemp)
python3 - "$tmp" <<'PY'
import json, sys
model = "claude" + "-opus-4-8"          # assembled so this source never holds the literal
json.dump([{"step":"rogue","provider":"anthropic","model":model}], open(sys.argv[1],"w"))
PY
python3 scripts/scrub_gate.py "$tmp"   # -> RESULT: FAIL, [AF-SM-NOANTHROPIC], exit 2
rm -f "$tmp"
```
