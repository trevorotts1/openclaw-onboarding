#!/usr/bin/env bash
# Folded from .github/workflows/content-pipeline-fail-closed-guard.yml (job "T0-63/T0-64/T2-38: the email-engine proofs hold"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax-check and compile
echo "--- step: Syntax-check and compile"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--email-engine-proofs: step \"Syntax-check and compile\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 50-email-engine/verify.sh
python3 -m py_compile 50-email-engine/tools/prove-email.py
python3 -m py_compile 50-email-engine/run_email_engine.py
python3 -m py_compile 50-email-engine/test_intake_contract_authority.py
echo "OK"
)
( # step: T2-38 — the intake contract is authoritative in both directions
echo "--- step: T2-38 — the intake contract is authoritative in both directions"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--email-engine-proofs: step \"T2-38 — the intake contract is authoritative in both directions\" failed (exit $fg_rc)"' EXIT
python3 50-email-engine/test_intake_contract_authority.py
)
( # step: The whole Skill 50 verification gate (includes T0-63 and T0-64)
echo "--- step: The whole Skill 50 verification gate (includes T0-63 and T0-64)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--email-engine-proofs: step \"The whole Skill 50 verification gate (includes T0-63 and T0-64)\" failed (exit $fg_rc)"' EXIT
bash 50-email-engine/verify.sh
)
( # step: T0-64 — the certificate check REALLY fails on an unsigned artifact
echo "--- step: T0-64 — the certificate check REALLY fails on an unsigned artifact"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--email-engine-proofs: step \"T0-64 — the certificate check REALLY fails on an unsigned artifact\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# A gate observed only passing has not been observed. Strip the signature
# from a COPY of the golden run dir and require a non-zero exit.
cp -r 50-email-engine/examples/golden-landing-10 /tmp/golden-unsigned
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("/tmp/golden-unsigned/delivery/PROCESS-CERTIFICATE.json")
body = json.loads(p.read_text())
body.pop("certificate_sig", None)
p.write_text(json.dumps(body, indent=2))
PY
if python3 50-email-engine/run_email_engine.py --verify-certificate /tmp/golden-unsigned; then
  echo "FAIL: an unsigned certificate authenticated (T0-64)"
  exit 1
fi
echo "OK: an unsigned certificate is rejected"
# And with the key removed, which is exactly the shipped-artifact defect.
rm -rf /tmp/golden-nokey && cp -r 50-email-engine/examples/golden-landing-10 /tmp/golden-nokey
rm -f /tmp/golden-nokey/working/checkpoints/.cert-hmac-key
if python3 50-email-engine/run_email_engine.py --verify-certificate /tmp/golden-nokey; then
  echo "FAIL: a certificate with no signing key authenticated (T0-64)"
  exit 1
fi
echo "OK: an unkeyed certificate is rejected"
)
( # step: The enforcement hash pin matches the pinned head
echo "--- step: The enforcement hash pin matches the pinned head"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--email-engine-proofs: step \"The enforcement hash pin matches the pinned head\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
cd 50-email-engine
computed="$(cat tools/prove-email.py run_email_engine.py EMAIL-MANIFEST.json \
  tools/launch_profiles.py tools/persona_canonical.py \
  profiles/launch-email-families.json schema/email.schema.json \
  intake/email-intake-questions.json | sha256sum | awk '{print $1}')"
pinned="$(tr -d ' \t\n' < ENGINE-PIN.sha256)"
if [ "$computed" != "$pinned" ]; then
  echo "FAIL: ENGINE-PIN.sha256 drift — computed $computed, pinned $pinned"
  exit 1
fi
echo "OK: enforcement hash matches the pinned head"
)
