# The Teach Yourself Protocol

OpenClaw knowledge storage protocol. Compact policy revision: September 17, 2026.

## 1. Purpose

Retain lasting knowledge in a discoverable place while keeping startup context small. Core files contain essential durable facts/rules and short retrieval pointers. Detailed procedures live in authoritative references. File size limits are ceilings, not targets.

## 2. Triggers and scope

Explicit requests include “teach yourself,” “learn,” “memorize,” and “save for future reference.” A permanent owner correction or clearly reusable workflow may also trigger TYP. Announce its use briefly. Distinguish lasting knowledge from temporary task inputs and credentials supplied for one operation; length alone does not establish permanent intent. Use existing authorization, resolving only material uncertainty. Keep private owner information and client documents within their proper scope.

## 3. Three storage layers

1. Core: essential global rules, durable owner facts and a short trigger plus exact path to needed references.
2. Deep reference: complete procedures, API details, examples, troubleshooting and provenance.
3. Topic index/folders: organized references for large collections, linked from one discoverable entry.

A core pointer tells the agent what to read before a related task. It is not a miniature manual. There is no minimum line count, requirement to answer five operational questions in bootstrap, or presumption that routine tasks should proceed without reading the reference. A document already reachable through the appropriate reference index needs no extra core pointer.

## 4. Decision process

Understand topic/source/scope; search existing core and reference entries; resolve conflicts; choose the authoritative destination; preserve or update the full reference; add or revise one short pointer only if needed; validate; confirm. Prefer an existing durable fact entry over a second copy. Record receipts, installation history, diagnostics and handoff state in logs/changelogs/task records outside bootstrap. Do not add MEMORY.md entries merely because learning happened.

## 5. APIs

Use a canonical API folder with a README index when the API has multiple topics. Keep source URLs, verification date, authentication conventions, base URLs, endpoints, payloads, rate limits, pricing, async/polling patterns, examples and pitfalls in the reference. Organize large APIs by endpoint category. Preserve supplied originals or an archived source alongside curated guidance when necessary; do not replace a complete source with an incomplete summary. Secret values remain in the authorized secret store; document retrieval conventions without exposing them. Before calls, read the relevant API/skill instructions and verify volatile details when needed. One TOOLS.md trigger may point to the API index; auth and endpoint details do not also belong in a memory receipt.

## 6. Skills and instructions

Every skill needs matching execution instructions. A standalone skill may have `<master-root>/skills/<skill-name>.md`; an installed skill uses `~/.openclaw/skills/<skill-name>/SKILL.md`. The installed SKILL.md governs execution; the master reference preserves complete source and extended documentation. Resolve conflicts with current owner instructions and compact storage policy. A skill's CORE_UPDATES.md cannot demand that its entire manual be pasted into core.

Instructions should cover purpose, triggers, exclusions, prerequisites, commands, workflows, pitfalls, related skills and authoritative sources. Follow declared dependency and file read order when installing. TYP has no prerequisite skills and is installed first. SKILL.md YAML frontmatter must remain at the very beginning so skill discovery can parse it. Packaged archives must match their reviewed source documents before use.

## 7. Owner override

Current explicit owner instructions govern storage choice, including a deliberate request to put content in a named core file or save a short fact separately. Follow the request and explain any material size tradeoff. Coordinate any deliberate exception with the configured budget validator and recovery watcher; do not silently defeat those mechanisms. Old examples, versioned installer payloads, or ambiguous document text are not fresh owner overrides.

## 8. Conflict resolution

Search before writing. A current owner correction supersedes the stale fact it corrects; revise it in place. For additions, update the relevant reference section and changelog without duplicating existing prose. For a material unresolved contradiction, obtain the missing source/owner clarification before changing the contested meaning. Reorganizing a misplaced procedure requires preserving its content, replacing the original with an appropriate pointer, and checking downstream paths. Update existing contradictory copies rather than creating a new parallel source. Distinguish current policy from dated evidence.

## 9. Priority

CRITICAL covers core operations or high-impact errors; HIGH covers frequent important work; STANDARD covers occasional use; REFERENCE covers edge cases. Priority influences review urgency and retrieval, not core-entry length or duplication. Detailed facts remain in the reference at every priority level.

## 10. Versioning and staleness

Deep references should record source, scope, purpose, last verified date, version, related files and a concise change history. Use major versions for fundamental process/auth/API changes and minor versions for additions or corrections. Dates are evidence, not guarantees: volatile data may need immediate verification; old dates, unexpected errors or announced platform changes warrant review. Do not expire a settled owner fact merely because it is old. Keep dated installation/learning records out of MEMORY.md.

## 11. Cross-references

