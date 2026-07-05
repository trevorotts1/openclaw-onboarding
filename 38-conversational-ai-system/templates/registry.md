# Conversation Workflows Registry (template)

This is the canonical shape of the client's
`<MASTER_FILES_DIR>/conversation-workflows/registry.md`. The registry is the
single source of truth the agent reads on every reply turn (via AGENTS.md Step
1.75) to decide which workflow (if any) applies. The authoritative prose lives in
`protocols/conversation-workflows-protocol.md` Section F; this file is the
copy-ready table header.

## Active workflows

| ID | Name | Trigger summary | Layer 1? | OpenClaw playbook | GHL prompt | Verification checklist | Tools | Visual | Doc (Notion/Docs/text) | Verification completed |
|---|---|---|---|---|---|---|---|---|---|---|
| appointment-booking | First playbook | "book", "schedule" | No (uses existing inbound) | appointment-booking.md | n/a | n/a | book_appointment, check_availability, update_tags, update_contact, reference_documents | diagram.png | https://www.notion.so/client/appointment-booking-abc123 | n/a (Layer 1 not built) |

## Column notes

- **Tools (U-1)**: the row's MOST PERMISSIVE phase tool set, for at-a-glance
  review of what the workflow can do at its most capable phase. This is a
  human-readable summary only; the ENFORCED gate is per-phase inside the playbook
  (`tools:` lines, Section E.5), resolved at runtime from the conversation log
  header by `tools/playbook_engine.py`. `escalate_to_human` is always granted and
  is omitted from this summary because it is implicit on every phase. A blank
  Tools cell means the workflow runs on the safe-minimum default
  (`reference_documents` + `update_tags`).
- **Visual (U-11)**: the recorded truth diagram (`diagram.png`) and, when present,
  the client hero image, populated by `scripts/31-generate-workflow-visual.sh`.
- **Doc (Notion/Docs/text)**: MANDATORY and machine-enforced by
  `scripts/qc-playbook-doc.sh` (Notion then Google Docs then plain-text fallback).
- **Verification completed**: the returned end-to-end test result for Layer-1
  workflows; a Layer-1 "No" row is legitimately `n/a (Layer 1 not built)`.
