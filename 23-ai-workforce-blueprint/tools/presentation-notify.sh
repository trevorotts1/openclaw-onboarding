#!/bin/bash
# presentation-notify.sh — sends presentation progress messages to the operator via Telegram
# Invoked by the engine's Reporter (report.py) via PRESENTATION_NOTIFY_CMD.
#
# TWO PROTOCOLS:
#   A (engine — stdin JSON):  echo '{"chat_id":"...","kind":"progress","message":"..."}' | presentation-notify.sh
#   B (manual — positional):  presentation-notify.sh "message text" progress
#
# GAP G1 (command injection, fixed): this script used to hand a python3-built
# string to `eval`. json.dumps() only escapes what JSON *syntax* requires
# (quotes, backslashes, control chars) — it does NOT escape shell
# metacharacters. A `message` value containing `$(...)`, backticks, or `;`
# survived json.dumps() unescaped, so `eval "$PARSED"` executed it as shell
# the moment the assignment ran, as whoever invoked this script (the
# operator). Fix: python3 still does the JSON parsing, but now hands the
# three fields back over stdout as NUL-delimited literal bytes, read with
# `read -r -d ''` into shell variables. NUL-delimited `read` assigns data —
# it never re-parses its input as shell syntax, so there is no eval, no
# string-built command, and no way for the JSON payload to reach a shell
# interpreter at all.
#
# GAP G1 FOLLOW-UP (field-boundary forgery, fixed): the NUL-delimited
# protocol above made NUL the wire's field delimiter — but JSON legally
# encodes a literal NUL as `\u0000`, and json.loads() decodes that escape
# into a real NUL *byte* in the untrusted `message` string. That byte is
# indistinguishable, once written to the pipe, from the delimiter the
# writer placed between fields. Proven: message =
# "legit\x00progress\x00999_ATTACKER_CHAT" forged two fake field breaks
# inside the message itself, so the 3 `read -d ''` calls above pulled
# MSG="legit" (truncated), KIND="progress" (the forged one, not the real
# trailing one), and CID="999_ATTACKER_CHAT" — an attacker-chosen chat_id
# silently replacing the trusted one. A lone leading NUL produced an empty
# MSG, which fell through to "no message" and exited 1 before ever
# reaching curl, silently dropping the notification. Fix: python3 strips
# NUL (the delimiter) and CR/LF (defense-in-depth against any other
# newline-framed consumer) from all three *decoded* fields before they are
# ever written back to the wire — see sanitize() below. This is a
# structural guarantee, not best-effort escaping: once no field can
# contain the delimiter byte, `read -r -d ''` cannot be handed a forged
# boundary, so this specific protocol is safe by construction. A
# length-prefixed or argv-vector framing was considered instead but
# rejected: bash variables are C strings and cannot hold an embedded NUL
# under ANY framing (confirmed empirically — `read -N`, `readarray -d ''`,
# and `$(...)` all drop/truncate on a raw NUL the same way `read -d ''`
# does), so a fancier framing scheme would buy nothing beyond what
# stripping the delimiter already gives; the real fix has to happen before
# the byte ever reaches bash. Stripping (not rejecting) is deliberate too —
# the notification must still be delivered, and refusing to send a
# poisoned message would just be a different way to suppress it.
#
# GAP G1 AMENDMENT (silent drop on unencodable character, fixed): sanitize()
# ran INSIDE the try block above, but the three sys.stdout.write() calls
# used to sit OUTSIDE it, with this whole python3 invocation's stderr
# thrown away by a trailing 2>/dev/null. A lone surrogate codepoint
# (U+D800-U+DFFF) survives sanitize() unchanged -- it is not NUL, CR, or
# LF -- but has no UTF-8 representation. Two real, attacker-free ways to
# get one: a literal \uD800 JSON escape in `message`, or Python's
# surrogateescape turning a non-UTF-8 byte in a filename (e.g. a badly
# named asset mentioned in a BLOCKED alert) into U+DCxx before it was ever
# embedded in the alert text. Proven: with the write outside the try,
# sanitize() succeeded, the try block exited clean, and the *next*
# statement -- str.write(), which encodes internally with the default
# 'strict' handler -- raised UnicodeEncodeError. Nothing had been flushed
# yet, so zero bytes reached the pipe, all three `read -r -d ''` calls hit
# EOF, MSG stayed empty, and the script exited 1 having sent nothing --
# stderr discarded, so even that silent failure left no trace. Fix, two
# parts: (1) the writes now happen INSIDE the same try that does the
# parsing, so nothing downstream of json.loads() can fail outside error
# handling; (2) each field is encoded explicitly with str.encode('utf-8',
# errors='replace') before being written as bytes to stdout.buffer --
# that error mode never raises, so the unencodable-character failure mode
# is eliminated at the source rather than merely caught. Degrading one
# character to U+FFFD beats losing the whole notification. The trailing
# 2>/dev/null on the python3 invocation is also removed below: stderr now
# reaches this script's own stderr (visible to whoever invokes it) instead
# of vanishing, so if a future defect ever reintroduces a raise here, it
# is loud, not silent.

