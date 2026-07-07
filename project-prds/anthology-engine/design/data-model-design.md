# Anthology Engine, Data Model Design Spec v3.0 (revision 3: aligned to PRD.md, SPEC.md, and WAVE-PLAN.md revision 3 of 2026-07-06; Command Center department/board terminology binding; explicit Drive tree; explicit field-push list; assembly staging collection)

Status: DESIGN COMPLETE, READY FOR /goal EXECUTION. Defines the durable state layer the whole engine stands on. SPEC.md Section 7 compiles this design into buildable schema; where this document and the PRD or SPEC could ever be read to disagree, the PRD governs, then the SPEC, and this design gets fixed. Grounding: the operator's ratified keying decisions, the verified legacy-estate audit (SPEC Section 1), and the Command Center repo ground truth (PRD Sections 3.15 to 3.17).

TERMINOLOGY BINDING (revision 3, normative): there is NO standalone dashboard app and NO producer role in any Command Center code. Wherever this document says "board" it means the Anthology DEPARTMENT BOARD inside the client's own Command Center (seeded via Skill 32's add-department.sh, equivalently POST /api/departments with create:true), whose review column is the chapter-approval queue and whose dedicated Assembly card carries the ready-to-assemble trigger and the final sign-off; participant-facing gate actions arrive through the NEW token-scoped public route (SPEC Section 11.3). Older revisions of this document said "dashboard" for the same surface; the Approvals door value named dashboard (Section 2, Approvals) MEANS this board surface, per the SPEC's own terminology binding.

Doctrine: move in silence; no Anthropic in any runtime file; credentials by label and location only (the Airtable credential under its existing label and the base id under ANTHOLOGY_STATE_BASE_ID in the client env stores; values never printed); Convert and Flow naming in every surface; config writes as the node user; only sub-agents build; zero client personally identifiable information in this document or the repo.

---

## 1. What exists today, and what is explicitly rejected

The legacy prompt base (label LEGACY-PROMPT-BASE) is a flat, name-keyed PROMPT library: five tables with identical columns, duplicated tone and avatar copies, and eight full-book records truncated at the platform's 32,767-character ceiling, ALL eight belonging to the twelve-chapter full-book product that is out of anthology scope by ratified decision. The second legacy base (label LEGACY-SYSTEMS-BASE) is the state store of OTHER product families. Verified verdict (SPEC Section 1.2): the anthology pipeline holds ZERO durable state in Airtable today; its only state lives in suspended n8n executions and Convert and Flow opportunity stage positions, meaning state dies with the execution. That fragility is exactly what this ledger replaces.

REJECTED FOREVER: prompts in the ledger base at runtime (prompts are baked into the skill, sha256-pinned, guard-prompt-pins.py proven; the legacy bases survive only as the operator's private editing workspace, with zero runtime references enforced by static scan at merge); name-keyed lookups by formula; any record-level state that requires a live execution to interpret; email as a key of any kind; per-anthology custom-field families on the contact (SPEC Section 7.5); any second state store recomputed beside the ledger (board rollups are projections, never stores).

## 2. The new base: Anthology Engine State (one base per deployment, plus a local mirror)

A NEW, purpose-built base is the durable system of record for orchestration state, created by provision-anthology-client.sh through the ledger writer's schema bootstrap and written ONLY through anthology_state.py (the sole writer, enforcing the legal-transition matrix of Section 4). A local SQLite mirror on the client box (WAL mode, under the engine's state directory, owned by the node user) is the fast read path for the board rollups, the intake router, and the crash-recovery cache; it carries the same tables and columns plus a meta table (schema_version, last_reconcile_at, base_cursor). anthology_state.py writes through to both stores in one operation and reconciles on the daily tick; the base is authoritative on conflict. The mirror means a network blip never blocks a gate action; the base means a dead box never loses a participant.

