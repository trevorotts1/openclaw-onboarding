# RR-034 worker-persona bridge (FLEET <-> ONB)

FLEET `rescue/service/worker-persona.mjs` is the deterministic worker-start
gate. Its resolver is INJECTED. In production the injected resolver shells to
ONB `23-ai-workforce-blueprint/scripts/resolve-worker-persona.py` and maps the
JSON envelope to `{ persona_id, persona_version, task_category,
interaction_mode, governance_persona_id, blend_applicable, blend_reason }`.

CLI:

    python3 resolve-worker-persona.py --task "<operator task>" \
        --company-config <company-config.json> \
        --catalog <persona-categories.json> \
        --company <slug> --box <slug> --ticket <id> --format json

Flags:

- `--search-available 0` simulates optional-search outage. The envelope stays
  usable with `source: cached-fallback`, `fallback: labeled`, and a
  `provenance.reason` naming the cause. Required policy is NEVER skipped:
  `policy_status: missing_mandatory` + `allow_unsafe_effects: false` when no
  company config resolves.
- Mechanical tasks (`restart`, `reboot`, `ping`, `ls`, `chmod`, `chown`,
  `check disk`, `check memory` — same contract as
  `shared-utils/mechanical-gate.py`) return `no_persona_required: true` plus
  the governance pointer. `blend_applicable` is ALWAYS false there.
- Content tasks return `blend_applicable: true, blend_reason: content_task`
  (voice-first AUDIENCE+TOPIC composition is assembled by the caller's
  `persona_blend.build_bundle` path, not here).
- The resolver takes NO incident-text argument by construction. Incident prose
  is untrusted data: FLEET hashes it (`incident.digest`) and never
  interpolates it into the prompt.

Envelope keys consumed by FLEET: `persona_id`, `persona_version`,
`task_mode`, `policy_status`, `policy_hash`, `allow_unsafe_effects`,
`safe_diagnosis_only`, `blend_applicable`, `blend_reason`,
`governance_persona_id`, `scope`, `scope_key`, `budget_ms`,
`budget_exceeded`, `catalog_sha`, `source`, `fallback`, `provenance`.
