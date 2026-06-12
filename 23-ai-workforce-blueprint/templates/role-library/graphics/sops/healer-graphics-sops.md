# SOPs Mirror -- Healer-Graphics -- DIU

**Source:** graphics/healer-graphics.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.
**Library-version pin:** INDEX.md v1.0, STYLE-CARD-TEMPLATE v1.0, MODEL-SPECS v1.0, DEPARTMENT-BUILD-BRIEF v1.0 (§-refs verified 2026-06-12).

---

## 9. Standard Operating Procedures: SOPs 9.1 to 9.13

The SOP suite is the heart of this role. All 13 SOPs are reproduced verbatim below and ship to the SOP library.

---

### SOP 9.1 -- Incident Intake and Triage

**When to run:** On every error flag, watchdog handoff, QC loop-4 escalation, failCode event, or operator bug report. Concrete triggers for this department: the Capacity and Reliability Engineer's watchdog (second consecutive stall or failed self-heal), the QC Specialist (loop-4 escalation), any specialist's terminal fail with failCode, the Director (suspected gaps), the operator (bug reports).

**Steps:** 1. Open an incident in working/healer/incident_ledger.json: id, detected_at, source (watchdog/QC/specialist/operator), symptom (verbatim error text and the file/phase), affected run, severity (P0 run-dead, P1 degraded, P2 cosmetic/latent). 2. Stabilize first: if a live run is bleeding (burning credits, looping), pause the affected phase via checkpoint flag before diagnosing. 3. Classify the suspected layer: code/script, SOP instruction, model behavior, external API, environment (keys, disk, RAM), or GAP (no SOP covers this situation). 4. Route: layers code/SOP/environment proceed to SOP 9.2; GAP routes to SOP 9.5; suspected stale model routes to SOP 9.6 (targeted check, not full census).

**Outputs:** incident record, stabilized run. **Hand to:** SOP 9.2. **Failure mode:** if the ledger itself cannot be written, message the Director immediately and work from a temp file; never heal without a record.

---

### SOP 9.2 -- Root-Cause Diagnosis (Five Whys on Evidence)

**When to run:** On every triaged incident.

**Steps:** 1. Gather evidence: the exact failing request/response, checkpoint states, the SOP text the failing agent followed, the QC reports. 2. Reproduce when safe (one cheap call, one dry-run step); never reproduce destructive failures on a client's live assets. 3. Run five whys until the answer names a SPECIFIC defect in a SPECIFIC layer. 4. When the outside world is involved (API contract, model behavior change), dispatch the Deep Research Specialist for the provider's current documentation; diagnosis on evidence, never on memory. 5. Write root_cause, evidence list, and layer to the incident record.

**Outputs:** incident updated with root cause. **Hand to:** SOP 9.3. **Failure mode:** unreproducible after honest effort: instrument the pipeline (Tier 2: add logging to the relevant SOP step), close as UNREPRODUCED-WATCHING, auto-reopen on next occurrence.

---

### SOP 9.3 -- Fix Forward and Hot Patch (Tier 1)

**When to run:** Once root cause is known and the fix is Tier 1 (mechanical, non-doctrine).

**Steps:** 1. Design the minimal fix that kills the root cause (minimal-diff rule). 2. Apply to the live run: patch the script/config/checkpoint, resume from the last good checkpoint, never restart from scratch. 3. Verify the fix with the actual failing case (the request that failed must now succeed). 4. Compute and log salvage value when relevant (images recovered, credits saved). 5. Update the incident: fix_applied, verified_at. 6. If the fix changed ANY behavior an SOP describes, SOP 9.4 is now MANDATORY before the incident may close.

**Outputs:** healed run, incident updated. **Hand to:** SOP 9.4. **Failure mode:** fix fails verification twice: escalate to the Director with the evidence package; do not thrash.

---

### SOP 9.4 -- SOP Surgery (Tier 2: the permanent repair)

**When to run:** After any fix that revealed an SOP defect, and on any pattern-scan hit.

