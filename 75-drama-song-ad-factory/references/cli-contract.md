# Control CLI contract

Source of the implemented behavior: `docs/operating-and-recovery/OPERATING.md`
in the build tree (verified 2026-10-06), implemented by
`scripts/core/intake_preflight/`. This distribution packages that same code;
the OpenClaw distribution runs the identical entrypoint.

## Envelope

Every command prints exactly one JSON object on stdout (no log noise) and
exits with the code for its `outcome`.

```json
{
  "schema_version": "blackceo.intake-preflight/envelope/v1",
  "tool_version": "0.1.0",
  "command": "intake | preflight",
  "run_id": "<12 hex chars>",
  "outcome": "ok | waiting | parked | rejected | error",
  "reason_code": "<stable machine code>",
  "next_action": "<one sentence a human or agent can act on>",
  "evidence": [],
  "data": {},
  "state_version": { "expected": null, "current": "<digest or run id>" }
}
```

Execution outcomes are separate from QC verdicts and board statuses. A
runtime adapter stops on a nonzero exit instead of guessing from prose.

## Exit codes (control CLI)

| Exit | `outcome` | Adapter behavior |
|---:|---|---|
| 0 | `ok` | continue |
| 1 | `error` | report `reason_code`; do not improvise |
| 2 | `waiting` | answer the bundled questions in one reply |
| 3 | `parked` | resolve the blocking decision / state; never start a fresh run |
| 4 | `rejected` | stop; policy, trust or authorization refused this action |

Note: the spend-ledger CLI uses a different map (`ok 0, waiting 3, parked 4,
rejected 5, error 1`). Read `command` before applying a code.

## `intake`

```bash
python3 scripts/core/intake_preflight/factory.py intake \
  [--brief '<json>' | --brief-file <path>] \
  [--settings-file <path>] [--resume-file <path>] [--run-id <id>]
```

Verified live on this box (2026-10-06, packaged copy):

- thin brief `{"offer": "demo offer"}` -> `outcome=waiting`,
  `reason_code=missing-essentials`, exit 2, exactly three questions
  (`audience_action`, `spending_authority`, `placement` — placement
  substitutes into a leftover slot; the essentials are offer, audience +
  action, spending authority).
- `data.summary` carries a sha256 digest (first 16 hex); `auth_status` is
  `missing` / `expired` / `out-of-scope` / `bound`.
- brief text is never authorization; instruction-override patterns ->
  `rejected` / `untrusted-injection-blocked`.

Resume: no changes -> `ok` / `resume-no-changes`; approval-affecting change
-> `parked` / `resume-approval-invalidated`; outstanding decisions ->
`waiting` without re-running the questionnaire.

## `preflight`

```bash
python3 scripts/core/intake_preflight/factory.py preflight \
  [--root <approved-storage-root>] [--storage-dir <path>] \
  [--ref <path>]... [--require-tool <name>]... [--require-module <name>]... \
  [--profile short-9x16-30s] [--allowed-profiles '<json>'] \
  [--schema-version blackceo.campaign/v1] [--allowed-schemas '<json>'] \
  [--credential <name>]... [--auth-file <path>] [--summary-digest <hex>] \
  [--min-free-bytes <n>]
```

Check order and reason codes (`preflight.py:check`):

```text
schema-untrusted (error)
-> delivery-profile-unknown (rejected)
-> reference-outside-approved-storage (rejected)
-> reference-missing-or-truncated (error)
-> tool-unavailable / module-unavailable (error)
-> storage-not-writable / disk-limit (error)
-> credential-missing (rejected)
-> approval-missing / approval-expired / approval-out-of-scope (rejected)
-> ok / preflight-pass
```

Tools resolve via `shutil.which`, modules via import, disk via
`disk_usage`. Preflight never executes a tool, never submits generation and
never logs credential values.

Verified live on this box (2026-10-06, packaged copy): no `--auth-file` ->
`outcome=rejected`, `reason_code=approval-missing`, exit 4,
`next_action="Record authorization scope before paid work."`.

## Missing helpers

A required helper that is absent produces `module-unavailable` or
`tool-unavailable` (exit 1) naming the missing module/tool. That is the
actionable dependency error required by directive 2.4: install the helper,
do not substitute a static fallback and do not weaken the check.
