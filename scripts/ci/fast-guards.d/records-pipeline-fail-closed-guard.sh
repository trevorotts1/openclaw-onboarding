#!/usr/bin/env bash
# Folded from .github/workflows/records-pipeline-fail-closed-guard.yml (job "Skill 39/40: the pipeline fails closed (T0-49/51/53/54/55, T1-05, T2-33/34)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Shell syntax of every changed script
set -e -o pipefail
set -euo pipefail
fail=0
for f in 39-real-estate-playbook/scripts/*.sh 40-zhc-public-records-scraper/scripts/*.sh \
         40-zhc-public-records-scraper/scripts/adapters/*.sh \
         tests/unit/records-pipeline-fail-closed.test.sh \
         tests/unit/re-routing-fair-housing.test.sh; do
  [ -f "$f" ] || continue
  bash -n "$f" || { echo "  x syntax: $f"; fail=1; }
done
python3 -m py_compile 40-zhc-public-records-scraper/scripts/selector-probe.py
[ $fail -eq 0 ] && echo "OK: every shell script parses and the selector probe compiles"
exit $fail
)
( # step: The selector probe evaluates, and reports what it cannot evaluate
set -e -o pipefail
set -euo pipefail
cat > /tmp/probe-doc.html <<'HTML'
<html><body><table id="r"><tbody>
<tr class="row" data-id="1"><td class="owner">REDACTED</td></tr>
<tr class="row" data-id="2"><td class="owner">REDACTED</td></tr>
</tbody></table></body></html>
HTML
P=40-zhc-public-records-scraper/scripts/selector-probe.py
python3 "$P" /tmp/probe-doc.html "tr.row" "td.owner" "#r tbody > tr" \
  || { echo "FAIL: a matching selector was reported as a miss"; exit 1; }
if python3 "$P" /tmp/probe-doc.html "td.no-such-class" >/dev/null; then
  echo "FAIL: a non-matching selector was reported as a match"; exit 1
fi
if python3 "$P" /tmp/probe-doc.html "<css-selector-for-each-result-row>" >/dev/null; then
  echo "FAIL: the unedited template placeholder was accepted as a selector"; exit 1
fi
if python3 "$P" /tmp/probe-doc.html "tr:first-child" >/dev/null; then
  echo "FAIL: an unevaluable selector silently passed"; exit 1
fi
echo "OK: the probe matches what matches, and REPORTS what it cannot evaluate"
)
( # step: Records pipeline fail-closed suite (with mutation proofs)
set -e -o pipefail
bash tests/unit/records-pipeline-fail-closed.test.sh
)
( # step: Fair-housing routing + keyed-provider-miss suite (with mutation proofs)
set -e -o pipefail
bash tests/unit/re-routing-fair-housing.test.sh
)
( # step: The three shipped Skill 40 gates still pass on a healthy tree
set -e -o pipefail
set -euo pipefail
bash 40-zhc-public-records-scraper/scripts/qc-compliance.sh
bash 40-zhc-public-records-scraper/scripts/qc-no-fabrication.sh
bash 40-zhc-public-records-scraper/scripts/qc-no-personal-data.sh
)
( # step: The three shipped Skill 39 gates still pass on a healthy tree
set -e -o pipefail
set -euo pipefail
bash 39-real-estate-playbook/scripts/qc-fair-housing.sh
bash 39-real-estate-playbook/scripts/qc-no-fabrication.sh
bash 39-real-estate-playbook/scripts/qc-no-personal-data.sh
)