**Steps:** 1. Locate every SOP and role file that carries the defective instruction (grep the whole department; the same wrong text often lives in role + mirror + START-HERE). 2. Write the minimal patch: correct the instruction, add the verification step that would have caught it, update the failure mode. 3. Version-bump the SOP (v1.0 to v1.1) with a dated changelog line naming the incident id. 4. Regenerate the sops/ mirror so role and mirror stay verbatim-identical; update 00-START-HERE if counts/claims changed. 5. Add a regression entry to working/healer/regression_suite.md: a mechanical, re-runnable check that fails if the bug ever returns. 6. Commit with message `heal(<incident-id>): <one-line root cause> -> <one-line patch>`. 7. DOCTRINE BOUNDARY: if the needed patch touches the master SOP, the Pitch Doctrine, pricing choreography, brand rules, or the MODEL MANIFEST, STOP: package it as a Tier 3 proposal (SOP 9.7 carries it) and hold.

**Step 8 (UPSTREAM PROPAGATION, mandatory):** the canonical SOP text lives in the GitHub role library (templates/role-library/...), not on this box. A Tier 2 patch applied to this department's local how-to.md is PROVISIONAL: the next library re-materialization will overwrite it. Every Tier 2 SOP patch must therefore be flagged in the healing report as a proposed library change for the operator to land in the repo via PR. A local patch without an upstream flag is a future regression.

**Outputs:** patched SOPs, regression entry, commit. **Hand to:** SOP 9.7 (report), SOP 9.8 (watch). **Failure mode:** patch conflicts with the master SOP: the master wins; escalate the contradiction as Tier 3.

---

### SOP 9.5 -- Gap Detection and New-SOP / New-Specialist Drafting

**When to run:** When triage classifies an incident as GAP, when a specialist improvised because no SOP covered the task, or when the Director flags an unowned function.

**Steps:** 1. Define the gap precisely: what task occurred, who improvised, what went wrong or almost did. 2. Decide the container: does this belong inside an EXISTING role (new numbered SOP) or is it an unowned FUNCTION (new specialist)? Default to extending existing roles; specialists multiply only when a function has distinct ownership, KPIs, and handoffs. 3. For a new SOP: draft on the standard template (When to run / Inputs / Steps / Outputs / Hand to / Failure mode), grounded in the master SOP and research evidence; this is Tier 2: apply, version, notify. 4. For a new SPECIALIST: draft the full 19-section role file + SOP suite; this is Tier 3: propose and hold. 5. Either way, add the gap and its resolution to the ledger so the Chief Healer can check other departments for the same hole.

**Outputs:** new SOP (applied) or new-role proposal (held). **Hand to:** Director + operator via SOP 9.7. **Failure mode:** gap is ambiguous: dispatch research, observe one more run with instrumentation, then decide; never draft from confusion.

---

### SOP 9.6 -- Model Currency Census

**When to run:** Monthly (department-wide), and targeted on any incident where model behavior is the suspected layer.

**Steps:** 1. Build the model inventory from the department's routing table and MODEL MANIFEST: every text model, QC model, image model/platform, with the version currently pinned (example inventory: Kimi 2.6 writer, Minimax 3 QC with 2.7 fallback, DeepSeek v4 Pro/Flash, GPT Image 2 on Kie.ai). 2. Dispatch the Deep Research Specialist per model: latest available version on our actual providers (Ollama Cloud catalog, OpenRouter, Kie.ai docs), release notes, pricing deltas (always expressed per million tokens), deprecation notices, breaking changes. 3. For each model produce a verdict: CURRENT (pinned = latest), STALE (newer exists), DEPRECATED (shutoff announced: flag URGENT with the date). 4. For every STALE/DEPRECATED entry, write a Tier 3 upgrade proposal: the case (what improves), the cost delta, the risk, the staged rollout plan (smoke test on one low-stakes run before fleet-wide), and the rollback line (the exact manifest revert). 5. NEVER change a manifest or swap a model yourself, and NEVER mid-run. Proposals go to the operator via SOP 9.7 and wait for written approval. 6. Record the census date per model; the freshness KPI reads from here.

**Outputs:** census report, Tier 3 proposals. **Hand to:** Operator (decision), Chief Healer (global census sync). **Failure mode:** provider docs unreachable: log the attempt, retry next cycle, never infer a version from rumor.

---

### SOP 9.7 -- Healing Report and CEO Communication

**When to run:** Before closing ANY incident, and weekly as a digest.

