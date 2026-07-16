# Fleet Roll Runbook (P6-01)

**Status:** REPO-SIDE MACHINERY — HELD. This runbook and its scripts are built,
QC'd, and merged during the earlier phases so the roll is *one command* when the
operator gives the word. **This document does not start a roll. Nothing here
touches a box until the operator says GO** (Section 9, D-1 of the master spec).

**Scope:** the single, batched, reversible, all-phases fleet roll — the FINAL
phase (P6-01). It deploys everything that landed repo-side in the earlier phases
onto boxes that are ALREADY provisioned. It is the sanctioned batch vehicle;
per-fix rolls are not doctrine.

**Fleet-generic by rule.** This repo is a fleet-wide template. This runbook names
ZERO boxes and ZERO people. Which box plays each pre-roll proving role, the wave
membership, and the per-box remediation checklist live in the operator's private
notes, never in this repo. See `scripts/qc-assert-no-client-names.sh` (enforced
on every commit by `.githooks/pre-commit`).

---

## Routed hand-off items (scope-boundary decisions landed in this run)

Items below were explicitly ROUTED to this run by another spec's scope-boundary
decision — never silently absorbed, never left unowned. Each row names the
mechanism that already exists in the repo and any deadline context the roll
must respect.

| Item | Mechanism (already built) | Deadline context | Routed by |
|---|---|---|---|
| **push-client-embeddings** — publish the `shared-utils/sop-embed-once/` + `shared-utils/prebuilt-index/` release assets; per-box read-only pull; per-box verify | `shared-utils/sop-embed-once/build-and-publish.sh:1-17` (embed the canonical SOP library ONCE with the operator's key; every client box pulls a versioned asset read-only — the fix for the prior broken state where the only writer of `sop_embeddings` was a per-client backfill burning the CLIENT's own key) | `gemini-embedding-001` hard shutdown 2026-07-14 (code-verified: `scripts/pre-july14-embedding-migration-check.sh`) | Skill 6 blended-persona-kanban v2, decision D21 (X.3) — recommendation: FLEET-ROLL scope, ROUTED not dropped |

**What this run owns:** DISTRIBUTION only — publishing the versioned release
asset(s) and, on each box's payload pass, a per-box read-only pull + verify
(Section 5's payload, Section 7's health gate). **What this run does NOT own:**
the operator-box-only embed-once BUILD step (`build-and-publish.sh` itself) —
that can run any time before the roll and is not part of any box's payload.

---

## 0. What a fleet roll IS (and is NOT)

A fleet roll is an **in-place UPDATE of already-provisioned boxes**. It is **NOT
a fresh install and NOT a re-provision.** Every box already has its own client
state: its memory database, its credential stores, its Command Center board data,
its crontab, its `openclaw.json`. The roll updates *code and content* and runs a
bounded *remediation* pass. **All client state is preserved. If a step would
re-initialise, reset, or overwrite client state, that step is wrong — stop.**

The distinction is load-bearing because the destroyers this runbook bans
(Section 6) all masquerade as ordinary steps while quietly resetting a store.

---

## 1. MODEL POLICY (who does what — no exceptions)

The roll uses exactly two model tiers, and never a third.

- **Opus 4.8 owns all judgment.** Every decision that is not a fixed mechanical
  step is Opus's: pre-roll proof analysis, per-box health verification, per-box
  **credential-integrity** verification, and *every* rollback, retry, skip, park,
  or anything off-script. If a box does something the script did not anticipate,
  an Opus agent decides what happens next. No lower tier may improvise on a box.
- **Sonnet 5 does the mechanical per-box execution** — running the payload steps
  in order — **under Opus verification.** Sonnet executes; Opus judges the result
  of each box before it counts as done.
- **Fable is NEVER used in the roll.** Not in planning, not in execution, not in
  verification. This is a hard constraint, stated so no agent reaches for it.

This section changes no model catalog. It adds, removes, and substitutes nothing.
It only assigns which existing tier owns which part of the roll.

---

## 2. TWO PLATFORM PROOF BOXES (required before any wave)

The Mac path and the VPS/Docker path are **different code paths** (Section 5).
A roll proven only on one platform is unproven on the other. Therefore, before
wave 1, the roll is proven end-to-end on **exactly two proving boxes, one per
platform** — plainly:

1. **One Mac proving box = the operator's OWN Mac.** Zero client risk: it is the
   operator's own machine, so a bad roll harms no client. This is the operator's
   standing "prove it on my own box first, no client box until it passes"
   doctrine.
2. **One VPS proving box = an operator-AUTHORIZED Docker VPS box.** The operator
   owns no VPS of their own, so the VPS path is proven on a box the operator has
   explicitly authorized for this purpose. The authorization and the identity of
   that box live in the operator's private notes, NOT in this repo.