### Table: Producers
producer_id (primary), producer_email (the OpenClaw BOX OWNER, the client who completed the AI Workforce Interview, passed via the Convert and Flow webhook payload; there is no separate producer identity system), display_name, drive_root_folder_id (the producer's folder under the delivery root, Section 6), status (active, revoked), created_at. One producer runs many anthologies.

### Table: Anthologies
anthology_id (primary), producer_id (link), name, theme, status (setup, open, writing, ready_to_assemble, assembling, delivered, archived), caf_location_binding (label reference, never a secret), caf_pipeline_binding (the AUTO-PROVISIONED standard Convert and Flow pipeline per PRD Section 3.12, bound at provisioning through the client's own private integration token; pre-existing-pipeline binding is an explicit override, never the default), caf_stage_map (json; drives the per-gate pipeline-stage update, nothing hardcoded), form_ids (json), drive_folder_id (the anthology folder, Section 6), chapter_order (json array of participant_keys, the S9 curation of record), assembly_state (not_ready, armed, ready_confirmed, proposed, adjusted, compiled, signed_off), min_chapters (the ready-trigger floor, default 2, per-anthology configurable up), assembly_ready_at (stamped by the s9_ready approvals row), created_at, updated_at.

### Table: Participants
participant_key (primary, the LITERAL composite contact_id::anthology_id), contact_id, anthology_id (link), first_name, last_name, email, phone, ideal_avatar (Q1), niche (Q2), primary_goal (Q3), stage_cursor (exact vocabulary: s0_intake, s1_avatar, s1_gate, s2_tone, s2_gate, s3_title, s3_gate, s4_blurb_outline, s4_gate_producer, s4_gate_participant, s5_chapter, s5_gate, s6_rewrite, s7_cover, s8_deliver, s9_wait_assembly, approved, delivered, held, exception), rewrite_count (0 to 2), qc_attempts_current (0 to 3), tone_inputs (json: describe_tone plus the four influences), chapter_about, personal_stories (json), title_locked, subtitle_locked (byte-exact, stamped at the S3 gate, one-way), chapter_updates (append-only json of rewrite notes, fed verbatim from s5_participant gate notes), hold_reason, stage_timestamps (json), drive_folder_id (the participant folder id; required by the SPEC Section 10.1 folder-id caching law and completed here since the SPEC 7.1 table omits the column; W1.7's schema bootstrap ships it), created_at, updated_at.

THE KEYING LAW (PRD decision 3.5, binding everywhere): everything keys off contact_id, NEVER email. Every form carries hidden contact_id, anthology_id, and stage. The same person in two anthologies is TWO participant rows sharing one contact_id, separated by anthology_id. No opportunity list-then-filter exists anywhere (the legacy getAll-limit-1 race is retired). Unroutable submissions land in Exceptions, never silently dropped, never guessed.

### Table: Artifacts
artifact_id (primary), participant_key (link; or anthology scope for manuscript artifacts), type (avatar, tone, titles, blurb, outline, chapter, rewrite, cover, anthology_manuscript), version, drive_doc_id, doc_url, pdf_url, caf_media_url, custom_field_keys_written (json), sha256, prompt_pin_sha256, model_used (honest, never an Anthropic id, by deny pattern), frozen (checkbox), created_at. Every deliverable version is a row; the current version is the highest per type; APPROVAL FREEZES THE ROW (frozen true); S9 consumes ONLY frozen chapter rows, byte-identical by sha256 (Section 7).

### Table: Approvals (append-only)
approval_id (primary), subject_key (participant_key or anthology_id), gate (s1_producer, s2_producer, s3_selection, s4_producer, s4_participant, s5_participant, s9_ready, s9_producer), actor (producer, participant), decision (approve, request_rewrite, escalate, hold, exclude, ready_to_assemble), notes (feeds chapter_updates verbatim when the gate is s5_participant), door (dashboard, nudge_link; the value dashboard MEANS the Command Center board surface per the terminology binding, and SPEC Section 11.2's "door recorded as board" is this same value; nudge_link covers the emailed deep link into the participant token page or the producer readiness nudge), decided_at. The s9_ready row (decision ready_to_assemble, actor producer) IS the producer "I'm ready to assemble" trigger of record (PRD Section 3.11); exclude rows (actor producer, subject a participant_key) record edition exclusions. Append-only: this is the audit trail multi-contributor publishing requires, and the board never holds it, only reads it.

### Table: Exceptions
exception_id (primary), raw_submission (json, the payload preserved), reason (unroutable_missing_ids, unknown_anthology, stage_mismatch, tenant_mismatch, legacy_reconciliation), status (open, resolved), resolved_by, resolved_participant_key, created_at, resolved_at. Resolution replays the submission through S0; the legacy_reconciliation reason is the ONLY sanctioned legacy-migration entry point (PRD Section 18, manual and operator-initiated, no bridge tooling).

## 3. Writer contract

anthology_state.py subcommands: upsert-participant, advance-stage, record-artifact, record-approval (including the s9_ready trigger with --confirm-name), assembly-readiness-report (read-only: emits the blocking list that arms or refuses the trigger), hold, resume, exception-open, exception-resolve, assembly-set-order, reconcile-mirror, export-bundle. Every subcommand takes explicit keys (participant_key or anthology_id), validates against the legal matrix of Section 4, writes base plus mirror in one operation, and exits 0 only on verified success. Exit codes (SPEC Section 3.4, row 1): 0 verified success; 2 illegal transition; 3 unknown key; 4 base unreachable (mirror-queued write); 5 validation or confirm-name mismatch. Illegal transitions exit nonzero and change NOTHING.

NO other code path writes to either store: the board's gate actions, the participant token page, the stage runners, the exceptions replay, and the revocation script all shell through the writer; Layer 4 holds no base credential at all (SPEC Section 2.3). This is enforcement, not description: a static route audit and a repo scan for direct base writes ride Gate A.

## 4. The legal transition matrix (enforced by the writer, never by UI alone)

    s0_intake -> s1_avatar                     on valid universal submission
    s1_avatar -> s1_gate                       on avatar artifacts recorded
    s1_gate -> s2_tone                         on approvals row (s1_producer, approve)
    s2_tone -> s2_gate -> s3_title             tone prover pass, then producer approve
    s3_title -> s3_gate -> s4_blurb_outline    titles delivered, then selection recorded
                                               (TITLE LOCK stamps here, one-way)
    s4_blurb_outline -> s4_gate_producer -> s4_gate_participant -> s5_chapter
    s5_chapter -> s5_gate                      only after Tier 1 plus rubric pass
    s5_gate -> s7_cover                        on approve (chapter artifact FREEZES)
    s5_gate -> s6_rewrite                      on request_rewrite AND rewrite_count < 2
    s6_rewrite -> s5_gate                      always re-enters the gate
    s7_cover -> s8_deliver -> s9_wait_assembly -> approved
    approved -> delivered                      at S9 manuscript delivery of the anthology
    ANY -> held                                typed hold (credit_out, callback_lost,
                                               strike_out); resume ONLY to the recorded cursor
    ANY -> exception                           router-detected; resolution replays S0

Anthology scope (the S9 bracket, PRD Section 3.11):

    not_ready -> armed                 when every participant is approved or carries an
                                       explicit exclude approvals row
    armed -> ready_confirmed           ONLY on the s9_ready approvals row (the producer
                                       trigger), with ALL guards revalidated by the writer:
                                       own-producer auth (the box owner's Command Center
                                       session or a producer-scoped token); every participant
                                       approved or explicitly excluded; at least min_chapters
                                       frozen approved chapters (floor 2); typed anthology-name
                                       confirmation echoed as --confirm-name (mismatch exits 5)
    ready_confirmed -> proposed -> adjusted* -> compiled -> signed_off
                                       signed_off requires an s9_producer approvals row

The s9_ready trigger is ONE-WAY: re-firing is an acknowledged no-op; reopening collection after ready_confirmed is a producer-initiated exception that resets assembly_state to not_ready and voids in-progress assembly. A silent third rewrite, an S9 compile before ready_confirmed, and a resume to any cursor other than the recorded one are all illegal transitions the writer refuses.

## 5. Convert and Flow custom-field push contract (the Doc plus PDF pairs)

The ledger is the source of truth; the contact's standardized custom fields are a PUSHED PROJECTION of the ACTIVE anthology's artifact rows, written by EXACT key, keyed by contact_id (never email), and read back byte-for-byte after every write (caf_delivery.py, exit 5 on read-back mismatch). At runtime the keys are spelled in exactly ONE place, config/field-map.json; the normative list is PRD Section 6, reproduced here because this projection is a data-model contract:

| Deliverable | Doc link field | PDF link field |
|---|---|---|
| Avatar | contact.anthology_avatar_doc_url | contact.anthology_avatar_pdf_url |
| Tone | contact.anthology_tone_doc_url | contact.anthology_tone_pdf_url |
| Titles | contact.anthology_titles_doc_url | contact.anthology_titles_pdf_url |
| Blurb | contact.anthology_blurb_doc_url | contact.anthology_blurb_pdf_url |
| Outline | contact.anthology_outline_doc_url | contact.anthology_outline_pdf_url |
| Chapter | contact.anthology_chapter_doc_url | contact.anthology_chapter_pdf_url |
| Cover | contact.anthology_cover_image_url | contact.anthology_cover_drive_url |
| Manuscript | contact.anthology_manuscript_doc_url | contact.anthology_manuscript_pdf_url |

Control fields: contact.anthology_active_id, contact.anthology_stage, contact.anthology_rewrite_count. MULTI-ANTHOLOGY CONTACTS: the fields carry the ACTIVE anthology's links, disambiguated by contact.anthology_active_id; history lives here in the ledger and in Drive, never in field archaeology. Provisioning creates or verifies every field per client at setup; missing fields STOP SETUP with an operator surface, never a silent runtime create. The per-gate Convert and Flow pipeline-stage update rides the registry's caf_stage_map (Anthologies row), fired at every gate, nothing hardcoded.

## 6. The Drive tree (delivery-plane state cached on the ledger)

The delivery-tree ROOT is the operator's EXISTING anyone-can-read folder, wired as the root of record (PRD Section 3.7: https://drive.google.com/drive/folders/1gVdZ3_cx7Sv7VAfARL_LsGh5IcVB6iZw; config key drive_root_folder in engine-config.template.json). The tree below it: Root, then Producer display name, then Anthology name, then Participant name. drive-tree-provision.py provisions it IDEMPOTENTLY at S0 (get-or-create, one code path, replacing the legacy sixteen-node folder plumbing), verifies root reachability at preflight, and NEVER creates a new root (exit 2 when the configured root is unreachable). Access is the operator's EXISTING service account by label (GOOGLE_IMPERSONATE_USER, full Drive scope, the clawd/google-api.js pattern); NOTHING new is provisioned in Google.

Ledger caching of the tree: Producers.drive_root_folder_id (the producer folder), Anthologies.drive_folder_id (the anthology folder), Participants.drive_folder_id (the participant folder, Section 2 completion note), and Artifacts.drive_doc_id per document. Every Doc is created inside the participant folder; the S9 manuscript lands at anthology scope; per-document sharing is anyone-with-link VIEW only (revocation-preserving: revoke-anthology-client.sh revokes shares and regenerates view links). The per-anthology export bundle (ledger rows as json plus the Drive folder) is produced by the writer's export-bundle subcommand or the revocation script.

## 7. Assembly staging: the all-approved-chapters collection

S9 never gathers content ad hoc; it compiles from a STAGED COLLECTION defined entirely by ledger state:

1. MEMBERSHIP: one chapter per participant whose stage_cursor is approved (or beyond) and who does NOT carry an exclude approvals row. Excluded participants are recorded, never deleted.
2. THE ARTIFACT SET: for each member, the single Artifacts row with type chapter, frozen true, highest version. Freezing happens at the s5_gate approve transition and is what makes the collection stable across the weeks or months between the last approval and the producer's trigger.
3. ARMING: when every participant is approved or explicitly excluded, the writer arms the trigger (assembly_state not_ready to armed) and the approvals steward fires ONE readiness nudge. assembly-readiness-report emits the blocking list (unapproved participants, missing frozen chapters, count below min_chapters) that the Assembly card and the nudge render.
4. THE TRIGGER: the producer fires s9_ready from either door (the Assembly card on the Anthology board, or the readiness nudge deep link; both doors, ONE endpoint, both shelling record-approval --gate s9_ready). All Section 4 guards revalidate inside the writer at fire time, never trusted from the UI.
5. STAGING CHECK AT COMPILE: the compile step re-reads every member row and verifies each frozen chapter byte-identical by sha256 against its artifact before inclusion; any mismatch aborts compilation with exit 5 and changes nothing. chapter_order (Anthologies row, written only via assembly-set-order) is the order of record: the ae-01 curation proposal writes it with rationale, the producer adjusts it on the Assembly card (assembly_state proposed to adjusted), and assembly-scope Gate B proves every approved chapter present exactly once in exactly that order.
6. CLOSE-OUT: the compiled manuscript is a NEW Artifacts row (type anthology_manuscript, anthology scope); producer sign-off is the s9_producer approvals row (assembly_state signed_off; anthology status delivered); member participants transition approved to delivered; manuscript fields push per Section 5.

## 8. Board and token-page read/write contract (Layer 4 against this model)

The Anthology department board is FED from this ledger, never a second store: one card per participant, status mirroring stage_cursor, ingested via mc_board.py to POST /api/tasks/ingest (HMAC plus Bearer, FAIL-SOFT: board unreachability never blocks the pipeline; the ledger remains the truth and cards reconcile on the daily tick). Producer-facing deliverables land the card in the REVIEW column (the chapter-approval queue); ONLY the independent QC scorer at or above 8.5 promotes review to done; the engine never self-promotes. Rollups (active participants, chapters pending approval, stuck items) are projections of the same ledger. Gate actions from the board and from the participant token page (token/PIN minted by gate_engine.py over participant_key, gate id, and expiry, under ANTHOLOGY_GATE_TOKEN_SECRET) write ONLY by shelling anthology_state.py; foreign, expired, or replayed tokens are refused before any writer call.

## 9. Retention, export, privacy

Participant personally identifiable data lives in this ledger and the client's own Convert and Flow account only; every client-visible payload passes the client-clean serializer; no secrets, prompts, or model internals are ever stored in the base (model_used is an honest model id, never a key or an Anthropic id). Client data-export path: the per-anthology export bundle of Section 6. Churned client (revoke-anthology-client.sh): gate tokens invalidated, board cards archived, Drive shares revoked, webhook route disabled, export produced, ledger rows archived, and ZERO recurring jobs left behind (guard-cron-inventory.py proven).

## 10. Build acceptance and traceability

Acceptance drills (CHECKLIST.md Part C items 6 and 7; executed at Wave 5): (1) base and mirror created by the provisioning script's schema bootstrap; (2) kill-and-resume drill: kill the process mid-stage, replay the event, nothing lost, no duplicate artifact (W5.5); (3) illegal-transition drill refused with exit 2 and zero change (W5.5); (4) two-anthology drill: one test contact in two anthologies, two clean rows sharing one contact_id (W5.6); (5) mirror-divergence drill: mutate the mirror, the daily reconcile restores base truth (W5.5); (6) static scan proves zero runtime references to either legacy base and zero write paths outside the writer; (7) the S9 trigger drill: every guard forced from BOTH doors (non-producer refused, blocking list shown, below-minimum refused, confirm-name mismatch refused, double-fire no-op), one explicit exclusion, staged compile byte-identical (W5.7); (8) field-push drill: every Section 5 field written by exact key and read back byte-for-byte, control fields current (W5.4).

Wave traceability: the writer, matrix, and schemas are W1.7; exceptions mechanics W1.19; the hold queue W1.20; the field push W1.13; the Drive tree W1.11; the assembly staging machinery W1.18; the board contract against this schema is Wave 3 (starts only when W1.7's schema is settled). Incremental persistence law applies: each unit, once QC'd at or above 8.5 and pushed, ticks CHECKLIST.md and TODO.md and appends SESSION-LOG.md and CHANGE-LOG.md before the agent moves on.
