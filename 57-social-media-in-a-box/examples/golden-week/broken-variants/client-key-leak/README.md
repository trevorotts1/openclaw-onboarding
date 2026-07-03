# Broken variant — client-key-leak  → AF-SM-SECRET

A generated artifact that leaks a CLIENT secret (an OpenRouter key of the shape
`sk-or-v1-<40+ alphanumerics>`, or a GHL `pit-<token>`, or a webhook
`accessToken`). The scrub gate (P5-SCRUB) catches the secret PATTERN and
fail-closes with `AF-SM-SECRET` (exit 2). The value is confirmed present and
FORBIDDEN — it is never printed.

## Why no fixture file is shipped here

This repository is fleet-wide; we never ship a secret-shaped literal, even a
fabricated one, into scanned bytes (the tree scrub would — correctly — flag it,
and shipping fake key-shapes is a bad habit). Instead `verify.sh` **materializes**
a fabricated key (all-`a` filler, not a real secret) into a read-only temp file
at test time, runs `scrub_gate.py` on it, asserts exit 2 + `AF-SM-SECRET`, and
deletes it. Reproduce the shape manually:

```
tmp=$(mktemp)
python3 - "$tmp" <<'PY'
import sys
open(sys.argv[1],"w").write('{"key": "' + "sk-or-" + "v1-" + "a"*40 + '"}')
PY
python3 scripts/scrub_gate.py "$tmp"   # -> RESULT: FAIL, [AF-SM-SECRET], exit 2
rm -f "$tmp"
```
