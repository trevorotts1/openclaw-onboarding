# Tamper Guard - operator doc (FIX-PLAN Item 32)

Implements B12's design (build/b12-antitamper/DESIGN.md). Program:
`shared-utils/tamper_guard.py` (stdlib only). Scope registry:
`shared-utils/tamper-guard-scope.json`. Pattern set:
`shared-utils/tamper-guard-patterns.json`. Acceptance suite:
`tests/unit/tamper-guard.test.py`. Repo CI guard:
`scripts/ci/fast-guards.d/tamper-guard-manifest.sh`.

## What it does

Every in-scope skill install carries a sealed, staff-signed inventory
of its files (an `integrity-manifest.json` at the tree root: per-file
SHA-256, size, executable bit, the signed exclusion list, a digest over
the manifest body, and an HMAC-SHA256 signature under the fleet
tamper-guard key). The guard lives OUTSIDE the trees it watches, in
`$TAMPER_GUARD_HOME` or `$HOME/.openclaw/security/tamper-guard/`, and
verifies trees byte-exactly at load, on the 600 s watchdog cadence, and
after every update roll. Divergence locks that one skill on that one
install at once. Extraction behavior runs through the three-strike
ladder below: each strike is recorded and notified at warning time,
and the third standing strike (or a bulk mechanical dump, at once)
locks the struck skill. Either way, once the response fires: incident
recorded FIRST, staff notified off-box, tree moved bytes-preserved to
quarantine, stub written in its place, engine disable marker set,
in-flight runs park at the next phase gate as TAMPER_LOCKED.
Reinstatement is staff-only, gated on the recorded
user_spoke_to_staff attestation, and restores from canonical source.

## The four deviations (design Section 11; owner rulings received 2026-10-15)

Built exactly as designed. The owner accepted DEV-1 to DEV-4 as
built on 2026-10-15, and the same day amended DEV-1's posture with
the warn-first ruling implemented in the ladder section below
(design amendment: build/b38-antitamper/AMENDMENT-2026-10-15.md,
with his calls on its flagged points F1 to F8). DEV-1 is recorded
here as amended. Do not narrow any of them silently.

- DEV-1 (AS AMENDED 2026-10-15): a judgment-layer positive warns and
  logs first, as originally designed; that warn step is now strike
  one of the three-strike ladder. Every conversational and pattern
  trigger (judgment, D2, and ordinary D1/D3 events) warns first the
  same way; corroboration never skips the warning, and lockout comes
  only at the third standing strike, counted per client across all
  guarded skills. Comprehension and use never score as extraction.
  Bulk mechanical dumping and the integrity trigger still lock
  immediately. The ladder section below is the operative text.
- DEV-2: in the 999 Claude Code shape, chat replies pass through no
  hook, so a conversational lock is recorded at once, tool denial is
  immediate, and the quarantine/stub lands at the next session start.
- DEV-3: divergence inside a verified update window does not lock; a
  crashed update gets one staff-notified 24-hour grace window. Events
  are logged and notified immediately; only the lock waits.
- DEV-4: a pre-guard install with no manifest adopts a signed baseline
  from its installed tree on first run (recorded, staff-notified)
  instead of locking on day one. Post-rollout shapes can disable this
  with `--no-baseline-adoption`.

## The three-strike ladder (owner ruling 2026-10-15, DEV-1 as amended)

The guard's target is reverse engineering only: attempts to extract
the skills' internal instructions, source, or construction in order
to copy or rebuild them. Helping a client understand a skill and
make it work, including through Muse, Claude Code, or their
9router, is legitimate use and never scores as extraction.

