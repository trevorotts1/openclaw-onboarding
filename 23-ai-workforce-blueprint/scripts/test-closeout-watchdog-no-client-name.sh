#!/usr/bin/env bash
# BU-61s: closeout-readiness-watchdog.sh must not name a client.
#
# The D17 comment in this script used to name a real client in the form of a
# two-token Title Case personal name. It must now carry the neutral placeholder
# and no person-shaped name. This test reads the file; it never greps the
# repository.
#
# ponytail: scope is the D17 comment block, where the literal lived. Add a
# whole-file comment scan (with an allowlist for benign capitalised pairs such
# as "All Telegram") when a second comment ever names someone.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="$here/closeout-readiness-watchdog.sh"
[[ -f "$target" ]] || { echo "FAIL: $target not found"; exit 1; }

fail=0
placeholder_seen=0
in_d17=0

while IFS= read -r line || [[ -n "$line" ]]; do
  case "$line" in
    [[:space:]]*'#'*|'#'*)
      if [[ "$line" == *"D17:"* ]]; then
        in_d17=1
      elif [[ "$in_d17" -eq 1 ]]; then
        if [[ "$line" == *"<client>"* ]]; then
          placeholder_seen=1
        fi
        if [[ "$line" =~ [A-Z][a-z]+\ [A-Z][a-z]+ ]]; then
          printf 'FAIL: D17 comment carries a person-shaped name: %s\n' "$line"
          fail=1
        fi
      fi
      ;;
    *)
      in_d17=0
      ;;
  esac
done < "$target"

if [[ "$placeholder_seen" -ne 1 ]]; then
  echo "FAIL: the D17 comment does not carry the <client> placeholder"
  fail=1
fi

if [[ "$fail" -eq 0 ]]; then
  echo "PASS: D17 comment carries <client> and no person-shaped name"
fi
exit "$fail"
