# Anthology Engine -- MASTERDOC (the SACRED floors, rule to code)

The single human-readable index tying every SACRED rule (mirrored from PRD Section
3) to the fail-closed gate that enforces it. Enforcement, not description: if a
rule is here, a prover or guard measures it; a model's self-report is never
trusted. Where this doc and the PRD could ever be read to disagree, the PRD
governs and this doc gets fixed.

## The unit of work

ONE participant, ONE chapter. An anthology is many participants; the engine
authors and certifies each chapter independently through Skill 54, so participants
run in parallel and one blocked chapter never strands the others. The producer is
the OpenClaw box owner; there is NO producer role in any Command Center code.

## The SACRED floors (never floored, reordered, renamed, or reinterpreted)

1. ONE CHAPTER PER PARTICIPANT, never twelve. The twelve-chapter full-book prompts
   are Skill 53 territory and permanently out of anthology scope.
2. CHAPTER BAND: 2,000 to 3,500 MEASURED stripped words. The self-report is
   ignored; padding is inert. The Write Chapter word-count contradiction is
   NORMALIZED to this band everywhere. Enforced by `prove_aw_chapter.py` (Skill 54).
3. TONE FLOOR: the blended tone doc is EXACTLY four influence analyses and at least
   3,000 MEASURED stripped words. Enforced by `prove_aw_tone.py` and the shared
   tone core, reused BYTE-IDENTICAL (`verify_tone_core_sync.py`); forking it is a
   build failure.
4. TITLE LOCK: the participant's chosen title and subtitle become byte-exact
   invariants carried into the outline, the chapter, every rewrite, and the cover
   prompt; the lock is one-way. Enforced by `prove_aw_chapter.py` (AF-AW-TITLE-LOCK).
5. STORY PLACEMENT: every non-N/A personal-story anchor is provably placed in the
   outline AND the chapter. Enforced by the story-placement prover.
6. REWRITE BUDGET: at most two rewrites per participant, each re-entering the S5
   gate; a silent third rewrite is an illegal transition. Enforced by
   `qc-strike-gate.py`. Three internal QC attempts per deliverable, then HOLD plus
   one deduped founder alert; standards never relaxed.
7. FONT FLOOR: every deliverable ships as BOTH a Google Doc and a designed PDF with
   NO rendered glyph below 14 point. Enforced by `guard-font-floor.py` over the
   RENDERED file, never the template.
8. KEYING: everything keys off contact_id, never email. One human in two
   anthologies is two participant rows sharing one contact_id, separated by
   anthology_id. Unroutable submissions land in the exceptions queue with the raw
   payload and a typed reason, never dropped or guessed.
9. NON-ANTHROPIC CLIENT SOVEREIGNTY: every resolved model id is the client's OWN
   strongest NON-Anthropic model, from the client's own keys, never the operator's.
   No Anthropic-family id, no operator key, no key taken through intake. Enforced by
   `model_router.py` deny patterns and `guard-no-anthropic-runtime.py`.
