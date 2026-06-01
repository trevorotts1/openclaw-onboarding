# F52 Data Contract -- Skill 41 Build With AI Playbook Generator

## Purpose

The append-only JSONL event log contract for build-with-ai sessions. Every build session appends one or more lines to MASTER_FILES_DIR/build-with-ai-events.jsonl.

## Common Fields (every event)

| Field | Type | Meaning |
|---|---|---|
| ts | string (ISO-8601 UTC) | When the event was appended |
| skill | string | Always "41-build-with-ai-playbook" |
| event | string | One of the event types below |
| session_ref | string | Opaque session reference (NOT PII) |
| source | string | Data origin: "ghl_catalog", "operator", "api_response", "script" |

## Event Types

### brainstorm_started
Emitted when the operator asks to build a workflow and the brainstorm flow begins.

| Field | Type | Meaning |
|---|---|---|
| operator_intent_summary | string | One-sentence summary of what the operator wants |

```
{"ts":"2026-05-30T20:00:00Z","skill":"41-build-with-ai-playbook","event":"brainstorm_started","session_ref":"sess_a1b2","source":"operator","operator_intent_summary":"New lead welcome email with 1-day SMS follow-up"}
```

### dependency_audited
Emitted after the dependency audit step lists missing dependencies.

| Field | Type | Meaning |
|---|---|---|
| missing_tags | array | Tag names that need creation |
| missing_fields | array | Custom field names that need creation |
| missing_values | array | Custom value names that need creation |

```
{"ts":"2026-05-30T20:01:00Z","skill":"41-build-with-ai-playbook","event":"dependency_audited","session_ref":"sess_a1b2","source":"ghl_catalog","missing_tags":["ZHC-new-lead","ZHC-welcome-sent"],"missing_fields":[],"missing_values":["welcome_email_subject"]}
```

### dependency_created
Emitted after each tag, field, or value is created via GHL API.

| Field | Type | Meaning |
|---|---|---|
| object_type | string | "tag", "field", or "value" |
| object_name | string | Name of the created object |
| zhc_prefixed | boolean | True if name starts with ZHC- or ZHC_ |

```
{"ts":"2026-05-30T20:02:00Z","skill":"41-build-with-ai-playbook","event":"dependency_created","session_ref":"sess_a1b2","source":"api_response","object_type":"tag","object_name":"ZHC-new-lead","zhc_prefixed":true}
```

### prompt_generated
Emitted when the standardized 8-section prompt is generated.

| Field | Type | Meaning |
|---|---|---|
| prompt_section_count | integer | Number of sections (should be 8) |
| sections_present | array | List of section names present |

```
{"ts":"2026-05-30T20:03:00Z","skill":"41-build-with-ai-playbook","event":"prompt_generated","session_ref":"sess_a1b2","source":"ghl_catalog","prompt_section_count":8,"sections_present":["workflow_name","trigger","dependencies","actions","conditions","webhook","settings","verification"]}
```

### build_initiated
Emitted when the operator confirms and pastes the prompt into GHL.

| Field | Type | Meaning |
|---|---|---|
| operator_confirmed | boolean | True if operator explicitly confirmed |

```
{"ts":"2026-05-30T20:04:00Z","skill":"41-build-with-ai-playbook","event":"build_initiated","session_ref":"sess_a1b2","source":"operator","operator_confirmed":true}
```

### build_completed
Emitted after the workflow is built and verified.

| Field | Type | Meaning |
|---|---|---|
| workflow_name | string | Name of the built workflow |
| verification_score | integer | Score out of 12 |

```
{"ts":"2026-05-30T20:05:00Z","skill":"41-build-with-ai-playbook","event":"build_completed","session_ref":"sess_a1b2","source":"operator","workflow_name":"New Lead Welcome Sequence","verification_score":12}
```

### verification_failed
Emitted when the verification checklist finds issues.

| Field | Type | Meaning |
|---|---|---|
| failed_items | array | List of checklist items that failed |
| fix_suggested | string | Human-readable fix recommendation |

```
{"ts":"2026-05-30T20:05:00Z","skill":"41-build-with-ai-playbook","event":"verification_failed","session_ref":"sess_a1b2","source":"script","failed_items":["Tag ZHC-welcome-sent does not exist"],"fix_suggested":"Create tag ZHC-welcome-sent before publishing"}
```

### webhook_configured
Emitted when a workflow includes a Custom Webhook action.

| Field | Type | Meaning |
|---|---|---|
| method | string | HTTP method (GET/POST/PUT/DELETE) |
| url_domain | string | Domain only (NOT full URL with tokens) |
| save_response_enabled | boolean | Whether save response is enabled |

```
{"ts":"2026-05-30T20:03:00Z","skill":"41-build-with-ai-playbook","event":"webhook_configured","session_ref":"sess_a1b2","source":"ghl_catalog","method":"POST","url_domain":"api.example.com","save_response_enabled":true}
```

### conversation_playbook_paired
Emitted when a workflow is paired with a Skill 38 conversation playbook.

| Field | Type | Meaning |
|---|---|---|
| workflow_id | string | Workflow identifier or name |
| playbook_path | string | Path to the conversation playbook |

```
{"ts":"2026-05-30T20:06:00Z","skill":"41-build-with-ai-playbook","event":"conversation_playbook_paired","session_ref":"sess_a1b2","source":"operator","workflow_id":"new-lead-welcome","playbook_path":"conversation-workflows/new-lead-welcome.md"}
```

## PII Discipline

The event log records:
- Object names and counts
- Workflow names
- Section names
- Domain names (not full URLs)

The event log NEVER records:
- Raw contact data
- Full webhook URLs with tokens
- API keys or credentials
- Phone numbers or emails