**Both must pass end-to-end BEFORE any wave — and end-to-end INCLUDES A REBOOT.**
"The update applied" and "the container came up" are not the bar. The proof is:
apply the roll → run the full health gate (Section 7) → **reboot the box** (Mac:
restart; VPS: restart the host/container) → run the full health gate AGAIN and
confirm the box still authenticates and the update is still live. An update that
does not survive a reboot is a false completion (N40). Only after **both**
platform proving boxes survive a reboot with a green health gate does wave 1 start.

> Naming note (no coded language): these are "platform proving boxes" — say
> plainly which platform (Mac / VPS) and that the Mac one is the operator's own
> box. Do not refer to them by any obscuring codeword, and never write which
> specific box is which into this repo.

---

## 3. PER-BOX PRE-FLIGHT (run on every box, before its payload)

For **every** box, in this order, before applying any payload:

1. **Run the credential-preflight-guard FIRST**
   (`scripts/fleet-roll/preflight-credential-guard.sh snapshot`). This backs up
   every credential store on the box (all env stores, the live process env, the
   host-side `.env`, the pm2 dump, any secrets files) recording only SET/NOT-SET
   plus a hash — **never a secret value** — to a safe backup path. This snapshot
   is the reference the after-check (Section 6) and any restore compare against.
   If the guard cannot read a store, it fails closed and the box does not proceed.
2. **Confirm durable state is on MOUNTED VOLUMES.** The memory database, the
   credential stores, and the board data must live on a mounted/persistent volume
   — not inside an ephemeral container layer. On a VPS this means the bind-mounts
   / named volumes in the compose file actually map these paths; a box whose
   durable state is inside the image layer is flagged and does not roll until the
   operator resolves it (a re-create would wipe it).
3. **Record the box profile** to the ledger (Section 8): platform (Mac launchd
   vs. VPS Docker), the compose file path (VPS), the host-side `.env` path (VPS),
   the volume mounts carrying durable state, and the process manager (launchd vs.
   pm2). The payload path branches on this profile (Section 5).

---

## 4. REVERSIBILITY — per-box snapshot (taken before the payload mutates anything)

Reversibility is proven on the first box before the roll proceeds. Per box, take
a **pre-roll snapshot**:

- `openclaw.json`
- Command Center `.env.local`
- the crontab
- the Command Center git SHA (the pinned version to roll back to)
- (the credential-store snapshot from Section 3.1 is part of this set)

**Revert = restore the snapshot + `git checkout <old-sha>` + atomic re-deploy +
`preflight-credential-guard.sh restore` if a credential store drifted.** The roll
does not start until the snapshot-and-revert path is *proven* on the first
proving box (Section 2) — snapshot, roll, then actually revert and re-roll it.

---

## 5. THE TWO PLATFORM PATHS (spelled out)

The per-box payload branches on the profile recorded in Section 3.

### 5a. MAC path (launchd)

- Update via the fresh-clone updater path (never a stale local copy), piped via
  `bash -s` (never zsh-assumed — the updater is bash, the Mac agent shell is zsh).
- **Write config as the box user, NOT root.** A root-owned config write freezes
  the gateway with `EACCES` on the next start. Run config-writing steps as the
  normal box user (`-u <boxuser>` where a wrapper elevates), never as root.
- Restart via the box's launchd mechanism; confirm the gateway comes back and
  authenticates (Section 7).

### 5b. VPS / DOCKER path

- **Image pull + `docker compose up -d --force-recreate`.** NEVER a bare
  `docker compose restart`. A bare `restart` keeps the OLD image **and** skips
  re-reading `env_file` — so the box looks restarted but runs old code with a
  stale env. Always `up -d --force-recreate` after the pull.
- **The host-side `.env` (e.g. `/docker/<project>/.env`) is READ, NEVER
  rewritten.** It holds the box's real credentials. The roll consumes it; it does
  not author it. Any step that would rewrite it is banned (Section 6).
- **`pm2 save` after any change** that touches a pm2-managed process. The pm2
  dump re-injects the OLD environment on the next reboot otherwise — so a change
  that looked applied silently reverts on restart (this is exactly why the reboot
  is part of the proof, Section 2).
- **Write config as the `node` user, NOT root** (`-u node`). Root writes freeze
  the gateway with `EACCES`.
- **`chown -R node <workdir>` after any push/clone into the container workdir.**
  A root-owned workdir breaks the node process on the next start.

---

## 6. CREDENTIAL SAFETY (the roll never resets a credential store)

