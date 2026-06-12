# SOPs Mirror -- The Healer -- Presentations

**Source:** presentations/healer-presentations.md
**Extract:** Section 9 (Standard Operating Procedures) verbatim mirror.
**Authority:** This file mirrors the role file. The role file is authoritative. If they diverge, the role file wins and this mirror must be regenerated.

---

## 9. Standard Operating Procedures (Numbered)

Master authority: universal-sops/CLIENT-WEBINAR-DECK-SOP.md

### SOP 9.1 -- Incident Intake and Triage

**When to run:** On every error flag, watchdog handoff, QC loop-4 escalation, failCode event, or operator bug report.

**Steps:** 1. Open an incident in working/healer/incident_ledger.json: id, detected_at, source (watchdog/QC/specialist/operator), symptom (verbatim error text and the file/phase), affected run, severity (P0 run-dead, P1 degraded, P2 cosmetic/latent). 2. Stabilize first: if a live run is bleeding (burning credits, looping), pause the affected phase via checkpoint flag before diagnosing. 3. Classify the suspected layer: code/script, SOP instruction, model behavior, external API, environment (keys, disk, RAM), or GAP (no SOP covers this situation). 4. Route: layers code/SOP/environment proceed to SOP 9.2; GAP routes to SOP 9.5; suspected stale model routes to SOP 9.6 (targeted check, not full census).

**Outputs:** incident record, stabilized run. **Hand to:** SOP 9.2. **Failure mode:** if the ledger itself cannot be written, message the Director immediately and work from a temp file; never heal without a record.

---

### SOP 9.2 -- Root-Cause Diagnosis (Five Whys on Evidence)

**When to run:** On every triaged incident.

**Steps:** 1. Gather evidence: the exact failing request/response, checkpoint states, the SOP text the failing agent followed, the QC reports. 2. Reproduce when safe (one cheap call, one dry-run step); never reproduce destructive failures on a client's live assets. 3. Run five whys until the answer names a SPECIFIC defect in a SPECIFIC layer ("the SOP told the poller to look for 'complete'" is a root cause; "the poller was confused" is not). 4. When the outside world is involved (API contract, model behavior change), dispatch ROLE-04 Deep Research Specialist for the provider's current documentation; diagnosis on evidence, never on memory. 5. Write root_cause, evidence list, and layer to the incident record.

**Outputs:** incident updated with root cause. **Hand to:** SOP 9.3. **Failure mode:** unreproducible after honest effort: instrument the pipeline (Tier 2: add logging to the relevant SOP step), close as UNREPRODUCED-WATCHING, auto-reopen on next occurrence.

---

### SOP 9.3 -- Fix Forward and Hot Patch (Tier 1)

**When to run:** Once root cause is known and the fix is Tier 1 (mechanical, non-doctrine).

**Steps:** 1. Design the minimal fix that kills the root cause (minimal-diff rule). 2. Apply to the live run: patch the script/config/checkpoint, resume from the last good checkpoint, never restart from scratch. 3. Verify the fix with the actual failing case (the request that failed must now succeed). 4. Compute and log salvage value when relevant (images recovered, credits saved). 5. Update the incident: fix_applied, verified_at. 6. If the fix changed ANY behavior an SOP describes, SOP 9.4 is now MANDATORY before the incident may close.

**Outputs:** healed run, incident updated. **Hand to:** SOP 9.4. **Failure mode:** fix fails verification twice: escalate to the Director with the evidence package; do not thrash.

---

### SOP 9.4 -- SOP Surgery (Tier 2: the permanent repair)

**When to run:** After any fix that revealed an SOP defect, and on any pattern-scan hit.

**Steps:** 1. Locate every SOP and role file that carries the defective instruction (grep the whole department; the same wrong text often lives in role + sops/ mirror + 00-START-HERE). 2. Write the minimal patch: correct the instruction, add the verification step that would have caught it, update the failure mode. 3. Version-bump the SOP (v1.0 to v1.1) with a dated changelog line naming the incident id. 4. Regenerate the sops/ mirror so role and mirror stay verbatim-identical; update 00-START-HERE.md if counts/claims changed. 5. Add a regression entry to working/healer/regression_suite.md: a mechanical, re-runnable check that fails if the bug ever returns. 6. Commit with message `heal(<incident-id>): <one-line root cause> -> <one-line patch>`. 7. DOCTRINE BOUNDARY: if the needed patch touches the master SOP, the Pitch Doctrine, pricing choreography, brand rules, or the MODEL MANIFEST, STOP: package it as a Tier 3 proposal (SOP 9.7 carries it) and hold.

**Outputs:** patched SOPs, regression entry, commit. **Hand to:** SOP 9.7 (report), SOP 9.8 (watch). **Failure mode:** patch conflicts with the master SOP: the master wins; escalate the contradiction as Tier 3.

---

### SOP 9.5 -- Gap Detection and New-SOP / New-Specialist Drafting

**When to run:** When triage classifies an incident as GAP, when a specialist improvised because no SOP covered the task, or when the Director flags an unowned function.

**Steps:** 1. Define the gap precisely: what task occurred, who improvised, what went wrong or almost did. 2. Decide the container: does this belong inside an EXISTING role (new numbered SOP) or is it an unowned FUNCTION (new specialist)? Default to extending existing roles; specialists multiply only when a function has distinct ownership, KPIs, and handoffs. 3. For a new SOP: draft on the standard template (When to run / Inputs / Steps / Outputs / Hand to / Failure mode), grounded in the master SOP and research evidence; this is Tier 2: apply, version, notify. 4. For a new SPECIALIST: draft the full 19-section role file + SOP suite; this is Tier 3: propose and hold. 5. Either way, add the gap and its resolution to the ledger so the Chief Healer can check other departments for the same hole.

