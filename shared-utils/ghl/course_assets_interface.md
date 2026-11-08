# Course asset normalizer — frozen interface (WF12-CP01)

Consumer: WF08 course native media binding. Contract: Document 1 sections 10.3–10.5.
Module: `shared-utils/ghl/course_assets.py`. Stdlib only, no network, no credentials,
no model/provider policy.

## Manifest (schema_version `1.0.0`)

```
asset_key          "course_key:module_key:lesson_key:role"   stable logical key
course_key module_key lesson_key role                        never a display title
modality           derived from role (image/video/audio/text/document)
provider model_id provider_task_id                           owner-selected, never overridden
generation_state   queued|running|submitted|validated|completed|failed|blocked
local_path sha256 mime_type byte_size duration_seconds       bytes required only when completed
durable_url storage_access                                  temporary provider URL is not durable
qc                 {"state": passed|failed|not_run, "receipt_ref"}
ghl_binding        {"state": not_started|in_progress|bound|failed, content_id, lesson_id}
manifest_revision updated_at
```

Rules: `completed` is the only finished state. `sha256`/`byte_size`/`mime_type` are
recomputed from the file at `local_path`; MIME must agree with the role family;
video/audio must carry `duration_seconds`; duplicate completions for one `asset_key`
update one record (repeat bytes = no-op, different bytes = recorded conflict).

## Functions

| Function | Contract |
|---|---|
| `logical_asset_key(course, module, lesson, role)` | `-> str`; raises `AssetError('bad_key')` |
| `parse_asset_key(key)` | `-> dict` of the four keys |
| `modality_for_role(role)` | `-> 'image'|'video'|'audio'|'text'|'document'|'other'` |
| `sniff_mime(head)` | `-> mime or None` from magic bytes |
| `file_facts(path)` | `-> {sha256, byte_size, sniffed_mime, real_path}` |
| `new_manifest(course, module, lesson, role, provider='kie', model_id=None, provider_task_id=None)` | pre-generation manifest, `generation_state='queued'` |
| `validate_manifest(m)` | `-> list[str]`; empty means handoff-legal |
| `assert_valid(m)` | raises `AssetError('invalid_manifest')` |
| `normalize_completion(m, local_path=..., durable_url=..., storage_access=..., duration_seconds=..., qc=..., mime_type=...)` | `-> completed manifest`; raises `AssetError` |
| `record_failure(m, reason)` | `-> failed manifest` |
| `completion_from_adapter_result(result, m, local_path=None, duration_seconds=None)` | Skill 74 envelope; queued stays incomplete; URL-only success is refused |
| `completion_from_callback_record(record, m, local_path, duration_seconds=None)` | Skill 46 record; `status != 'done'` or zero URLs is a failure |
| `bounded_poll(fetch_result, m, timeout_seconds=300, interval_seconds=3, backoff=1.5, max_interval_seconds=15)` | returns running with `poll_deadline_reached` at the deadline |
| `AssetStore().apply(m)` | `-> {record, changed, duplicate, conflict}`; one record per `asset_key` |
| `to_wf08_handoff(m)` | binding request; refuses anything not `completed`/valid |
| `handoff_batch(manifests)` | `-> {schema_version, assets[]}`; all-or-nothing |

## Handoff to WF08

```json
{"schema_version":"1.0.0","asset_key":"...","course_key":"...","module_key":"...","lesson_key":"...",
 "role":"lesson_video","modality":"video","local_path":"...","sha256":"...","mime_type":"video/mp4",
 "byte_size":123456,"duration_seconds":42.5,"durable_url":"https://...","storage_access":"approved_for_destination",
 "qc":{"state":"passed","receipt_ref":"..."},"ghl_binding":{"state":"not_started","content_id":null,"lesson_id":null}}
```

A later change is `WF12-CP02` with a migration note and the affected-consumer list.