What counts as a strike (one recorded warning event against the
client, from a non-staff context on that client's install):

- A judgment-layer positive, scored under the loosened rubric:
  comprehension and use turns are excluded from the signal counts
  by construction (the pattern file's comprehension markers, applied
  as an explicit pass in `score_transcript` before any signal phrase
  is counted; a turn naming an internal artifact or asking for
  verbatim text is never reclassified as comprehension).
- A D2 pattern hit (a dump request), refused at the time it is made.
- An ordinary D1 tool-gate trip or D3 egress block. The act itself
  is still denied or blocked at the moment it occurs; the strike is
  the consequence, and the skill locks only through the ladder.

Counting: one strike per session per trigger kind for a continuous
attempt (a repeat of the same kind inside a session that already
holds that kind's strike is refused and recorded, but records no
second strike). A corroborated positive counts as one strike;
corroboration is recorded as evidence and never skips the warning.
Strikes never expire on their own. The count runs PER CLIENT across
every guarded skill on the install: probes against two different
skills add up to the same lockout. The ledger lives in the guard
registry's top-level `strikes` list; the incident log remains the
append-only evidence, and the per-skill `judgment_warnings` list
remains the judgment layer's evidence index.

- Strike one and strike two: the request is refused or flagged, the
  client sees the warning notice (the notice states plainly that a
  strike was recorded and that Trevor was notified; it carries no
  thresholds and no counting rules), the strike is recorded, and
  Trevor is notified at warning time and asked for his call: allow
  the behavior, or remove the strike. No further consequence.
- Strike three: the struck skill locks out automatically through
  the Section 6 response (in the 999 shape, DEV-2 applies as
  accepted: record and tool denial at once, stub at next session
  start). Reinstatement follows the staff-only checklist below.

Bulk mechanical dumping locks immediately, even on a first offense
(it is not a conversational act). The thresholds, set by the crew
under the ruling and stated here exactly:

- An archive action (`archive` at the tool gate) over an in-scope
  tree: the action itself is the bulk form; no count applies.
- More than 10 denied gated source acts (D1 trips) inside one
  session (`BULK_GATED_ACTS_PER_SESSION`). The skill's own execution
  reads are allowed at the gate and never counted.
- A single egress payload carrying a verbatim span of internal text
  at or above 2000 characters (`BULK_EGRESS_VERBATIM_CHARS`, ten
  times the ordinary D3 threshold of 200).

Trevor's calls, entered by staff through the authenticated channel
only (`pardon-strike` / `allow-strike` CLI, or `pardon_strike()` /
`allow_strike()`); no reply path is built, and there is no
conversational path to either:

- Pardon ("remove the strike"): appends a STRIKE_PARDON record
  against the warning incident and marks the strike pardoned. A
  pardoned strike does not count toward the ladder and does not
  serve as a prior warning. The warning record itself is never
  edited or deleted.
- Allow ("allow the behavior"): appends a STRIKE_ALLOW record and
  voids the strike, as if never recorded. No whitelist, no time
  box: the next identical ask is judged fresh.
- Neither call reinstates a locked skill. A pardon or allow after a
  strike-three lockout reduces the standing count; reinstatement
  stays the separate staff-only flow below, because it also
  restores verified content.

The integrity trigger is NOT part of the ladder: byte-exact
divergence keeps its immediate lockout exactly as designed (DEV-3
and DEV-4 govern its window, grace, and baseline adoption,
unchanged). Guard faults never lock and never record strikes.

Client name in notifications: every record carries a `client`
field. The installer records the client's name in the guard
registry's top-level `client_name` key at install time; the
`TAMPER_GUARD_CLIENT_NAME` environment value, when set, takes
precedence. An install with neither set carries no name (`client`:
null) and the box identity stands, exactly as before; a missing
name never blocks a record, a notification, or a strike.

## Staff exemption (design Section 5)

Staff context exempts the conversational trigger ONLY through an
authenticated channel: the secrets-store staff token
(`TAMPER_GUARD_STAFF_TOKEN`, presented by staff tooling), the Command
Center operator token (`TAMPER_GUARD_CC_TOKEN`), or a staff SSH session
(the session wrapper exports `TAMPER_GUARD_STAFF_SSH=1` after SSH
authentication). A claim of staff status in conversation has no effect
on any check; it is logged as AF-TAMPER-EXEMPT-CLAIM and notified.
There is no conversational path to reinstatement, at all. Staff hand
edits still trip the integrity trigger; staff clear them through the
recorded re-baseline flow (`rebaseline`, requires a reason string).

## Keys (design Section 2.3)

Per-fleet HMAC key, following the sp-turn-ledger key template
discipline: current + previous, values only in the box secrets store
(`TAMPER_GUARD_KEYS_FILE` pointing at the secrets-held JSON, or
`TAMPER_GUARD_KEY` / `TAMPER_GUARD_KEY_ID`), never committed, never
logged; key IDs are safe to log. The previous key is accepted for 14
days from `rotation_started_at`, then fails closed; every old-key
acceptance writes a KEY_ACCEPTANCE audit record. A missing or unusable
key is a GUARD FAULT (AF-TAMPER-GUARDFAULT): staff are notified and
the skill is NOT locked. A staff provisioning mistake must not lock a
paying client as a tamperer.

Publish/CI mechanics note (design governs scope, code governs
mechanics): PR CI holds no fleet key, so the repo-committed manifest
is digest-sealed and unsigned (`signature: null`); the CI guard checks
digest consistency (FP8). The fleet key signs the manifest at
publish/install time; an install's first verification signs an unsigned
shipped manifest in place and registers its digest, and from then on
the checker requires the signature.

## Run points (design Section 2.5)

- Load: `tamper_guard.py session-start <tree> --slug <slug>` (SessionStart
  hook in the 999 shape; engine Phase-0 preflight calls `verify` and
  `gate-check` for the skills a run will use).
- Watchdog: the box scheduler runs `tamper_guard.py watchdog` every
  600 s; each pass verifies every registered tree and appends a
  heartbeat record. A stopped heartbeat is itself a staff-visible
  signal.
- Post-roll: after update-skills.sh releases its update lock, run
  `tamper_guard.py verify` per sealed tree. The guard reads the
  updater's lock (`/tmp/openclaw-update.lock`, overridable with
  `TAMPER_GUARD_UPDATE_LOCK_PATH`) for the DEV-3 update window.
