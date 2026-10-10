#!/usr/bin/env bash
# setup-kie-live-adapter.sh — install THIS CLIENT'S OWN KIE key into the Claude
# config roots' settings.json, and nothing else.
#
# Owner order (Trevor, 2026-10-10): insert ONLY the one key `env.KIE_API_KEY`.
#   * never an ANTHROPIC_* key, never any other key, never a base-URL write
#     (07-kie-setup/references/kie-common-rules.md rule 14),
#   * a BYTE-MINIMAL in-place edit: every pre-existing line keeps its bytes,
#     key order, indentation and trailing-newline style; exactly one entry is
#     added, nothing is re-serialized,
#   * NO backup file of any kind — no settings.json.bak-kie-*, no .bak, no .orig,
#   * the key value is never printed to stdout, stderr or any log, and the
#     resulting settings.json is chmod 600,
#   * the api.kie.ai base URL is REPORTED as copyable text and never written
#     into settings.json.
#
# Key sources, in order (never an operator key, never a value hard-coded here):
#   1. KIE_API_KEY already in the caller's environment (the client's own).
#   2. the client's own API document: --api-docs PATH, else $API_DOCS_PATH —
#      the line `KIE_API_KEY=...`. Presence is checked; the value stays inside
#      this process and is handed to the writer by environment, never by argv.
# Neither present: print `KIE key: NOT SET` plus the PREREQS instruction and
# write nothing. No prompt (headless installers must never block on a TTY).
#
# Roots: every --config-root DIR given, else $CLAUDE_CONFIG_DIR (when set),
# $HOME/.claude and $HOME/.claude-nine (each only when that directory exists).
#
# Output contract (SET/NOT SET only):
#   KIE key: SET | NOT SET
#   settings: <path> env.KIE_API_KEY written (mode 600)
#   settings: <path> env.KIE_API_KEY already present (mode 600)
#   KIE base URL (copy it into your agent config yourself; never written to
#   settings.json): https://api.kie.ai/anthropic
#
# Exit 0 = every addressed root now carries env.KIE_API_KEY (or the key was not
# set and nothing was written). Exit 1 = a settings.json could not be edited.
set -euo pipefail

BASE_URL="https://api.kie.ai/anthropic"

ROOTS=()
API_DOCS="${API_DOCS_PATH:-}"

