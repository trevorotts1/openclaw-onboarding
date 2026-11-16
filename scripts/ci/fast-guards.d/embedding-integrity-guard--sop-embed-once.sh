#!/usr/bin/env bash
# Folded from .github/workflows/embedding-integrity-guard.yml (job "P4-03 — CC SOP-embeddings embed-once pipeline (Corpus 5)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: SOP embed-once — HASH-SKIP + real-vector hard gate
echo "--- step: SOP embed-once — HASH-SKIP + real-vector hard gate"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"SOP embed-once — HASH-SKIP + real-vector hard gate\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/sop-embed-once-hash-skip.test.py -v
)
( # step: SOP-embeddings client-box provisioning — idempotency + sha256/model-mix refusal
echo "--- step: SOP-embeddings client-box provisioning — idempotency + sha256/model-mix refusal"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"SOP-embeddings client-box provisioning — idempotency + sha256/model-mix refusal\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/provision-sop-embeddings-idempotency.test.py -v
)
( # step: CC SOP embedding-health — dual-surface reconciliation (dark-box no longer false-passes)
echo "--- step: CC SOP embedding-health — dual-surface reconciliation (dark-box no longer false-passes)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"CC SOP embedding-health — dual-surface reconciliation (dark-box no longer false-passes)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/embedding-health-cc-sop-reconciliation.test.py -v
)
( # step: SOP library — coverage gate (an under-populated sops table can no longer report pass)
echo "--- step: SOP library — coverage gate (an under-populated sops table can no longer report pass)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"SOP library — coverage gate (an under-populated sops table can no longer report pass)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/sop-library-coverage-gate.test.py -v
)
( # step: SOP library v3 — builder carries V2 verbatim + dept SOPs; manifest pins real sample slugs
echo "--- step: SOP library v3 — builder carries V2 verbatim + dept SOPs; manifest pins real sample slugs"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"SOP library v3 — builder carries V2 verbatim + dept SOPs; manifest pins real sample slugs\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/sop-library-v3-build.test.py -v
)
( # step: SOP library — update-path ingestion (idempotent, non-clobbering, fails loud; offline)
echo "--- step: SOP library — update-path ingestion (idempotent, non-clobbering, fails loud; offline)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--sop-embed-once: step \"SOP library — update-path ingestion (idempotent, non-clobbering, fails loud; offline)\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/sop-library-update-path-ingest.test.sh
bash tests/unit/sop-library-update-path-ingest.test.sh
)