- Tool gate (D1): hook/policy layers call `tool-gate` per gated tool
  call. Egress (D3): outbound paths call `egress`. Judgment: session
  end (and periodically in long sessions) calls `transcript`.

## Notification (design Section 6.2)

Skill 51's notify_transport precedent: override command
(`TAMPER_GUARD_NOTIFY_CMD`), then gateway command
(`TAMPER_GUARD_GATEWAY_CMD`), then the file queue
(`notify-outbox.jsonl` in the guard home). The transport used is
recorded on the incident record. Warning notifications go out at
warning time, not at lockout time, and every record names the
client (the `client` field; see the ladder section) with what they
were trying to do (the trigger class and the recorded evidence),
and asks for Trevor's call: allow the behavior, or remove the
strike.

## Reinstatement checklist (design Section 7)

1. Speak to the user. The reinstate command refuses without the
   recorded attestation (`--user-spoke-to-staff`).
2. Authenticate through a staff channel (`--staff-method`).
3. `tamper_guard.py reinstate <tree> --slug <slug> --incident <id>
   --source <canonical tree>`. The source is verified against its
   signed manifest before it replaces the stub; quarantined bytes are
   restored only with `--forensic --second-confirmation`, for staff's
   own unrecorded change, and the restore is recorded as forensic.
4. The reinstatement record (staff identity, attestation, source) is
   written to the incident log and notified.

## Honesty limits (design Section 9; keep these visible)

- A client who owns their box has root. Skills are plain files with
  no encryption at rest. A determined owner can read everything,
  disable this guard, or wipe the local log. This guard defends the
  agent-mediated surface, casual browsing, and unattributed drift; it
  makes tampering detected, evidenced, and reported off-box at
  trigger time. It is NOT proof against the box's root user.
- In the 999 shape, D3 cannot run on live chat text (no hook sees
  chat replies); the judgment layer runs after the fact (DEV-2).
- In OpenClaw shapes, D1 at the gateway and D3 on agent replies need
  the gateway's tool-policy / outbound-inspection hook. That hook was
  NOT verified against the installed gateway version (UNVERIFIED,
  design Section 9 point 3). The checks are implemented here; the
  gateway wiring waits on that verification. The integrity trigger
  and the whole response machinery depend on neither.
- Locking does not recall content already extracted. The claim is
  detection and response; egress rules shrink the window.
- The operator-annotation trap (design Section 3.5): any hand edit to
  a sealed tree, staff edits included, trips the integrity trigger.
  The guard cannot tell a staff annotation from an attacker's edit by
  bytes, and does not pretend to. The separation is authentication:
  staff clear it through re-baseline, on the record.