usage() {
  cat <<'EOF'
usage: setup-kie-live-adapter.sh [--config-root DIR]... [--api-docs PATH] [--help]

  --config-root DIR  settings.json directory to edit (repeatable).
                     Default: $CLAUDE_CONFIG_DIR, ~/.claude, ~/.claude-nine.
  --api-docs PATH    file holding the client's own `KIE_API_KEY=...` line
                     (default: $API_DOCS_PATH).
  --help             this text.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --config-root)
      [ $# -ge 2 ] || { echo "setup-kie-live-adapter: --config-root needs a directory" >&2; exit 1; }
      ROOTS+=("$2"); shift 2 ;;
    --api-docs)
      [ $# -ge 2 ] || { echo "setup-kie-live-adapter: --api-docs needs a path" >&2; exit 1; }
      API_DOCS="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "setup-kie-live-adapter: unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ── 1. the key ──────────────────────────────────────────────────────────────
KIE_VALUE="${KIE_API_KEY:-}"
if [ -z "$KIE_VALUE" ] && [ -n "$API_DOCS" ] && [ -f "$API_DOCS" ]; then
  # Read into a variable; never echoed, never traced.
  KIE_VALUE="$(grep -m1 -E '^[[:space:]]*KIE_API_KEY=' "$API_DOCS" 2>/dev/null | cut -d= -f2- || true)"
  KIE_VALUE="${KIE_VALUE#"${KIE_VALUE%%[![:space:]]*}"}"   # ltrim
  KIE_VALUE="${KIE_VALUE%"${KIE_VALUE##*[![:space:]]}"}"   # rtrim
fi

if [ -z "$KIE_VALUE" ]; then
  echo "KIE key: NOT SET"
  echo "Ask the operator to provision this client's own KIE_API_KEY (presence check only, value never printed)."
  echo "KIE base URL (copy it into your agent config yourself; never written to settings.json): $BASE_URL"
  exit 0
fi
echo "KIE key: SET"

# ── 2. the roots ────────────────────────────────────────────────────────────
if [ "${#ROOTS[@]}" -eq 0 ]; then
  [ -n "${CLAUDE_CONFIG_DIR:-}" ] && [ -d "${CLAUDE_CONFIG_DIR}" ] && ROOTS+=("${CLAUDE_CONFIG_DIR}")
  [ -d "$HOME/.claude" ] && ROOTS+=("$HOME/.claude")
  [ -d "$HOME/.claude-nine" ] && ROOTS+=("$HOME/.claude-nine")
fi

if [ "${#ROOTS[@]}" -eq 0 ]; then
  echo "settings: no config root found — nothing written"
  echo "KIE base URL (copy it into your agent config yourself; never written to settings.json): $BASE_URL"
  exit 0
fi

# ── 3. the edit (byte-minimal, additive only) ───────────────────────────────
# The key travels by environment only: never in argv (visible in `ps`), never
# printed. Everything the writer needs is in this process.
KIE_VALUE="$KIE_VALUE" KIE_ROOTS="$(printf '%s\n' "${ROOTS[@]}")" python3 - <<'PY'
import json
import os
import re
import sys
import tempfile

KEY_NAME = "KIE_API_KEY"
MODE = 0o600


def die(msg):
    sys.stderr.write("settings: %s\n" % msg)
    sys.exit(1)


def skip_ws(s, i):
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def scan_string(s, i):
    """i is at the opening quote; return the index just past the closing quote."""
    i += 1
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        i += 1
    die("unterminated string in settings.json")


def skip_value(s, i):
    """Return the index just past the JSON value starting at i."""
    c = s[i]
    if c == '"':
        return scan_string(s, i)
    if c in "{[":
        close = "}" if c == "{" else "]"
        depth = 0
        n = len(s)
        while i < n:
            ch = s[i]
            if ch == '"':
                i = scan_string(s, i)
                continue
            if ch == c:
                depth += 1
                i += 1
                continue
            if ch == close:
                depth -= 1
                i += 1
                if depth == 0:
                    return i
                continue
            i += 1
        die("unbalanced %s in settings.json" % c)
    m = re.match(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null", s[i:])
    if not m:
        die("unreadable value at byte %d in settings.json" % i)
    return i + len(m.group(0))


def scan_object(s, start):
    """Parse the object starting at `start` ('{').

    Returns ([(key, value_start, value_end), ...], index_just_past_close_brace).
    Only scanning — nothing is re-encoded, so byte offsets stay exact.
    """
    out = []
    i = skip_ws(s, start + 1)
    if s[i] == "}":
        return out, i + 1
    while True:
        i = skip_ws(s, i)
        if s[i] != '"':
            die("expected a key at byte %d in settings.json" % i)
        kend = scan_string(s, i)
        try:
            name = json.loads(s[i:kend])
        except ValueError:
            die("unreadable key at byte %d in settings.json" % i)
        i = skip_ws(s, kend)
        if s[i] != ":":
            die("expected ':' at byte %d in settings.json" % i)
        i = skip_ws(s, i + 1)
        vs = i
        i = skip_value(s, i)
        out.append((name, vs, i))
        i = skip_ws(s, i)
        if s[i] == ",":
            i += 1
            continue
        if s[i] == "}":
            return out, i + 1
        die("expected ',' or '}' at byte %d in settings.json" % i)


def opener_style(s, open_idx):
    """The newline token and the member indent that follow a '{'.

    `open_idx` points at the '{'. Whatever follows it byte-for-byte is what the
    surrounding members already use, so the inserted line matches by construction
    and no existing line has to be touched to look right.
    """
    m = re.match(r"(?:\r\n|\n)", s[open_idx + 1:])
    if not m:
        return "", ""
    nl = m.group(0)
    rest = s[open_idx + 1 + len(nl):]
    return nl, re.match(r"[ \t]*", rest).group(0)


def write_settings(path, data, created):
    """Temp file in the same directory, then rename. No .bak, no copy, ever."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".kie-live-adapter-", dir=d)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, MODE)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)
    os.chmod(path, MODE)
    print("settings: %s env.KIE_API_KEY %s (mode 600)"
          % (path, "created" if created else "written"))


value = os.environ["KIE_VALUE"]
roots = [r for r in os.environ.get("KIE_ROOTS", "").split("\n") if r]
entry = json.dumps(KEY_NAME) + ": " + json.dumps(value)

for root in roots:
    path = os.path.join(root, "settings.json")

    if not os.path.exists(path):
        if not os.path.isdir(root):
            die("%s: no such config root" % root)
        doc = ("{\n  \"env\": {\n    " + entry + "\n  }\n}\n").encode("utf-8")
        write_settings(path, doc, created=True)
        continue

    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        die("%s: not UTF-8 — left untouched" % path)

    try:
        json.loads(text)
    except ValueError as exc:
        die("%s: not valid JSON (%s) — left untouched" % (path, exc))

    top = skip_ws(text, 0)
    if text[top] != "{":
        die("%s: top level is not an object — left untouched" % path)
    top_entries, top_end = scan_object(text, top)

    env = next((e for e in top_entries if e[0] == "env"), None)
    if env is None:
        nl, ind = opener_style(text, top)
        if top_entries:
            insert = (nl + ind + '"env": {' + nl + ind + "  " + entry
                      + nl + ind + "},")
        else:
            insert = '"env": {' + nl + ind + "  " + entry + nl + ind + "}"
        pos = top + 1
    else:
        _, vs, ve = env
        if text[vs] != "{":
            die("%s: env is not an object — left untouched" % path)
        env_entries, _ = scan_object(text, vs)
        if any(k == KEY_NAME for k, _, _ in env_entries):
            os.chmod(path, MODE)
            print("settings: %s env.KIE_API_KEY already present (mode 600)" % path)
            continue
        nl, ind = opener_style(text, vs)
        insert = nl + ind + entry + ("," if env_entries else "")
        pos = vs + 1

    new_text = text[:pos] + insert + text[pos:]

    # The whole contract in one line: dropping our insert byte-for-byte restores
    # the original, so no pre-existing byte can have moved, changed or vanished.
    if new_text[:pos] + new_text[pos + len(insert):] != text:
        die("%s: edit was not additive — left untouched" % path)
    try:
        json.loads(new_text)
    except ValueError as exc:
        die("%s: edit would produce invalid JSON (%s) — left untouched" % (path, exc))

    write_settings(path, new_text.encode("utf-8"), created=False)
PY

# ── 4. the base URL, reported and never written ─────────────────────────────
echo "KIE base URL (copy it into your agent config yourself; never written to settings.json): $BASE_URL"
exit 0
