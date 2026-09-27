# Teach Yourself Protocol - How to Use

## 1. Announce and understand

Briefly announce TYP when retaining lasting knowledge. Identify the topic, source, owner/client scope and intended future use. Explicit learning requests authorize this work. Temporary task inputs stay with their task; a long attachment alone is not evidence that every detail belongs in permanent memory. Resolve ambiguous intent only when it matters.

## 2. Search before creating

Search the relevant core entries, installed skill and canonical master folder for this topic. Update the authoritative existing document. Follow current owner corrections; use source evidence to resolve stale instructions. Ask only when a material contradiction remains genuinely unresolved. Never create another master folder because the first search missed the existing one.

## 3. Choose storage by purpose

| Content | Destination |
|---|---|
| API/tool procedure, model list, pricing, endpoint details | Canonical deep reference, with one TOOLS.md pointer if needed |
| Workflow/playbook/SOP | `playbooks/` reference, with one AGENTS.md pointer if needed |
| Durable owner preference or fact | Its existing appropriate USER.md or MEMORY.md entry; no automatic duplicate |
| Essential global behavioral rule | Concise AGENTS.md rule, only if it applies generally |
| Installation/learning receipt or diagnostic history | Installation log, changelog or task record outside bootstrap |
| Task state/handoff | Project PRD/TODO or active task record |
| Related subtopic already reachable from a core index | Link from that reference index; no additional core entry |

Content length does not make a procedure eligible for bootstrap. A short procedure still belongs in its reference. A single durable fact does not require a new deep file or a version-history table.

## 4. Store the complete reference

Reuse the existing canonical root:

- Mac: `~/Downloads/openclaw-master-files/` (resolve the home directory in actual pointers).
- Documented Docker VPS layout: `/data/.openclaw/master-files/`.

Use `apis/`, `skills/`, `processes/`, `references/`, or the dedicated `playbooks/` subfolder for playbooks/books/SOPs. Create only a needed subfolder. On a Docker VPS verify that the destination is inside its persistent bind mount before writing; the documented deployment uses `/data/.openclaw/`. Do not treat temporary/container-root paths as durable storage.

Preserve the complete supplied reference or its original source alongside an organized guide. Do not silently discard source details. Record source, scope, last verification date, version and related documents in the deep file. Keep history there, not in bootstrap. Credentials remain in the authorized secret store; references describe how to retrieve them without copying secret values.

## 5. Write one short pointer, if needed

Use one sentence stating the task trigger, what the reference covers and its exact absolute path. Example template:

`Before using ClickUp, read <absolute-canonical-root>/apis/clickup.md for setup, API operations and troubleshooting.`

Resolve the placeholder and verify the file before installing the pointer. Load the relevant reference before acting, including routine use; do not expect the pointer to contain the procedure. There is no minimum length or requirement to answer operational questions in core. Expand the reference itself when details are missing.

Prefer one appropriate core file, or an already-linked reference index. Do not add duplicate pointers to every core file and do not record “learned/installed [date]” in MEMORY.md. Independent durable facts may be revised where they already belong. Use a stable version-free block ID for managed pointers, replacing it in place.

## 6. Validate and commit safely

On compact workspaces, check whole-file character budgets: AGENTS.md ≤15,000; MEMORY.md ≤8,000; TOOLS.md ≤15,000. Preserve exact owner facts, reference paths and balanced markers. Compare the expected current hash, use the shared writer lock and atomic replacement, and coordinate deliberate shrinkage with the approved watcher baseline. Run the installed core validator. An identical second run must change no core bytes and create no backup. Stage unresolved core changes for review; never claim pending work applied.

Current explicit owner instructions override historical source examples and default storage choices. Honor a deliberate owner exception without silently bypassing the validator or recovery baseline; report and coordinate the required exception.

## 7. Confirm

Tell the user what was stored or corrected, the authoritative location, and which entries changed. State when an existing pointer made core changes unnecessary. Keep the installation/learning receipt in this completion or task record, not in MEMORY.md.

## Priority and maintenance

Priority (CRITICAL, HIGH, STANDARD, REFERENCE) controls retrieval/review urgency, never pointer length or number of core copies. Verify volatile facts before relying on them; old verification dates and unexpected errors are prompts to recheck. Update broken paths and source conflicts in place. See MIGRATION-TYP.md for legacy cleanup and teach-yourself-protocol-full.md for the complete protocol.
