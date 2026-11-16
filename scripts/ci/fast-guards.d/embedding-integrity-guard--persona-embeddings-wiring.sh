#!/usr/bin/env bash
# Folded from .github/workflows/embedding-integrity-guard.yml (job "A-U8 — book-to-persona embeddings wiring (index write / deferral / index-verify / drift)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export OPENCLAW_PLATFORM=mac
( # step: Credential-error classification (is_credential_error, exit 4 vs 6)
echo "--- step: Credential-error classification (is_credential_error, exit 4 vs 6)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"Credential-error classification (is_credential_error, exit 4 vs 6)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/embedding-credential-error-classify.test.py -v
)
( # step: Orchestrator Phase-5 EMBED_FAILED exit-8 gate (regression, extended with DEFERRED)
echo "--- step: Orchestrator Phase-5 EMBED_FAILED exit-8 gate (regression, extended with DEFERRED)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"Orchestrator Phase-5 EMBED_FAILED exit-8 gate (regression, extended with DEFERRED)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/orchestrator-embed-fail-exit8.test.py -v
)
( # step: Orchestrator Phase-5 classify + deferred receipt (keyless real-subprocess end-to-end)
echo "--- step: Orchestrator Phase-5 classify + deferred receipt (keyless real-subprocess end-to-end)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"Orchestrator Phase-5 classify + deferred receipt (keyless real-subprocess end-to-end)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/orchestrator-phase5-deferred-receipt.test.py -v
)
( # step: persona_fleet.py index-verify (indexed OR honestly deferred, exit 7 on gap)
echo "--- step: persona_fleet.py index-verify (indexed OR honestly deferred, exit 7 on gap)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"persona_fleet.py index-verify (indexed OR honestly deferred, exit 7 on gap)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/persona-fleet-index-verify.test.py -v
)
( # step: persona_embedding_drift_probe (one operator card per run, fleet_refresh_runner wiring)
echo "--- step: persona_embedding_drift_probe (one operator card per run, fleet_refresh_runner wiring)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"persona_embedding_drift_probe (one operator card per run, fleet_refresh_runner wiring)\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/persona-embedding-drift-probe.test.py -v
)
( # step: publish-personas-to-fleet.sh end-to-end (triad + index-verify gate + rollback)
echo "--- step: publish-personas-to-fleet.sh end-to-end (triad + index-verify gate + rollback)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards embedding-integrity-guard--persona-embeddings-wiring: step \"publish-personas-to-fleet.sh end-to-end (triad + index-verify gate + rollback)\" failed (exit $fg_rc)"' EXIT
chmod +x tests/unit/publish-personas-to-fleet.test.sh
bash tests/unit/publish-personas-to-fleet.test.sh
)