set -euo pipefail

MSG=""
KIND=""
CHAT_ID_STDIN=""

# I/O-DUAL: detect piped stdin (engine transport) vs positional args (manual)
if [ ! -t 0 ]; then
  # Read stdin ONCE into a variable, then parse with python3
  RAW="$(cat)"

  if [ -n "$RAW" ]; then
    # Parse JSON from stdin. Emit MSG, KIND, CID as three NUL-terminated
    # fields on stdout — NUL-delimited `read` treats every byte it receives
    # as literal data, so nothing here is ever handed to a shell parser.
    MSG=""
    KIND="progress"
    CID=""
    {
      IFS= read -r -d '' MSG || true
      IFS= read -r -d '' KIND || true
      IFS= read -r -d '' CID || true
    } < <(python3 -c "
import sys, json

# sanitize(): strip the wire delimiter (NUL) and newlines (CR/LF) from a
# DECODED field so it can never forge a field boundary downstream. See the
# GAP G1 FOLLOW-UP header comment for why this is the structural fix.
def sanitize(v, default=''):
    if v is None:
        v = default
    s = str(v)
    return s.replace('\x00', '').replace('\r', ' ').replace('\n', ' ')

# encode_field(): turn a sanitized str into wire bytes with a total,
# never-raising strategy. errors='replace' swaps anything UTF-8 cannot
# represent (a lone surrogate, for instance) for U+FFFD's UTF-8 bytes
# instead of raising -- see the GAP G1 AMENDMENT header comment above.
def encode_field(s):
    return s.encode('utf-8', errors='replace')

try:
    d = json.loads(sys.argv[1])
    msg = sanitize(d.get('message'), '')
    kind = sanitize(d.get('kind'), 'progress') or 'progress'
    cid = sanitize(d.get('chat_id'), '')
    out = sys.stdout.buffer
    out.write(encode_field(msg))
    out.write(b'\x00')
    out.write(encode_field(kind))
    out.write(b'\x00')
    out.write(encode_field(cid))
    out.write(b'\x00')
    out.flush()
except Exception as exc:
    # Loud, not silent: this is the only place an operator (or a caller
    # inspecting captured stderr) can see the notify transport itself
    # broke, as opposed to Telegram rejecting the send (reported
    # separately, further down this script).
    sys.stderr.write('presentation-notify: sanitize/encode failed: ' + repr(exc) + chr(10))
    sys.exit(1)
" "$RAW")

    CHAT_ID_STDIN="${CID:-}"
  fi
fi

# Fall back to positional args if stdin didn't populate MSG
if [ -z "${MSG:-}" ]; then
  MSG="${1:-}"
  KIND="${2:-progress}"
fi

if [ -z "$MSG" ]; then
  echo "ERROR: no message text (stdin JSON or positional args required)" >&2
  exit 1
fi

# --- Source secrets -------------------------------------------------------------
SECRETS_FILE="${HOME}/.openclaw/secrets/.env"
if [ -f "$SECRETS_FILE" ]; then
  set -a
  # shellcheck source=/dev/null
  . "$SECRETS_FILE"
  set +a
fi

BOT_TOKEN="${OPERATOR_TELEGRAM_BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID_STDIN:-${OWNER_CHAT_ID:-}}"

if [ -z "$BOT_TOKEN" ] || [ -z "${CHAT_ID:-}" ]; then
  echo "ERROR: OPERATOR_TELEGRAM_BOT_TOKEN or OWNER_CHAT_ID unset" >&2
  exit 2
fi

# --- Prefix by kind -------------------------------------------------------------
case "${KIND:-progress}" in
  ack)      PREFIX="[Presentation ACK] " ;;
  done)     PREFIX="[Presentation DONE] " ;;
  blocked)  PREFIX="[Presentation BLOCKED] " ;;
  *)        PREFIX="[Presentation] " ;;
esac

FULL_MSG="${PREFIX}${MSG}"

# --- Send via Telegram Bot API --------------------------------------------------
RESP="$(curl -s --max-time 15 -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT_ID}" \
  --data-urlencode "text=${FULL_MSG}" \
  --data-urlencode "disable_web_page_preview=true" \
  --data-urlencode "disable_notification=${DISABLE_NOTIFICATION:-false}" 2>&1)" || true

OK="$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok',False))" 2>/dev/null || echo "False")"

if [ "$OK" != "True" ]; then
  echo "ERROR: Telegram send failed: $RESP" >&2
  exit 3
fi

exit 0
