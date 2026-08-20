# Podcast Client Dashboard: Command Center payload (W3.1)

This directory is an APPLY-READY file tree for the Command Center repository.
It implements the /podcast route group per design/dashboard-design.md in full,
against the podcast_state.py schema (the sole writer, W2.1). It rides the
Command Center repo's OWN serial merge train, coordinated at merge step 5 of
the Wave 6 plan; it is NOT installed by the onboarding updater and it never
merges through the onboarding train.

Writing rules honored: zero em dash characters, no triple backtick fences,
zero forbidden provider references in every file here (the W2.8 runtime
provider guard passes over this payload), no client names (fleet-wide repo).

## 1. What is in this payload (all files are NEW; nothing overwrites)

    src/lib/podcast/types.ts          Row and serialized shapes
    src/lib/podcast/db.ts             Read-only DB open; guarded auth handle
    src/lib/podcast/stages.ts         Stage taxonomy, labels, colors, fixed copy
    src/lib/podcast/serializers.ts    THE client-clean vs operator boundary
    src/lib/podcast/queries.ts        Parameterized read queries
    src/lib/podcast/auth.ts           Token gate, sessions, operator detection
    src/lib/podcast/format.ts         Client-safe formatting helpers
    src/components/podcast/*          Shell, pills, meters, rows, views, gates
    src/app/podcast/**                Client pages: overview, episode, queue
    src/app/podcast/ops/**            Operator pages: overview, queue, access
    src/app/api/podcast/**            Read-only JSON API plus the two token
                                      write endpoints (operator only)
    tests/unit/podcast-serializers.test.ts  Serializer whitelist proof (AC 6)

## 2. How the Command Center merge train applies it

1. From the Command Center repo root, copy the payload over the tree:

       rsync -a <onboarding>/58-podcast-production-engine/command-center/src/ ./src/
       rsync -a <onboarding>/58-podcast-production-engine/command-center/tests/ ./tests/

2. OPTIONAL one-line shared-file edit (global nav): add the Podcast item to
   NAV_ITEMS in src/components/AppShell.tsx after the Departments entry:

       { label: 'Podcast', href: '/podcast', icon: <Mic className="w-5 h-5" /> },

   and add Mic to the lucide-react import. The /podcast subtree carries its
   own shell (PodcastShell) with the item already present, so the payload is
   fully functional without this edit; the edit only surfaces the nav item on
   non-podcast pages. This is the ONLY shared-file touch and it belongs to
   the Command Center merge-writer, not to this slice.

3. Build gates on the Command Center train:

       npm run lint
       npx tsc --noEmit
       npm run build
       npm run test:unit

4. Run the W2.8 runtime provider guard script over the applied files (merge
   gate, PRD Section 3.3): expected result is zero findings; this payload
   contains no model ids, no provider names, no sdk imports.

## 3. Runtime prerequisites (all engine-side, per design)

- podcast_state.py (W2.1) has created ~/.openclaw/podcast-engine/podcast-engine.db
  (or PODCAST_DB_PATH). The dashboard NEVER creates the schema: a missing DB
  renders the empty state by design.
- Environment for the Command Center process:
      PODCAST_DB_PATH          same value exported to the engine (optional,
                               defaults to the engine's default path)
      PODCAST_CLIENT_ID        optional explicit client slug override
      PODCAST_OPERATOR_EMAILS  comma-separated operator allowlist (falls back
                               to OPERATOR_EMAILS); operator surfaces stay
                               closed when neither is set and no MC_API_TOKEN
                               bearer is presented (fail closed)
- Cloudflare Access rides in front via the existing middleware posture
  (REQUIRE_CF_ACCESS); this payload adds no middleware and no bypass.
- Config writes run as the node user, never root.

## 4. Auth model implemented (design Section 11)

- Layer 1: Cloudflare Access (existing middleware, unchanged).
- Layer 2: revocable dashboard token. Hash-only storage (sha256) in
  podcast_dashboard_tokens; raw value shown exactly once at mint. The paste
  gate exchanges the token for an HttpOnly, Secure, SameSite=Lax cookie that
  holds a SESSION REFERENCE (token id plus an HMAC over a box-local 0600
  secret file beside the DB), never the token. Every request re-validates
  the token row, so revocation and the podcast_client_state.active = 0
  application blade take effect on the very next request.
- Operator: Cloudflare Access email on the allowlist or MC_API_TOKEN bearer.
  Client tokens never unlock operator fields; the split is enforced at the
  API serializer boundary, not in the UI.

## 5. Kill switch (three blades) and runbook note

Blade 1 (application): revoke tokens at /podcast/ops/access plus
podcast_state.py deactivate-client; both the token check and the active
check fail closed in this payload. Blade 2 (edge): Cloudflare Access app and
tunnel ingress removal, executed by revoke-podcast-client.sh (W2.11). Blade
3 (engine): the deactivated engine refuses new submissions (webhook layer).
The fleet Cloudflare revocation runbook append (acceptance criterion 8) is
owned by W4.13 so this slice never edits that shared document; the dashboard
side exposes no mutation beyond token revocation.

## 6. Acceptance criteria mapping (design Section 15)

1  Read-only enforcement: db.ts opens episode data { readonly: true,
   fileMustExist: true }; the auth handle throws PodcastDbWriteError on any
   episode-table or DDL statement. Schema creation exists nowhere in the app.
2  podcast_state.py subcommands and transition matrix: owned by W2.1
   (feat/podcast-state-writer); this dashboard is built against that schema.
3  Idempotency (UNIQUE client_id + submission_fingerprint): engine-side,
   proven in the W2.1 harness and the W5 canary.
4  Happy-path stage rendering: stage pills, 9-segment meter, timeline, and
   links panel all key off podcast_state.py output; canary W5.4 drives it.
5  Hold age, 60-day meter, aged-out sweep rendering: queue view implements
   the age meter, 50-day red border, Expired group over aged_out rows.
6  Serializer matrix: proven by tests/unit/podcast-serializers.test.ts on
   serialized JSON, not the UI.
7  Token round trip and active = 0 fail-closed: session and ops endpoints
   implemented here; engine-side job refusal is the webhook layer's half.
8  Revocation runbook append: W4.13 (cross-referenced, not duplicated).
9  Visual parity: reuses tailwind.config.ts, globals.css, Breadcrumb,
   avatar gradients, kanban scroll classes, card and pill conventions, and
   brand-* utilities everywhere a brand hue appears, so BrandTheme recolors
   the dashboard with zero per-component edits.
10 Responsive: 375 stacked cards and bottom nav padding, 768 collapsed
   sidebar and 2x2 KPIs, 1280 full shell with drawer and board toggle; no
   horizontal body scroll (board scrolls inside .kanban-scroll only).
11 No secret rendering: serializers whitelist; last_error is operator-only
   and pre-sanitized by the writer's redaction filter; tokens render only as
   ids and labels; no webhook URLs anywhere.
12 Empty, loading, error states incl. the no-DB-file case: states.tsx plus
   null-db handling in every route.
13 Fixed strings from Section 8.3 and 8.1 are verbatim in stages.ts; zero em
   dashes in every file.
14 Gate A 8.5 rubric: scored on the onboarding SESSION-LOG entry for this
   slice before the merge trains run.

Board caller (producer side)
-------------------------

The Podcast department producer-side board caller (`scripts/cc_board.py`)
cards episode runs onto the Command Center Kanban board. It is a FAIL-SOFT
caller -- a board outage never fails an episode run.

Show label convention (two-show fleet model)
---------------------------------------------

Every podcast client in the fleet publishes TWO shows under the single
Podbean host account:

  1. the PERSONAL show (solo episodes), and
  2. the INTERVIEW show (guest episodes).

The publish roster (podcast_publish_roster) carries one row per SHOW, so a
single client legitimately owns two roster rows (same email + last name,
different podbean_channel_id), and Skill 58 modes mirror the split
(modes/personal.md vs modes/interview.md). Because one client maps to two
shows, the episode card on the CC Podcast lane MUST say which show the
episode belongs to, otherwise personal vs interview episodes for the same
client are indistinguishable on the lane.

Convention: the caller of run-begin carries the show name. Pass
--show-name <name> with the client's show name (resolved upstream from the
matched roster row) and the card title becomes:

  Episode: <title> - <show> (<client>)

The separator is a plain hyphen (never an em dash). When --show-name is
absent (legacy single-row callers, or callers that have not been updated),
the title stays exactly the old format "Episode: <title> (<client>)" --
fully backward compatible. This is a labeling convenience only: the board
is never a gate, and a missing show name never fails or blocks an episode
run.

CLI subcommands:

  run-begin   --job-id <id> --client-label <label> --episode-title <title>
              [--show-name <name>] [--department podcast]
              Creates one card on the CC board in the Podcast workspace.
              Card title: "Episode: <title> (<client>)", or, when
              --show-name is given, "Episode: <title> - <show> (<client>)"
              (see the show label convention below).
              Idempotent: re-calling with the same job-id returns the cached
              task_id without creating a duplicate.
              Prints the task_id to stdout on success.

  patch-phase --job-id <id> --phase <slug> --status <status>
              Updates the card's phase annotation (phase_id) and CC-native
              status. Valid phases: received, researching, writing, in_qc,
              generating_art, producing_audio, publishing, enrolling, complete.
              Valid statuses: in_progress, review, done, blocked.

  close       --job-id <id> --status done|blocked [--note <text>]
              [--reason <decision|approval|credential|payment>]
              [--blocked-on-human <owner|operator>] [--permalink <url>]
              Terminal patch for the episode card.

              Blocked (--status blocked):
                Sends the full blocked triad matching the CC blocked-column
                gate (route.ts L349-377): blocked_reason (from --reason,
                default approval), blocked_on_human (from --blocked-on-human,
                default operator), and ask (from --note, default sensible
                string). blocked_reason must be one of decision, approval,
                credential, payment. A job that hit an error or needs
                re-routing should call POST /api/tasks/{id}/return-to-orchestrator
                instead. This call requires Authorization: Bearer $MC_API_TOKEN --
                the Command Center write-back API is fail-closed and 401s without
                it (never $OPENCLAW_GATEWAY_TOKEN here).

              Done (--status done):
                When --permalink is provided, registers it as a task
                deliverable via POST /api/tasks/{id}/deliverables before
                the done patch so the completion-evidence gate (T0-01,
                completion-evidence.ts L118) passes. Without --permalink,
                logs a stderr warning and still attempts (fail-soft absorbs
                the gate refusal). This call also requires Authorization: Bearer
                $MC_API_TOKEN -- the Command Center write-back API is fail-closed
                and 401s without it (never $OPENCLAW_GATEWAY_TOKEN here).

  API endpoints targeted:

  POST  {CC_BASE_URL}/api/tasks/ingest
        Creates the task in the podcast workspace (via department_slug=podcast).
        Sends: title, department_slug, source, source_ref, idempotency_key.
        Source file: src/app/api/tasks/ingest/route.ts
        Returns: {ok, task_id, workspace_id, status}

  PATCH {CC_BASE_URL}/api/tasks/{task_id}
        Updates the card's status, phase_id, and optional note.
        Requires Authorization: Bearer $MC_API_TOKEN -- the Command Center
        write-back API is fail-closed and 401s without it (never
        $OPENCLAW_GATEWAY_TOKEN here).
        When status=blocked, requires the full blocked triad:
        blocked_reason, blocked_on_human, ask (route.ts L349-377).
        When status=done, a task_deliverables row registered via the
        endpoint below must exist (completion-evidence gate T0-01,
        completion-evidence.ts L118).
        Source file: src/app/api/tasks/[id]/route.ts
        Returns: the updated task object.

  POST  {CC_BASE_URL}/api/tasks/{task_id}/deliverables
        Registers a task deliverable (e.g. the Podbean episode permalink).
        Sends: {deliverable_type, title, path}.
        Source file: src/app/api/tasks/[id]/deliverables/route.ts
        Returns: the created deliverable object (HTTP 201).

Env contract:

  CC_BASE_URL     Base URL of the Command Center (e.g. http://localhost:4000).
                  Absent -> board disabled (clean no-op).
  MC_API_TOKEN    Long-lived bearer token for the middleware auth layer.
                  Optional; sent as Authorization: Bearer header when set.
  WEBHOOK_SECRET  HMAC secret for the per-route signature layer.
                  Optional; sent as x-webhook-signature header when set.
  CC_BOARD_TIMEOUT Per-request timeout in seconds (default 5).

State persistence:

  Job-id -> task-id mapping is persisted in
  ~/.openclaw/podcast-engine/board-map.json (0600) so patch/close can find
  the card after a restart. The file is loaded at call time (no in-memory
  cache needed); atomic replace on write.

Phase-to-lane mapping (the 9 podcast production phases):

  The phase slugs below ARE podcast_state.py FORWARD_ORDER. cc_board.py
  resolves the accepted phase set from that single writer at import time,
  with a frozen local fallback, and the parity is locked by test
  (PhaseParityTest in scripts/tests/test_cc_board.py): the board can never
  card a stage the state machine cannot reach.

  Phase             Suggested CC status for in-flight work
  ------------      --------------------------------------
  received          in_progress
  researching       in_progress
  writing           in_progress
  in_qc             review
  generating_art    in_progress
  producing_audio   in_progress
  publishing        in_progress
  enrolling         in_progress
  complete          done

  Use close --status blocked --reason <decision|approval|credential|payment>
  to park a stuck episode. The blocked-column gate (route.ts L349-377)
  requires the full triad: blocked_reason (one of the four enumerated values),
  blocked_on_human (owner or operator), and ask (a non-blank human-actionable
  request string). Calls lacking any of these three fields are rejected with
  HTTP 400.

FAIL-SOFT posture:

  - CC_BASE_URL unset -> every subcommand exits 0 (no-op).
  - Any HTTP error (4xx, 5xx, unreachable, timeout) -> logged to stderr
    as "[cc_board] <message>" and exits 0.
  - Only a usage error (missing required args, invalid phase/status) exits
    with code 2.
  - Bounded 5s timeout per request, one retry on network error only.
  - A board outage never fails an episode run.

Producer binding (roll-4, closes deferred H8)
---------------------------------------------

The producer side is bound, not merely offered. scripts/podcast_state.py
(the SOLE state writer) IS the caller of this board caller: every job the
writer creates or transitions mirrors the same create/transition onto the
board, so the card rides in lockstep with the real state machine by
construction. The binding lives in the writer, not in the runbook: whether a
job is driven by the intake bridge (webhook/intake_handler.py), the
deterministic step driver (scripts/podcast_step_driver.py, invoked by the
controllerId runbook in the podcast agent's OWN tool-bearing turn), or a
manual operator command, the card lifecycle is identical with zero caller
wiring. There is no podcast_controller.py: the step driver is a TOOL the
agent calls, not a resident daemon (SKILL.md NO-DAEMON DESIGN). Every fleet
box whose podcast processor is activated (install-podcast-department.sh
during provisioning, removed by revoke-podcast-client.sh on revocation) runs
the same writer, so episode runs are kanban-visible fleet-wide, not only on
the box where the board happens to be configured. The writer drives the
three subcommands in this order:

  1. run-begin at create. The accepted submission (one job, one card; the
     job-id is the state writer's job id) lands a card in the Podcast
     workspace before the first pipeline step executes. The episode title
     does not exist at create time (podcast_jobs.episode_title is produced
     later in the pipeline), so the card lands with a "Title pending"
     placeholder; the real title rides the dashboard, not the board.
     run-begin is idempotent, and the writer mirrors it on the duplicate
     paths too, so a card missed while the board was down heals on the next
     submission.
  2. patch-phase per state transition. Each podcast_state.py advance maps to
     one patch-phase call: the phase slug is the new status (received ...
     complete, see the phase-to-lane mapping above for the suggested CC
     status of each), so the card rides the lane in lockstep with the nine
     forward segments of the dashboard meter. An advance to 'complete'
     closes the card done (with the Podbean permalink when recorded); a
     resume from the credit-out queue patches the card back to the resume
     stage.
  3. close blocked on the terminal-off-path edges. hold, fail, and
     aged-out all close the card with --status blocked and the full blocked
     triad (reason, blocked-on-human, ask) so the blocked column gate
     accepts the card.

This sequencing is TRANSITION-AWARE, consistent with rem-2: cc_board.py
reads the card's current status before a done close and PATCHes status
'review' first when needed, so the done PATCH always lands on a legal
state-machine edge (done is reachable only from review or testing). The
deliverable registration stays before the done PATCH. The board mirror
never bypasses podcast_state.py: it fires after the writer's COMMIT and
reads the job row the writer just persisted, so the board can never lead
the real state machine. The mirror is FAIL-SOFT: absent CC_BASE_URL makes
cc_board.py no-op, and any board failure is logged with the run unaffected.

Show name on the card (T8 status note)
--------------------------------------

T8 (fix/podcast-audit-t8-board-show-label, "T8 board caller carries the show
name") adds an optional --show-name flag to run-begin so the card title
becomes "Episode: <title> - <show> (<client>)" and personal vs interview
episodes for the same client stay distinguishable on the Podcast lane under
the two-show fleet model. The flag exists on origin/main; the writer's
board mirror resolves the show name from the job row (podcast_jobs.show_name,
set at create from the intake payload) and always passes --show-name when the
row carries it. The plain hyphen in the title is intentional; never an em
dash.

END OF WIRING NOTE