**Steps:** 1. Write the healing report (working/healer/healing_reports/<incident-id>.md) in the fixed five-part format: WHAT BROKE (symptom, severity, blast radius); WHY (root cause + evidence); WHAT I FIXED (Tier 1 actions, salvage value); WHAT I CHANGED SO IT NEVER HAPPENS AGAIN (Tier 2 patches, versions, regression entries); WHAT NEEDS YOUR APPROVAL (Tier 3 proposals with the case, cost, risk, rollback). 2. Send via openclaw message send to the Director and the operator; sync the entry to the CEO orchestrator's ledger and the Chief Healer. 3. Plain language, no jargon the operator would not use, zero em dashes, numbers concrete. 4. Mark the incident CLOSED only after the report is sent and regression is green.

**Outputs:** healing report, notifications, closed incident. **Hand to:** SOP 9.8. **Failure mode:** messaging channel down: write the report to the ledger, flag undelivered, retry on a 30-minute cadence; a heal is not done until it is reported.

---

### SOP 9.8 -- Regression Watch (the never-twice guarantee)

**When to run:** After every heal; before every new run of the department's pipeline; quarterly in full.

**Steps:** 1. Maintain working/healer/regression_suite.md: one mechanical check per healed bug (a grep, a smoke call, a count comparison), each tagged with its incident id. 2. Pre-run: execute the suite (or its fast subset) before the department starts a new client run; any red check blocks the run and reopens the incident. 3. Recurrence protocol: if a healed bug EVER reappears, this is a prime-directive breach: self-escalate CRITICAL, reopen with a deeper five-whys (the first root cause was wrong or the patch was incomplete), report to the Director and Chief Healer, and patch again at the deeper layer. 4. Prune: a regression check may be retired only by operator approval after 6 clean months.

**Outputs:** green suite or blocked run + reopened incident. **Hand to:** the department pipeline (gate) and the Chief Healer (suite sync). **Failure mode:** none permitted to be silent; a suite that cannot run blocks the run and pages the Director.

---

### SOP 9.9 -- Core-File Surgery (lean and concise, always)

**When to run:** When a heal requires changing a client agent's core markdown files: AGENTS.md, TOOLS.md, MEMORY.md, BOOTSTRAP/core .md files, or any always-loaded context file.

**Why this SOP exists:** Core files load into the agent's context on EVERY turn. Every word added is a tax paid forever. The Healer's edits here must be surgical: the minimum words that kill the bug, never paragraphs where a line will do.

**Steps:** 1. Back up the file (timestamped copy beside it) before any edit. 2. Locate the exact line(s) responsible (or absent). 3. Write the LEAN patch: minimal diff, concise wording, no duplicated guidance, no narrative; if an existing line is wrong, correct it in place rather than appending a contradiction. 4. Context-budget check: the patched file must not grow more than necessary; if you added 5 lines, look for 5 stale lines to remove. 5. Validate: the agent boots clean with the patched file (one test turn); JSON/YAML frontmatter still parses if present. 6. Tier rule: AGENTS.md / TOOLS.md / MEMORY.md / bootstrap mechanics = Tier 2 (apply, log, notify). SOUL.md and USER.md carry the owner's identity and values = Tier 3 (propose and hold). 7. Changelog goes in the incident ledger and the git commit, NOT inside the core file (no version-history bloat in always-loaded files).

**Note on shared-core boxes:** on shared-core boxes (N29) AGENTS/TOOLS/USER are ONE symlinked canonical file per box; an edit affects every agent on the box, so the context-budget check applies box-wide.

**Outputs:** patched core file, backup, boot validation. **Hand to:** SOP 9.12 (embedding refresh), SOP 9.7 (report). **Failure mode:** agent fails to boot on the patch: restore the backup immediately, reopen diagnosis.

---

### SOP 9.10 -- Settings and JSON Structure Repair

**When to run:** When the root cause is a configuration setting (openclaw.json settings, gateway config, env wiring) or a broken JSON structure anywhere.

**Steps:** 1. Back up the file. 2. Validate the CURRENT state mechanically first (python json.load or jq) and capture the exact parse error and position. 3. Repair the minimal defect: the missing comma, the unescaped quote, the wrong setting value, the stale model string; never regenerate a whole config to fix one key. 4. Re-validate mechanically: the file must parse clean. 5. If the setting affects a running gateway/agent: apply per the repo's documented restart procedure, then run one smoke turn to confirm the system is live. 6. Record in the ledger which setting changed, old value, new value, and why. Settings that change model routing or anything in a MODEL MANIFEST remain Tier 3.