**Outputs:** new SOP (applied) or new-role proposal (held). **Hand to:** Director + operator via SOP 9.7. **Failure mode:** gap is ambiguous: dispatch ROLE-04 for research, observe one more run with instrumentation, then decide; never draft from confusion.

---

### SOP 9.6 -- Model Currency Census

**When to run:** Monthly (department-wide), and targeted on any incident where model behavior is the suspected layer.

**Steps:** 1. Build the model inventory from the department's routing table and MODEL MANIFEST: every text model, QC model, image model/platform, with the version currently pinned. Presentations department inventory includes: GPT Image 2 (image generation, Kie.ai), Minimax m3:cloud (QC scoring model), DeepSeek v4 Pro/Flash (text/director models), and any fallbacks named in the manifests. 2. Dispatch ROLE-04 Deep Research Specialist per model: latest available version on the department's actual providers (Kie.ai docs, Ollama Cloud catalog, OpenRouter model list), release notes, pricing deltas (always expressed per million tokens), deprecation notices, breaking changes. 3. For each model produce a verdict: CURRENT (pinned = latest), STALE (newer exists), DEPRECATED (shutoff announced: flag URGENT with the date). 4. For every STALE/DEPRECATED entry, write a Tier 3 upgrade proposal: the case (what improves), the cost delta, the risk, the staged rollout plan (smoke test on one low-stakes run before fleet-wide), and the rollback line (the exact manifest revert). 5. NEVER change a manifest or swap a model yourself, and NEVER mid-run. Proposals go to the operator via SOP 9.7 and wait for written approval. 6. Record the census date per model; the freshness KPI reads from here.

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

**Outputs:** patched core file, backup, boot validation. **Hand to:** SOP 9.12 (embedding refresh), SOP 9.7 (report). **Failure mode:** agent fails to boot on the patch: restore the backup immediately, reopen diagnosis.

---

### SOP 9.10 -- Settings and JSON Structure Repair

**When to run:** When the root cause is a configuration setting (openclaw.json settings, gateway config, env wiring) or a broken JSON structure anywhere (checkpoints, manifests, config files, malformed escapes).

**Steps:** 1. Back up the file. 2. Validate the CURRENT state mechanically first (python json.load or jq) and capture the exact parse error and position. 3. Repair the minimal defect: the missing comma, the unescaped quote, the wrong setting value, the stale model string; never regenerate a whole config to fix one key. 4. Re-validate mechanically: the file must parse clean. 5. If the setting affects a running gateway/agent: apply per the repo's documented restart procedure, then run one smoke turn to confirm the system is live. 6. Record in the ledger which setting changed, old value, new value, and why. Settings that change model routing or anything in a MODEL MANIFEST remain Tier 3.

**Outputs:** valid config, smoke-test pass, ledger entry. **Hand to:** SOP 9.7. **Failure mode:** repair does not parse after two attempts: restore backup, escalate to the Chief Healer with the captured parse errors.

---

### SOP 9.11 -- Teacher-Self Protocol (turn every heal into a lesson)

**When to run:** When a heal contains a lesson the wider fleet should internalize as knowledge, not just encounter as a patched SOP (a misunderstood API contract, a recurring formatting trap, a model quirk).

**Steps:** 1. Decide if a teaching is warranted: would another agent, in another department, plausibly hit this? If yes, teach. 2. Locate the repo's teachers location and follow its existing teacher-self protocol and document format exactly (discover, do not invent a parallel format). 3. Write the teaching doc LEAN: the trap, the tell (how you recognize it), the correct move, one concrete example, the incident id. One page maximum. 4. Register the teaching per the protocol (index, naming convention) so agents actually load it. 5. Cross-link: incident ledger entry points to the teaching; the teaching points back. 6. Hand the teaching to the Bugs Department's Bug Librarian for the knowledge base.

**NOTE -- Bug Ticket Filing:** the Bug Ticket schema lives in the ZHC Bugs Department (PART 2.2 of THE_HEALER_AND_BUGS_DEPARTMENT.md). That department is not yet built. **TODO: wire this SOP's teaching handoff step to the Bugs Department's Bug Librarian once the Bugs Department is commissioned and merged.** Until then, write teachings to working/healer/teachings/ and cross-link from the incident ledger.

**Outputs:** teaching doc, registrations, cross-links. **Hand to:** SOP 9.12. **Failure mode:** no teachers structure exists in this deployment: flag to the Chief Healer as a gap (SOP 9.5 territory) rather than inventing an unsanctioned folder.

---

### SOP 9.12 -- Embedding and Retrieval Index Refresh (the system must remember the fix, not the bug)

**When to run:** After ANY change to markdown, SOPs, core files, or teachings in a deployment that uses embeddings/retrieval over its docs.

**Why this SOP exists:** A patched document with a stale embedding means the system keeps RETRIEVING the buggy version. The knowledge layer must reflect every heal immediately or the company keeps remembering its own diseases.

**Steps:** 1. Identify every file changed by this heal (from the incident ledger). 2. Run the repo's documented embedding/index refresh for exactly those files (discover the existing pipeline; never build a second one). 3. Verify: run one retrieval query that previously surfaced the old content and confirm the NEW content returns. 4. Record refresh time and verification result in the ledger. 5. If no embedding pipeline exists for this deployment, note "n/a, no retrieval layer" once in the ledger and skip in future heals for this client.

**Outputs:** refreshed index, verified retrieval, ledger entry. **Hand to:** SOP 9.7 (the heal may now close). **Failure mode:** retrieval still returns stale content after refresh: treat as its own P1 bug ticket against the embedding pipeline.

---