**The roll is CODE-ONLY with respect to credentials.** It never re-initialises,
re-keys, resets, or clears any credential store. It reads them; it does not
author them.

**BANNED — the known destroyers (never invoke these on the roll path):**

- **A bare Google-Workspace `gws` headless call.** In a headless / non-interactive
  context `gws` cannot unlock its keyring and its own failure mode rewrites the
  default credential to `credential_source:"none"` — self-wiping every account's
  OAuth. The roll never invokes `gws`. (Resilience is baked by
  `scripts/harden-gws-credential-resilience.sh`; the roll must not undo it.)
- **The old destructive Skill-23 kill/reset script.** It wiped a box once. It is
  never part of the roll payload.
- **Any script that writes to a `/data`-else-`$HOME` default path** and thereby
  clobbers the live workspace. Scripts that pick a workspace root by a
  `/data`-else-`$HOME` default must be pinned to the box's real workspace before
  they run, or excluded from the roll.

**Before/after credential-integrity check with halt-and-restore on drift:**

- **Before** each box's payload: `preflight-credential-guard.sh snapshot`
  (Section 3.1).
- **After** each box's payload:
  `preflight-credential-guard.sh verify`. If ANY credential store changed,
  disappeared, or flipped SET→NOT-SET relative to the snapshot, the guard exits
  nonzero. On nonzero: **HALT that box, do not mark it done, restore with
  `preflight-credential-guard.sh restore`, and hand the box to an Opus agent**
  for judgment. Credential drift is never "acceptable and continue."

The guard **never prints a secret value** in any mode — it records and compares
only SET/NOT-SET plus a hash.

---

## 7. HEALTH GATE (the bar a box must clear to count as rolled)

"Container up" is NOT the bar. A box passes only if it still **authenticates**
AND the update **survives a reboot.**

**Authentication (all must hold):**

- Gateway process up and answering.
- The GoHighLevel token works (a real authenticated call succeeds, not merely a
  process being alive).
- Google / Telegram credentials work (a real check, per the box's configured
  providers).
- Active language models > 0 (the box is not structurally mute).

**Survives a reboot:** reboot the box, then re-run the authentication checks and
confirm the rolled version is still live and the credential-integrity check
(Section 6) still passes. If any check fails only after reboot, the box has NOT
passed — diagnose, do not mark done.

The per-box post-validation probe writes one JSON verdict per box to the ledger
(Section 8): rolled versions match target, gateway/health reachable, auth checks
green, credential-integrity green, reboot-survival green. A probe that cannot run
is UNKNOWN, never PASS.

---

## 8. WAVES + PERSISTENT PER-BOX LEDGER

- **Staggered waves, ≤20 boxes per wave** (engine ≤16 in practice). Large
  fan-outs stacked past this hit the server rate limit; stagger and use
  `resumeFromRunId` to continue.
- **The roll is resumable.** A persistent per-box ledger at
  `/tmp/fleet-roll-<period>/<box>.json` records each box's state (profile,
  snapshot path, payload result, health verdict, credential-integrity verdict).
  **Commit/flush the ledger after EVERY box, not at wave end** — a session that
  dies mid-wave must resume from the ledger, not restart the wave.
- **Failed boxes auto-retry once, then park with a diagnosis** — never block the
  wave. Parked boxes get individual Opus attention in parallel with the waves.
- **Never run `qc-completeness.sh` standalone** during the roll — it leaks a
  client Telegram alert. MOVE IN SILENCE: no client box receives roll noise.

---

## 9. ROLLBACK (per-box, version-pinned)

Every box carries its own revert story from its Section 4 snapshot:

1. Restore `openclaw.json`, Command Center `.env.local`, and the crontab from the
   snapshot.
2. `git checkout <pinned-old-sha>` for the Command Center + atomic re-deploy
   (VPS: re-create from the old image tag; Mac: restart via launchd).
3. If a credential store drifted, `preflight-credential-guard.sh restore`.
4. Re-run the health gate (Section 7) on the reverted box, including a reboot,
   before the box is considered safely rolled back.

Because every box is independently snapshotted and independently reversible, the
blast radius of any single bad box is that one box, and the revert is mechanical.

---

## 10. PRECONDITIONS (gate — all true before wave 1)

- Every earlier phase is built, QC'd at ≥8.5, and MERGED to its repo; both merge
  trains clean; annotated release tags cut.
- The two platform proving boxes (Section 2) have BOTH passed end-to-end
  including a reboot.
- The snapshot-and-revert path (Section 4) is proven on the first proving box.
- **The operator has said GO** (Section 9, D-1). The roll never self-starts.

**Version note:** this runbook does not bump the repo version. The version bump
is the merge step's job, per the two-repo version discipline (Section 2.6).