10. PER-CLIENT DELIVERY ROOT (BlackCEO hosts one Shared Drive per client). Google
    delivery uses the BlackCEO-owned service account (label `GOOGLE_SA_KEY_FILE`)
    impersonating the BlackCEO Workspace user (`GOOGLE_IMPERSONATE_USER`), and lands
    every deliverable under a PER-CLIENT delivery root: BlackCEO provisions ONE Google
    Shared Drive per client inside BlackCEO's own Workspace, and each client box points
    at its OWN Shared-Drive root, resolved per box from `GOOGLE_DRIVE_ROOT_FOLDER` (never
    one shared operator root, so no client's tree ever co-mingles with another's).
    BlackCEO provisions the per-client Shared Drive out of band; the engine VERIFIES the
    supplied root and NEVER creates a NEW Drive root. Per-document sharing is EDIT on the
    co-author's OWN Doc (friction-free pull-back) and VIEW on PDFs/images; the root itself
    is never anyone-can-read. Enforced by `caf_credential_gate.py` (the delivery-credential
    presence gate), `drive_adapter.load_root_folder_id` (resolves the per-box root and
    refuses an unresolved template slot), and `drive-tree-provision.py` verify_root (never
    creates a root).

    FLEET UPDATE -- the n8n CREDENTIAL BROKER (client boxes hold NO Google key). The
    fleet Drive model is now the n8n credential broker: Trevor's Google service-account
    key lives ONLY inside n8n (his n8n VPS). A client box holds NO Google key -- only the
    broker webhook URL plus a low-privilege shared token (`N8N_DRIVE_WEBHOOK_TOKEN`). The
    PRIVILEGED per-book folder-tree creation + producer editor share are POSTed to n8n
    (action `create_book_tree`) via `drive_adapter.provision_book_tree`, which uses the
    folder ids n8n returns; a compromised client box cannot leak Google creds because they
    were never there. The U19 SA-key-on-box path (SA key + impersonate user + per-client
    root) remains ONLY for the operator's OWN box, which legitimately holds the SA key.
    Selection is per box: broker if configured (`drive_adapter.broker_configured`), else
    local SA. `caf_credential_gate.py` enforces EITHER the broker pair OR the SA trio per
    box (a half-configured broker, or a mode missing its levers, STOPS provisioning, exit
    2). The per-Doc broker actions (`create_doc`, `upload_pdf`, `share_doc_edit`,
    `pull_doc_text`) AND the per-participant runtime tree (`create_participant_tree`) are
    IMPLEMENTED in the n8n route template, so the WHOLE S0..S8 Drive path (S0 first-sight
    tree, S7 cover upload, S8 Doc create/share, confirm-then-pull read-back) runs on a
    pure client box through the broker -- the local SA is never touched there. Selection
    is per box: `deliver_doc` / `deliver_media` / `do_share` / `pull_doc_text` route to the
    broker whenever `broker_configured()`, else the local SA (operator's own box). To
    avoid a stale broker dead-ending mid-run, `drive_adapter.py broker-preflight` probes
    the broker's `capabilities` (with a side-effect-free `probe:true` fallback) and the
    provisioner HOLDs at STEP 5 by NAME (AF-AE-BROKER-ACTIONS-MISSING) on any missing
    action. The n8n workflow asset ships at
    `config/n8n/anthology-drive-broker.workflow.json` (import + activate it per its
    README; the per-Doc branches use Drive-scope-only endpoints -- files.create + media
    update + files.export -- so the single Google Drive credential suffices).
11. PIPELINE FIND-AND-BIND: GoHighLevel exposes no API to create a pipeline --
    pipelines are UI-only. The standard Anthology pipeline must pre-exist in the
    CLIENT's OWN Convert and Flow account (shipped in the snapshot, or hand-built
    once in the UI); onboarding FINDS it BY EXACT NAME through the CLIENT's OWN
    private integration token and BINDS to it, STOPPING setup with
    AF-AE-PIPELINE-UI-CREATE if it is absent. The per-gate pipeline-stage update
    fires at EVERY gate from the registry stage map, never hardcoded.
12. THE PRODUCER TRIGGER: S9 assembly fires ONLY on the producer's explicit
    ready-to-assemble trigger, from the Assembly card or the readiness nudge (both
    doors, one endpoint). Guards, enforced by the writer's legal-transition matrix
    and never by UI alone: own-producer auth; every participant approved or
    explicitly excluded; at least the configured minimum of frozen approved chapters
    (floor 2); typed anthology-name confirmation; one-way. The final sign-off closes
    the anthology.
13. IDEMPOTENT, RESUMABLE STATE: every stage is one idempotent job against the
    durable ledger; a crash, a credit outage, or a six-month pause costs nothing;
    insufficient credits HOLD durably with ONE deduped founder alert; duplicate
    webhook deliveries acknowledge without a second run. `anthology_state.py` is the
    SOLE ledger writer and enforces the legal-transition matrix.
14. MOVE IN SILENCE: operator-verbose, client-silent; the only client-facing copy is
    the three sanctioned nudge templates, with zero em dash characters and zero code
    fences; the recipient is always the ledger-resolved address.

## Client-exact overrides win

Any client-stated exact word target is honored verbatim, never floored, capped, or
substituted (fleet-wide absolute law), and ONLY through the audited override
channel Skill 54 already enforces (`working/overrides.json`, brief-tied and logged);
an unlogged override fails closed.

## The layer law

Layer 2 (orchestration) is the ONLY layer that writes the ledger, routes models, or
opens gates. Layer 1 (Skill 54) is a local subprocess with no external I/O beyond
its model calls. Layer 3 adapters read back every external write in the same job.
Layer 4 (the Command Center board and token page) holds no base credential and
writes state ONLY by shelling `anthology_state.py`.