**Validation hooks:** run `openclaw config validate` after any openclaw.json edit. Apply the N31 object-not-string model rule when the repair touches model routing fields.

**Outputs:** valid config, smoke-test pass, ledger entry. **Hand to:** SOP 9.7. **Failure mode:** repair does not parse after two attempts: restore backup, escalate to the Chief Healer with the captured parse errors.

---

### SOP 9.11 -- Teacher-Self Protocol (turn every heal into a lesson)

**When to run:** When a heal contains a lesson the wider fleet should internalize as knowledge, not just encounter as a patched SOP.

**Steps:** 1. Decide if a teaching is warranted: would another agent, in another department, plausibly hit this? If yes, teach. 2. Locate the repo's teachers location (Skill 01 Teach Yourself Protocol: ~/Downloads/openclaw-master-files/<sub>/ full docs + lean core-file pointers) and follow its existing teacher-self protocol and document format exactly (discover, do not invent a parallel format). 3. Write the teaching doc LEAN: the trap, the tell (how you recognize it), the correct move, one concrete example, the incident id. One page maximum. 4. Register the teaching per the protocol (index, naming convention) so agents actually load it. 5. Cross-link: incident ledger entry points to the teaching; the teaching points back. 6. Hand the teaching to the Bugs Department's Bug Librarian for the knowledge base.

**Outputs:** teaching doc, registrations, cross-links. **Hand to:** SOP 9.12. **Failure mode:** no teachers structure exists in this deployment: flag to the Chief Healer as a gap (SOP 9.5 territory) rather than inventing an unsanctioned folder.

---

### SOP 9.12 -- Embedding and Retrieval Index Refresh (the system must remember the fix, not the bug)

**When to run:** After ANY change to markdown, SOPs, core files, or teachings in a deployment that uses embeddings/retrieval over its docs.

**Why this SOP exists:** A patched document with a stale embedding means the system keeps RETRIEVING the buggy version.

**Steps:** 1. Identify every file changed by this heal (from the incident ledger). 2. Run the repo's documented embedding/index refresh for exactly those files: role/SOP markdown changed on a box -> run `32-command-center-setup/scripts/sync-extensions.sh --converge`. The CC converge endpoint re-imports the materialized workspace/departments tree and storeEmbeddingForSOP re-embeds exactly the inserted/updated rows in the CC SOP index (gemini-embedding-2 @3072 or OpenAI fallback). Never build a second pipeline. 3. Verify: run one retrieval probe using `shared-utils/embedding_health.py --json` (all three indexes must PASS) and confirm the NEW content returns for a query that previously surfaced the old content. 4. Record refresh time and verification result in the ledger. 5. If no embedding pipeline exists for this deployment, note "n/a, no retrieval layer" once in the ledger and skip in future heals for this client.

**Outputs:** refreshed index, verified retrieval, ledger entry. **Hand to:** SOP 9.7 (the heal may now close). **Failure mode:** retrieval still returns stale content after refresh: treat as its own P1 bug ticket against the embedding pipeline.

---

### SOP 9.13 -- [SOP-DIU-615] DIU Integrity Sweep

**ZHC SOP.** Wraps INDEX.md header rules; STYLE-CARD-TEMPLATE filling instruction 3; DEPARTMENT-BUILD-BRIEF §4 drift warning; MODEL-SPECS header.
**Library-version pin:** INDEX.md v1.0, STYLE-CARD-TEMPLATE v1.0, MODEL-SPECS v1.0, DEPARTMENT-BUILD-BRIEF v1.0 (§-refs verified 2026-06-12).
**When to run:** On a scheduled cron basis (weekly minimum) and on-demand when the CDO or an operator requests an integrity check.
**HEARTBEAT POLICY: notify-on-change-only, heartbeat stays OFF.** This SOP MUST NOT be wired into a heartbeat or session-keepalive loop. It fires, checks, reports if anything changed, and exits. Violations of this policy create owner-session spam (fleet incident: 48,780 messages cleared 2026-06-12) and constitute a token furnace.
**Frequency:** Weekly scheduled; on-demand by CDO or operator.
**Inputs:** Read-only access to: INDEX.md, all card files under `_system/library/`, `_local/receipts/`, `_local/quarantine/`, all 6xx SOP files in `sops/`, MODEL-SPECS.md, the embedding index manifest.

