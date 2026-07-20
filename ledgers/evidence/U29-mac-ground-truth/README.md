# U29 (B/B-U15) — Mac-leg first-hour ground-truth receipt (sanitized)

Run 2026-07-20 on the real operator Mac by the Fable 5 confirmation pass:

    python3 tools/ghl_env_matrix_ground_truth.py run --evidence-root <scratch> \
        --box-label operator-mac-mini --run-id u29-conf-20260719

- `validate` on the emitted receipt -> `valid`, exit 0 (validated BEFORE sanitization).
- Real box resolution measured live: platform=darwin, is_vps=False, supervisor=launchd,
  durable_root = the box's own `~/.openclaw`.
- The receipt honestly stamps `live: false` for the BUILDER tier (deterministic fixture
  builder). The genuine live tier (real `ghl_survey_builder`/`ghl_verify` against a
  designated GHL test location) and the VPS-side receipt + `compare` parity run remain
  operator-gated and OWED.
- Sanitization applied to this copy only: `durable_root` and `evidence_root` path values
  homogenized (no box identifiers in the repo). No other field changed.
