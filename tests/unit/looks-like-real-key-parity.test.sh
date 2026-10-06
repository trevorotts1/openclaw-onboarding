#!/usr/bin/env bash
# Parity test: the bash looks_like_real_key (install.sh) and the python
# shared-utils/secret_helper.looks_like_real_key must give the SAME verdict for the same
# placeholder list and for a synthetic real-shaped key. No network, no real credential.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMPF="$(mktemp)"; trap 'rm -f "$TMPF"' EXIT
# Extract the bash function body verbatim from install.sh (function start to its closing brace).
awk '/^looks_like_real_key\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$ROOT/install.sh" > "$TMPF"
[ -s "$TMPF" ] || { echo "FAIL: could not extract looks_like_real_key from install.sh"; exit 1; }
# shellcheck disable=SC1090
source "$TMPF"
REAL="$(python3 -c 'a="ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"; print("".join(a[(i*37+11)%57] for i in range(32)))')"
VALUES=( "YOUR_CLIENT_KIE_API_KEY_HERE" "your_client_key_value_abcdef" "SOMETHING_KEY_HERE_12345" "paste_token_here_please_ok" \
         "your_key_here_please" "PASTE_REAL_TOKEN" "CHANGE_ME_LATER_ok" "<TODO_fill_this_in>" "sk-example1234567890" "short" "$REAL" )
# Every placeholder token, as a whole token (delimiter-bounded) after a key-shaped value:
# both twins must reject all of them (same set), and agree. sk-* are documented PREFIXES.
TOKENS=( your_key your-key your_api your-api yourkey your_token replace_me replace-me replaceme changeme change_me change-me \
         here placeholder example sample dummy demo test_key test-key fake_key fake-key todo tbd fill_in fill-in fillin \
         paste-your paste_your paste-real paste_real pastereal insert_your insert-your enter_your enter-your set_your set-your \
         no_key nokey none_yet not_set not-set unset missing your_client key_here token_here )
REJECT=()
for tok in "${TOKENS[@]}"; do REJECT+=( "${REAL}-${tok}-${REAL}" ); done
for pre in sk-test sk-xxx sk-example sk-replace; do REJECT+=( "${pre}${REAL}" ); done
REJECT+=( "${REAL}xxxxx${REAL}" "your-demo-key-abcdef" "demo_key_abcdef123" "DEMO_KEY_ABCDEF123" "KEY_HERE_ABCDEF123" "demo-${REAL}" "${REAL}_Demo" )
# Whole-token rule: placeholder words INSIDE a random alphanumeric run (or glued to digits)
# are real-key text and must be ACCEPTED by both twins.
ACCEPT=( "$REAL" )
for w in demo todo sample tbd here missing unset example dummy placeholder nokey; do ACCEPT+=( "Qx7${w}Lm9Zk2Pq8Rt4Vb6Nc3Hd5" "${REAL}${w}Z" "${w}Z${REAL}" "${REAL}-${w}9${REAL}" ); done
VALUES+=( "${REJECT[@]}" "${ACCEPT[@]}" )
FAIL=0
for v in "${VALUES[@]}"; do
  if looks_like_real_key "$v" KIE_API_KEY; then b=1; else b=0; fi
  p="$(cd "$ROOT/shared-utils" && PYTHONDONTWRITEBYTECODE=1 VAL="$v" python3 -c 'import os,secret_helper as s; print(1 if s.looks_like_real_key(os.environ["VAL"], "KIE_API_KEY") else 0)')"
  if [ "$b" != "$p" ]; then echo "FAIL: verdict differs bash=$b python=$p for a ${#v}-char value"; FAIL=1; fi
done
for v in "${REJECT[@]}"; do
  looks_like_real_key "$v" KIE_API_KEY && { echo "FAIL: placeholder not rejected (bash): ${v:0:20}..."; FAIL=1; }
  p="$(cd "$ROOT/shared-utils" && PYTHONDONTWRITEBYTECODE=1 VAL="$v" python3 -c 'import os,secret_helper as s; print(1 if s.looks_like_real_key(os.environ["VAL"], "KIE_API_KEY") else 0)')"
  [ "$p" = 0 ] || { echo "FAIL: placeholder not rejected (python): ${v:0:20}..."; FAIL=1; }
done
for v in "${ACCEPT[@]}"; do
  looks_like_real_key "$v" KIE_API_KEY || { echo "FAIL: real-shaped key rejected (bash): ${v:0:24}..."; FAIL=1; }
done
# Expected: only the synthetic real-shaped key is accepted.
looks_like_real_key "YOUR_CLIENT_KIE_API_KEY_HERE" KIE_API_KEY && { echo "FAIL: installer placeholder accepted (bash)"; FAIL=1; }
looks_like_real_key "$REAL" KIE_API_KEY || { echo "FAIL: real-shaped key rejected (bash)"; FAIL=1; }
[ "$FAIL" = 0 ] && echo "looks-like-real-key parity: PASS (${#VALUES[@]} values)"
exit "$FAIL"