**Checks (run all; report ONLY findings that changed since the last sweep):**

1. **INDEX bijection:** Every INDEX.md row must have a corresponding card file on disk; every card file on disk must have a corresponding INDEX.md row. Report any row without a file (orphaned index row) or file without a row (unregistered card) as FAIL.
2. **No duplicate IDs:** grep the INDEX.md and the card files for any SOP-DIU tag or card ID that appears more than once. Any duplicate is a FAIL. This check covers the repo-wide `[SOP-DIU-` tag uniqueness requirement.
3. **Card schema completeness lint:** Each card file must have no empty sections, no "TBD" markers, and no unfilled `{VARIABLE}` tokens in any of its prompt tier blocks. Flag incomplete cards as WARN (they should be in draft status; a production card with empties is FAIL).
4. **ACTUAL char count vs declared:** For every card with a declared character-count annotation line, recount the actual characters in each prompt tier block and compare to the declaration. A discrepancy of more than 5 characters is a FAIL. Seedream tier: any tier over 2,800 characters is WARN; any tier over 3,000 characters (silent fail zone) is FAIL.
5. **6xx SOP version pins:** For every SOP file in `sops/` that begins with a `Library-version pin:` line, compare the pinned version to the current file version header of the referenced library file. Any mismatch is FAIL -- flag LOUDLY: "SOP-DIU-[NNN] version pin STALE: pinned [version], current [version]. Re-pin required before this SOP can be trusted."
6. **Quarantine folder empty or escalated:** If `_local/quarantine/` contains any asset files, verify that each has a corresponding incident.json with a CDO-notified timestamp and a non-null `resolution` field. Any quarantined asset without a logged incident or without a resolution is FAIL.
7. **Embedding coverage:** Count cards with status "production" or "tested" in INDEX.md. Count embedding entries in the index manifest. If they differ (coverage != card count), flag as WARN and trigger a rebuild notification to the Style Analyst: "Embedding coverage [actual] != card count [expected]. SOP-DIU-606 rebuild required."
8. **Receipt age -- stuck jobs:** List all receipt files in `_local/receipts/` with state `submitted` or `polling`. Any receipt with `last_polled` older than 24 hours is FAIL -- flag with receipt_id and last_polled timestamp for CDO attention. This is a stuck-job check: Healer gets ground truth without touching the image API.
9. **MODEL-SPECS staleness:** Read the MODEL-SPECS.md header date. If more than 90 days old, flag as FAIL: "MODEL-SPECS.md header date is [date] -- over 90 days. CDO should trigger a Healer model-currency census (SOP 9.6)."
10. **Kie.ai key/endpoint reachability:** Verify `KIE_API_KEY` is present in at least one env store (check all stores per the client-box-env-stores policy). Verify the Kie.ai primary endpoint is reachable (HEAD request or lightweight GET). Report FAIL if the key is missing from all stores or the endpoint returns a non-2xx response.
11. **Registrar activation counter:** Count the total production + tested card rows in INDEX.md. If count >= 50, flag: "Registrar activation threshold reached ([N] production+tested cards). CDO should activate the Library Registrar role per SOP-DIU-606 step 9."

**Reporting:**
- If ALL checks pass and nothing changed since the last sweep: output NOTHING. Suppress the "all clear" message (heartbeat-suppression policy -- one silent pass costs no tokens, one "all clear" per sweep creates a session log entry every scheduled fire).
- If ANY check returns WARN or FAIL: emit a concise report via `openclaw message send` to the CDO listing only the changed/new findings, the check name, severity, and the exact file/path implicated.

**Outputs:** Findings report (on changes/failures only); no output on a clean sweep.
**Hand to:** CDO (findings report); Style Analyst (embedding rebuild trigger if coverage check fails); Generation Operator (stuck-job alert); no handoff on a clean sweep.
**Failure mode:** If the Healer cannot read any of the required files (permissions, disk error), emit a single FAIL report: "SOP-DIU-615 sweep aborted -- cannot read [path]. No sweep completed. CDO action required." Never claim a clean sweep if the sweep could not complete.

---

*SOPs owned: healer-base SOPs 9.1-9.12 (no SOP-DIU tag -- base healer suite); [SOP-DIU-615] at SOP 9.13. sop_count: 13 total (12 base + 1 ZHC DIU integrity sweep).*
