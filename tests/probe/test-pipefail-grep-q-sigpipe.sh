#!/usr/bin/env bash
# Regression lock for the u53 crown-executor guard flake (v28.0.0).
# Root cause: `set -o pipefail` + `printf '%s' "$BIG" | grep -q pat`. grep -q
# exits on first match, printf gets SIGPIPE on a block larger than the pipe
# buffer, the pipeline status is non-zero, and a present anchor reads as absent.
# Proves: (1) the pipe form really fails on a large block, (2) the here-string
# form always passes, (3) the u53 test no longer uses the pipe form.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
U53="$HERE/test-u53-hl-u68-crown-executor-single-path.sh"
fail=0
BIG="$(printf 'needle\n'; head -c 3000000 /dev/zero | tr '\0' 'x')"

pipe_fail=0
for _ in 1 2 3 4 5; do
  printf '%s' "$BIG" | grep -q needle || pipe_fail=$((pipe_fail+1))
done
if [ "$pipe_fail" -ge 1 ]; then echo "PASS: pipe form is unsafe under pipefail ($pipe_fail/5 false negatives) - premise holds"
else echo "FAIL: could not reproduce the SIGPIPE false negative"; fail=1; fi

here_fail=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  grep -q needle <<<"$BIG" || here_fail=$((here_fail+1))
done
if [ "$here_fail" -eq 0 ]; then echo "PASS: here-string form matched 10/10"
else echo "FAIL: here-string form failed $here_fail/10"; fail=1; fi

if grep -nE "printf .*\| *grep" "$U53" | grep -vE '^[0-9]+:\s*#'; then
  echo "FAIL: u53 test still pipes a captured block into grep"; fail=1
else echo "PASS: u53 test has no printf|grep pipelines"; fi
exit "$fail"
