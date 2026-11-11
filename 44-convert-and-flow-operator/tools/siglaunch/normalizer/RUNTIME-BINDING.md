# runtime-binding.json: the normalizer install step (issue 31)

Skill 83's checkout rule (`AF-LAUNCH-CHECKOUT-RUNTIME`) lets a checkout piece carry a status of
`live_verified` or `ready_for_activation` only when the package holds a `runtime-binding.json`.
This directory writes it. Nothing else does, and nothing hand-writes it.

```bash
python3 44-convert-and-flow-operator/tools/siglaunch/normalizer/normalizer.py --emit-binding <package-dir>
```

`<package-dir>` gets `runtime-binding.json`; a path that is not an existing directory is used as the
file name (its folder must exist). The command prints the written path and exits 0. It exits 7 and
writes nothing when any probe fails or the folder is missing. Any other invocation of `normalizer.py`
still exits 6 (`PRODUCTION_ENTRY_ENABLED` stays `False`; these modes ingest no live event and start no
runner).

To check a record that already exists (read-only, writes nothing):

```bash
python3 44-convert-and-flow-operator/tools/siglaunch/normalizer/normalizer.py --verify-binding <package-dir-or-file>
```

It re-runs the probes and exits 0 only when the file holds exactly the six keys, every value is what
the probes prove now, `evidence_ref` carries the digest they re-derive, and `verified_at` is a
`YYYY-MM-DDTHH:MM:SSZ` time. A hand-written file, a flipped value, an invented digest, or a record
written by a normalizer that has since changed behaviour exits 7. Skill 83's rule proves the record is
present, well formed and sealed in the package; this is the call that proves the normalizer wrote it.

## What is written (exactly six keys)

| Key | Value |
|---|---|
| `normalizer` | `44/tools/siglaunch/normalizer` |
| `schema_version` | the highest purchase-event schema version this normalizer stamps (read from the vendored schema, `1.2` today) |
| `grant_policy` | `once` |
| `paid_edges_only` | `true` |
| `verified_at` | UTC time the probes passed, `YYYY-MM-DDTHH:MM:SSZ` |
| `evidence_ref` | `siglaunch-normalizer-probe:sha256:<digest of the probe transcript>` |

## Why the values are true

The values are not constants copied into a file. `--emit-binding` first runs the real normalizer,
processor and store on probe events in a throwaway database and refuses unless all eight pass:

| Probe | Proves |
|---|---|
| `paid-event-grants` | a verified `succeeded` event is accepted, processed, and the right is `active` |
| `redelivery-is-duplicate` | the same provider event again is `duplicate` (the inbox keeps one) |
| `replay-grants-nothing-more` | processing the same event again creates 0 actions and 0 reconciled rights |
| `pending-never-grants`, `failed-never-grants`, `requires_customer_action-never-grants`, `unknown-never-grants` | each is processed as `no_grant:<status>` and no right is recorded |
| `refund-revokes-never-grants` | a refund only revokes: the right ends `revoked` |

The transcript has no clock and no random id, so re-running the probes re-derives the same digest;
`test_emit_binding.py` proves that, and proves that breaking each claim in the real code path
(a processor that grants unpaid events or grants twice, a store that does not dedupe, a refund that
leaves the right active) makes the command refuse and write nothing.