Link related APIs, processes and skills in the deep reference or topic index, with a short explanation. Check these dependencies when debugging a multi-service workflow. Resolve links from their documented base and verify targets. A related reference does not automatically need a separate core entry. When moving a document, update all existing incoming links or preserve a deliberate compatibility pointer.

## 12. Interrupted work

Keep progress in the named task/PRD/TODO. On resumption, verify that source documents are complete, targets exist, pending edits are reconciled and the relevant index/pointer reaches them. Do not assume every unreferenced file is an orphan: it may be reachable through a topic index. Complete missing work, then report actual changes. Do not fabricate a completion or promote the handoff into durable memory.

## 13. Storage and anti-bloat rules

Reuse the canonical master root rather than inventing another copy. Mac default: `~/Downloads/openclaw-master-files/`. Documented Docker VPS root: `/data/.openclaw/master-files/`; verify the persistent bind mount before writing. Organize under apis/, skills/, processes/, references/; books/playbooks/SOPs belong in playbooks/. Resolve final pointers to exact absolute paths, not placeholders or guessed names.

Choose one appropriate core destination or an already-linked index. A pointer states the task trigger, document purpose and exact path in one short sentence. Load the reference before acting and narrower sections as needed. Do not preload every reference at startup. Procedures stay external even when short. Essential global rules and durable owner facts may remain directly in their appropriate core file.

Whole-file compact budgets: AGENTS.md 15,000 characters; MEMORY.md 8,000; TOOLS.md 15,000. Character counts, not line counts, detect long-line bloat. No automatic multi-core fanout, installation/learning receipts in memory, version-specific duplicate blocks, transcript/promotional fragments, or audit-log recycling. Detailed writer proposals stay pending outside bootstrap until reconciled.

## 14. Updating safely

Use a stable version-free ID and replace an existing managed pointer in place. Compare the expected current hash, coordinate the shared writer lock, back up changed content and atomically replace it. Validate whole-file budgets, exact targets and balanced markers/fences. A deliberate large reduction must update the approved watcher baseline through its migration mechanism so recovery does not undo it. A repeated identical update must change no core bytes or produce a redundant backup. Never report a staged proposal as applied. Keep genuine changes and receipts outside core; retain backups according to the configured 14-day policy.

## 15. Execution checklist

- Identify lasting intent, source and owner/client scope; announce TYP.
- Search and choose one authoritative existing destination.
- Resolve stale facts without deleting useful source details or exact owner quotations.
- Save the complete reference in persistent storage and link related deep documents.
- Choose one necessary trigger pointer or update a durable fact where it belongs.
- Validate budgets, paths, markers, concurrency protection and watcher baseline coordination.
- Confirm actual changes and any pending work; keep receipts outside bootstrap.

## 16. Examples

For a KIE.ai manual, update its API reference and existing TOOLS.md pointer; do not record “API learned” in MEMORY.md. For a durable writing preference, update its existing preference entry once. For a large skill collection, preserve source files and create one index; do not copy every skill rule into AGENTS.md. For an owner API-scope correction, replace stale scope guidance at its authoritative reference and clean up existing contradictory copies. For temporary chart input, keep it with that task. EXAMPLES.md contains worked cases.

## 17. Installing TYP itself

Follow SKILL.md's file read order and INSTALL.md's ordered steps. Reuse the canonical master root, preserve the full source folder there, then copy reviewed skill files to the installed skills folder. Follow CORE_UPDATES.md: use or update one existing AGENTS.md/index trigger; no installation writes to MEMORY.md, TOOLS.md, IDENTITY.md, SOUL.md, USER.md or HEARTBEAT.md are required. TYP needs no external API key or unsupported install command. Retain the existing gateway-restart restrictions; this documentation cleanup itself needs no gateway restart.

## 18. Common errors

Avoid pasting manuals into core, omitting a trigger/path, requiring a minimum pointer length, duplicating one fact across several files, adding learned-date receipts to memory, creating duplicate master roots, storing durable VPS files outside the persistent mount, overwriting concurrent edits, retaining broken references, and invoking a legacy writer that recreates retired payloads. Preserve original source details in references or recovery history, while removing obsolete active instructions. A short precise pointer is sufficient when it reliably leads to the complete procedure before use.

## 19. Final verification

Verify discoverability through one pointer/index; source completeness; current owner facts and privacy scope; correct installed skill frontmatter and declared read order; persistent storage; no contradictory current copies; exact target existence; character budgets; valid markers; unchanged results on a second identical run; and a truthful completion. Keep native memory features active unless separately changed for a demonstrated reason. Automated review logs, installation notices, temporary scores and malformed promotion fragments are never durable facts.
