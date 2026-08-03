# Skill 41 — Build With AI Playbook: design rules (canonical deep reference)

> **This file is the CANONICAL, FULL text of Skill 41's design rules.**
> It is a Teach-Yourself-Protocol DEEP FILE and is **never** pasted into a box's
> `MEMORY.md`. `scripts/04-update-core-files.sh` writes exactly ONE compact
> pointer block into `MEMORY.md` (marker `<!-- BEGIN skill-41 memory-rules -->`)
> that points here.
>
> **Why:** core bootstrap files are re-billed to the model on every single turn,
> so rule corpora live in deep files and core files carry pointers only (TYP).
> Per-rule enforcement detail lives in `protocols/*.md` and `references/*.md`.

---

## Build With AI design rules

1. **Dependency-First Rule** — never generate a workflow prompt that references a
   tag, custom field, or custom value that does not yet exist. Create the
   dependencies via the GHL API first, verify with GET, then build.
   See `protocols/dependency-creation-protocol.md`,
   `references/ghl-dependency-protocol.md`, `scripts/qc-dependency-order.sh`.
2. **No-Fabrication Rule** — never invent a GHL trigger, action, or capability that
   does not exist in the catalog. Absence routes to an honest gap plus the
   operator manual path. See `references/ghl-triggers-catalog.md`,
   `references/ghl-actions-catalog.md`, `scripts/qc-no-fabrication.sh`.
3. **ZHC-Prefix Rule** — agent-created tags carry the `ZHC-` prefix; agent-created
   custom fields carry the `ZHC_` prefix. Never rename existing operator-owned
   tags or fields. See `scripts/qc-zhc-tag-prefix.sh`.
4. **Verification Rule** — every build runs the 12-point verification checklist
   before publishing. A build without verification is incomplete.
   See `protocols/verification-checklist.md`.
5. **Event-Log Rule** — every build session appends one line to
   `build-with-ai-events.jsonl` (field names and counts only, never raw PII).
   See `references/f52-data-contract.md`.
6. **Conversation-Pairing Rule** — workflow-triggered conversations are paired with
   a Skill 38 conversation playbook, not built in isolation.
   See `protocols/build-with-ai-protocol.md`.
7. **Operator-Approval Rule** — dependency creation is an allow-list action. The
   operator approves (standing approval for `ZHC-` / `ZHC_` prefixed objects). A
   customer can never cause a field or tag to be created.
   See `protocols/dependency-creation-protocol.md`.
