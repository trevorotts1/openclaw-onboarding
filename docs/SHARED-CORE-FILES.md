# Shared Core Files — Zero-Human-Workforce File Model

> **Status:** binding (N29). **Amended 2026-07-31** (authorized by Trevor,
> operator) from symlink to copy-on-run — see *Why a copy, not a symlink*
> below. Implemented by `link_shared_core_files()` in `install.sh` (Step 10a)
> and `update-skills.sh` (post-wiring), enforced by QC check `9.9` in
> `scripts/qc-system-integrity.sh`. **Widened 2026-10-29 (owner-approved, "one
> rulebook"):** the refresher now covers `agents.entries` workspaces, creates
> missing copies for registered agents, and skips backup / vendored trees. See
> *Which workspaces are covered* below.

## The rule, in one sentence

On **every box**, **all** of that account's agents and sub-agents **share that
box's ONE canonical `AGENTS.md`, `TOOLS.md`, and `USER.md` CONTENT** — via a
**real file copy**, not a symlink and not hand-duplicated. Each agent keeps
its **own** `IDENTITY.md`, `SOUL.md`, `MEMORY.md`, and `HEARTBEAT.md`.

## Why a copy, not a symlink (the amendment)

N29 originally required a **symlink** from each agent workspace's
`AGENTS.md`/`TOOLS.md`/`USER.md` to `CANON_DIR`. That is **no longer the
mechanism** — do not "restore" symlinks here.

The OpenClaw runtime enforces a **workspace-root boundary guard**
(`applyResolvedSymlinkHop`, reached via `readWorkspaceFileWithGuards`) that
**rejects any symlink whose realpath resolves outside the reading agent's own
workspace**. A rejected symlink is reported `missing: true` and a ~107-char
`[MISSING] Expected at: …` stub is injected in its place — the agent then
runs with essentially no instructions, silently, with **no error anywhere**.

This was proven live: a client's `dept-master-orchestrator` reported
`rawChars:0 / injectedChars:107 / missing:true` while its 335KB `AGENTS.md`
sat intact on disk, and answered that it had no defined CEO routing /
escalation procedure.

No config key, env var, or flag reaches that call site, and the guard is
unchanged between OpenClaw `2026.6.11` and `2026.7.1-2` (the newer build is
*stricter*, not looser). Repointing an agent's own `workspace` at
`CANON_DIR` would satisfy the guard, but only by collapsing that agent's
per-agent `IDENTITY.md` / `SOUL.md` / `MEMORY.md` / `HEARTBEAT.md` / `memory/`
/ `skills/` into the canonical agent's — destroying the very isolation N29
exists to protect. A real file copy is invisible to the guard (it has no
symlink hop to reject), so it is the only mechanism that satisfies both N29's
intent (one canonical source, zero drift) and the runtime's boundary rule.

## Shared vs per-agent

| File | Scope | How it lives in an agent workspace |
|------|-------|-------------------------------------|
| `AGENTS.md` | **SHARED** (one canonical source per box) | real file, byte-identical copy of `CANON_DIR/AGENTS.md` |
| `TOOLS.md` | **SHARED** (one canonical source per box) | real file, byte-identical copy of `CANON_DIR/TOOLS.md` |
| `USER.md` | **SHARED** (one canonical source per box) | real file, byte-identical copy of `CANON_DIR/USER.md` |
| `IDENTITY.md` | **per-agent** (own real file) | the agent's own file — never touched* |
| `SOUL.md` | **per-agent** (own real file) | the agent's own file — never touched |
| `MEMORY.md` | **per-agent** (own real file) | the agent's own file — never touched |
| `HEARTBEAT.md` | **per-agent** (own real file) | the agent's own file — never touched |

\* `IDENTITY.md` is only ever **added to**, never overwritten — see *Backups &
content preservation* below.

A copy means the canonical edit propagates only on the **next**
`install.sh` / `update-skills.sh` run, not instantly like a symlink would —
that one-roll propagation lag is the accepted cost of a mechanism the runtime
actually honors. An update run therefore re-copies canonical content into
every agent's file every time it runs (a no-op when content already matches),
so drift is bounded to at most one missed roll.

### Why these three are shared

`AGENTS.md` (operating procedures / protocols), `TOOLS.md` (local tool notes /
conventions), and `USER.md` (the human being served) are **the same for every
agent on the box**: the operating rules, the tooling, and the owner do not
change agent-to-agent. Sharing one canonical source means a single edit
propagates to every agent and sub-agent on the next update run, with zero
drift beyond that one roll. The per-agent files (`IDENTITY`, `SOUL`, `MEMORY`,
`HEARTBEAT`) encode *who that specific agent is* and *what it remembers* —
those must stay distinct.

## CANON_DIR — what the copies come from

`CANON_DIR` is **the box's default agent workspace** — resolved with the same
precedence used everywhere else (`install.sh` Step 10 / `obs_resolve_workspace`):

1. per-agent `main` override: `agents.list[<main>].workspace`
2. `agents.defaults.workspace`
3. canonical default: `~/.openclaw/workspace` (Mac) / `/data/.openclaw/workspace` (VPS)

The canonical `AGENTS.md` / `TOOLS.md` / `USER.md` live in `CANON_DIR`. Every
other agent workspace gets its own **copy of that content**.

## Co-mingling guard (CRITICAL — N0)

The copy source is **always the LOCAL box's own canonical** — i.e. that box's
default agent workspace, resolved from **that box's own `openclaw.json`**. It is
**NEVER** a hardcoded path and **NEVER** a cross-box / cross-account path.

A client box copies from the **client's own** files. The client is the USER. A
client agent must **never** have the operator's, Trevor's, or another
client's content copied into it. The resolver reads only the local box's
`openclaw.json` and resolves only the local workspace, so a foreign path's
content can never be written into a client's file. This is the
[NO-COMINGLING-RULE](../NO-COMINGLING-RULE.md) applied at the filesystem layer.

## Which workspaces are covered (one rulebook, 2026-10-29)

Every agent and department on a box uses ONE rulebook: its `AGENTS.md`,
`TOOLS.md` and `USER.md` are identical to the box's one master copy
(`CANON_DIR`). Symlinks stay forbidden (see *Why a copy, not a symlink*), so the
master is a real file and every other workspace holds a real copy that each
`install.sh` / `update-skills.sh` roll re-syncs. Both scripts build the same
candidate set (the `LSC-CANDIDATES-BEGIN` block, kept byte-identical by
`tests/unit/shared-core-entries-sync.test.sh`):

| Source | What it is | Missing file |
|--------|------------|--------------|
| `agents.entries{}` | the current config shape: an object keyed by agent id, each with a `workspace` | **created** from the master |
| `agents.list[]` | the legacy shape: an array whose entries carry their own `workspace` | **created** from the master |
| `agents.defaults.workspace` | the workspace of every agent that declares none | **created** from the master |
| scan of `<oc-root>/workspaces` (includes `workspaces/command-center/<dept>`) | agent-shaped folders (they hold an `AGENTS.md`, `IDENTITY.md` or `SOUL.md`) | stays absent |
| scan of `<canon>/agents` and `<canon>/departments` (includes `departments/<dept>/<role>`) | same | stays absent |
| scan of THIS box's own company tree: `<companyRoot>/departments` from `.workforce-build-state.json`, and `<master-files>/zero-human-company/<this box's slug>/departments` (master-files = `$MASTER_FILES_DIR`, the Downloads and `/data` master-files folders, the OpenClaw workspace, the canonical workspace) | where Skill 23 builds `<dept>/<role>` folders | stays absent |

A *registered* workspace is a real agent, so a missing core file is created for
it. A folder found only by the scan is kept in step when it already holds a
core file and never gains one (no churn).

**Role folders (U053 disposition, unchanged).** A department role folder
(`departments/<dept>/<role>`) carries no `AGENTS.md`: the U053 pass retires it
with a backup, and the sync does not recreate it, even if the folder is
registered. A role folder still keeps `TOOLS.md` and `USER.md` as real copies
and they are re-synced and created like any other. If a role folder is ever
registered as its own agent and must load an `AGENTS.md`, that is a U053
decision for the owner, not something this sync overrides.

**The scan never rewrites a file that belongs to something else.** It does not
descend into:

| Skipped | Where |
|---------|-------|
| a hidden folder (`.*`, which covers `.floor-backups` and `codex-home/.tmp`), `*.bak*`, `*.backup*`, `departments-archive`, `node_modules` | at any depth |
| `skills`, `templates`, `onboarding`, `fleet-refresh`, `codex-home` | only INSIDE an agent workspace, meaning the parent folder holds `IDENTITY.md` or `SOUL.md` |
| `onboarding`, `fleet-refresh`, `codex-home` | at depth 1 of `<oc-root>/workspaces`, where the roll keeps its own trees |

So a backup copy, an agent's vendored skill folder and a template tree keep
their own `AGENTS.md`, while a real department that is merely NAMED `templates`,
`onboarding` or `skills` under `workspaces/command-center/` is kept in step.
Registered workspaces are the owner's explicit list and are not filtered by
name at all. The walk is python `os.walk`, so a scan root that is itself a
symlink (a symlinked `departments/`, `agents/` or `workspaces/`) is walked.
QC check 9.9 runs the byte-identical function (kept equal by
`tests/unit/shared-core-entries-sync.test.sh`).

**Company tree, this box only (co-mingling guard N0).** The scan reaches the
role folders Skill 23 writes under the company tree, found the way
`materialize-dept-agents.sh` finds them: the build state's `companyRoot`
(`.workforce-build-state.json`) and
`<master-files>/zero-human-company/<slug>/departments`, where `<slug>` is
`$COMPANY_SLUG` or the build state's `companySlug` / `clientSlug`. When the box's
own slug is not known, no master-files company tree is read at all (fail
closed; `materialize-dept-agents.sh` falls back to every company with a warning,
this sync does not). Another company's folder on the same disk is never
touched.

**A create failure does not block the roll.** If a registered workspace that
never had a core file cannot be written (for example a read-only folder), the
sync warns loudly (`verified create FAILED`, counted as `create-failed=N` in the
summary line) and carries on; the updater still stamps the version. A failure to
replace an EXISTING drifted file still fails the step, as before.

**One rulebook includes the remote-rescue agent.** The `remote-rescue` agent's
workspace gets the box's `USER.md` like every other registered agent. That is
the owner's rule (one rulebook for every agent); it is not an oversight.

**Department-specific content goes in that department's `IDENTITY.md`, never in
`AGENTS.md`, `TOOLS.md` or `USER.md`.** Hand edits to a department copy are
overwritten on the next roll (the original is kept in `.bak-unify-<ts>`, newest
`UNIFY_BAK_KEEP`). On the first sync of a drifted copy, any block the master
does not already contain is appended to that department's own `IDENTITY.md`.
That is how the two department-specific role-library tool files
(`templates/role-library/presentations/TOOLS.md` and
`templates/role-library/rescue-rangers/TOOLS.md`) behave: a freshly scaffolded
department starts with that file as its `TOOLS.md`, the next sync replaces it
with the master and the whole of its unique content is preserved in the
department's `IDENTITY.md` (41 and 18 unique blocks; proven by
`tests/unit/shared-core-entries-sync.test.sh` case S9). The owner wants ONE
rulebook, so the template stays as the starting point and the master wins on
the roll. Text that names a department (for example the Persona Operating
Protocol, which carries the department's folder name) belongs in that
department's `IDENTITY.md`, never in the master `AGENTS.md`, which reaches every
agent on the box.

## Nested workflow agent exemption

Internal **workflow micro-agents** — any workspace path matching
`*/workflows/*/agents/*` (for example `workflows/bug-fix/agents/triager`) — are
**EXEMPT** and are **never touched**. They are ephemeral internal workers of a
workflow, not account agents, and must keep their own files.

## Backups & content preservation (never destructive)

When an agent workspace has a **real** `AGENTS.md` / `TOOLS.md` / `USER.md`
whose content **differs** from canonical, the unifier:

1. **Backs it up** to `<file>.bak-unify-<timestamp>` — the original is never
   discarded, it is retired into a backup.

   **Retention is bounded (2026-09-21).** Only the newest `$UNIFY_BAK_KEEP`
   backups (default **3**) are kept per target; older ones are deleted
   oldest-first. Set `UNIFY_BAK_KEEP` to change the count (`0` keeps none).
   Before this, the set was unbounded: a canonical file that differs between
   rolls left one FULL-SIZE copy per target per roll, forever. Measured live on
   a client Mac Mini: 25,604 `AGENTS.md.bak-unify-*` files / 4.3 GB across the
   department tree, written daily since 2026-06-23, with the disk at 95%. Only
   a target's OWN `.bak-unify-<timestamp>` siblings are ever pruned — no other
   file is touched.

   **A roll reclaims the backlog on its own (v25.1.73).** The prune runs for
   every target on every run, before the file is inspected, so it also reaches
   a target that is absent (its `AGENTS.md` deleted by the U053 disposition
   pass) or already byte-identical to canonical. No operator action is needed.

   **A roll also reclaims what the scan cannot see (v25.1.74).** The
   per-target prune above only ever reaches a path the unify **scan**
   enumerated, and that scan reads `$OC_ROOT/workspaces`,
   `<workspace>/agents` and `<workspace>/departments`, keeping only dirs that
   still carry a live `AGENTS.md` / `IDENTITY.md` / `SOUL.md`. Three
   populations are structurally invisible to it, all three measured on client
   boxes 2026-09-22 (71,805 files / ~8.4 GB across 6 boxes, oldest
   2026-06-07):

   | Population | Why the per-target prune never reached it |
   |---|---|
   | **Orphans** — a role folder whose live core files were deleted or moved, and hidden archive dot-dirs | It fails the scan's live-file filter, so it is never enumerated |
   | **Out of tree** — `<workspace>/zero-human-company/<co>/departments/...` and `~/clawd/zero-human-company/<co>/departments/...` | Under neither `agents/` nor `departments/`, so the scan never descends into it |
   | **An early exit** — the unify step refused (workspace unresolved), was skipped, or filtered a workspace out | Nothing bounded that run at all |

   `reclaim_unify_backups()` therefore runs **once at the end of every roll**
   in both `install.sh` and `update-skills.sh`, after the unify step and
   **regardless of whether that step succeeded**. It walks this box's own
   resolved roots (the OpenClaw root, the resolved workspace, `~/clawd`,
   `~/.clawdbot`), groups every backup by its target prefix and keeps the
   newest `$UNIFY_BAK_KEEP`, then reports the count reclaimed. It always
   returns success — a reclaim must never be the thing that fails a roll.

   **What it will refuse to delete.** A file is deletable only when its
   basename matches `<target>.bak-unify-<8 digits>-<6 digits>[-<n>]` exactly
   (the `-<n>` tail is the python writer's same-second de-dupe suffix). A live
   `AGENTS.md` / `TOOLS.md` / `USER.md` cannot match that pattern, and neither
   can a hand-made `.bak-manual` or an `AGENTS.md.bak-unify-notatimestamp`.
   Symlinks and non-regular files are never unlinked.

### `UNIFY_BAK_KEEP` — the single retention knob

   | Value | Meaning |
   |---|---|
   | unset | keep the newest **3** backups per target |
   | *N* ≥ 1 | keep the newest *N* |
   | `0` | keep **none** — every backup of every target is removed |
   | anything non-numeric | falls back to the default **3** |

   The same variable governs the per-target prune, the end-of-roll reclaim,
   and the python department-tree writer, so one value means one thing
   everywhere. `0` is safe despite emptying the backup set: the pattern above
   makes a live core file unmatchable, so `0` can empty the backups, never the
   tree.

   **Reclaiming an existing box's backlog.** A normal roll now does it —
   `reclaim_unify_backups()` runs at the end of every `update-skills.sh` and
   every `install.sh`, so no operator action is required:

   ```bash
   bash ~/openclaw-onboarding/update-skills.sh
   ```

   To run the reclaim on its own, without a full roll, source the shipped
   function and call it (tested as written; `note` is the logger `install.sh`
   defines):

   ```bash
   note(){ echo "$@"; }; . <(sed -n "/^reclaim_unify_backups() {/,/^}$/p" ~/openclaw-onboarding/install.sh); reclaim_unify_backups
   ```

   It prints the count reclaimed, honours `UNIFY_BAK_KEEP`, and touches
   nothing but timestamped `.bak-unify` backups.

2. **Preserves unique content**: any block in the agent's file that is **not
   already present** in `CANON_DIR/<file>` is **appended** (additive only) to
   that agent's **own `IDENTITY.md`**, under a guarded marker:

   ```
   <!-- PRESERVED FROM <agent> <file> (unification <timestamp>) blocks=<hashes> -->
   ```

   (If the agent has no `IDENTITY.md`, one is created.) This guarantees no
   agent-specific notes are lost when its file is overwritten with the shared
   content. Each block is keyed by its own hash, listed in the marker's
   `blocks=` field: a LATER, different drift of the same file is appended too,
   and a block already preserved (by hash or by its text) is never appended
   twice, so repeat runs add nothing.
3. **Overwrites** the file with a real-file copy of `CANON_DIR/<file>` — never
   a symlink — and **verifies the write by content hash** before counting it
   as a success.

A pre-existing **symlink** (a relic of the pre-amendment behavior) is
**migrated**: deleted and replaced with a verified real-file copy, always —
no preservation step runs for it, since a symlink has no content of its own
to preserve.

A file that is **absent** is created from the master when the workspace is
**registered** (`agents.entries`, `agents.list`, `agents.defaults.workspace`)
and left absent otherwise (no churn). A department role folder never gets an
`AGENTS.md` (U053).

**Fail-open, never destructive:** if the canonical source itself is
unreadable or empty, **every** agent's existing copy of that file is left
**exactly as-is** and a loud warning is printed to stderr. This function must
never write an empty or truncated core file — this is a direct regression
guard for commit `5e181ceb`, which once emptied a shared `AGENTS.md` this
exact way when the updater could not read the source.

## Idempotency

The unifier is fully idempotent:

- A real file whose content **already byte-matches** `CANON_DIR/<file>` →
  **no-op** (no rewrite, no backup, no churn).
- A **symlink** (any target) → migrated to a verified real copy (logged).
- A real file that **differs** → backed up + preserved + overwritten (once).
- An absent file in a registered workspace → created; elsewhere → left absent.

A **second run produces no new backups and no churn** — the preservation
per-block hash guard prevents re-appending, and already-correct copies are skipped by their
content hash. Every action is logged with the `[link-shared]` prefix.

## Where it runs

- **Install:** `install.sh` Step 10a — after the workspace is resolved and the
  bootstrap files exist in `CANON_DIR`.
- **Update:** `update-skills.sh` — after skills + workspaces are set up,
  `CORE_UPDATES.md` is merged, and the workforce migration runs.

## QC enforcement

`scripts/qc-system-integrity.sh` check **9.9** asserts that, for **every
non-workflow-agent workspace in the same candidate set the sync uses**
(`agents.entries`, `agents.list`, `agents.defaults.workspace`, plus the scan of
`workspaces/`, `agents/`, `departments/` and this box's own company tree, with
the same skip rules, run by the identical python function),
`AGENTS.md` / `TOOLS.md` / `USER.md` **exist as real files and are
byte-identical (content hash) to `CANON_DIR`**. A
**symlink is itself a FAIL** now, regardless of what it resolves to — a
symlink that happens to point at the right canonical bytes would still be
rejected by the runtime's boundary guard, so a pure content check without the
symlink test would let that exact failure mode go green again. Files that
differ in content, or are unreadable, also emit a QC failure line. A file
missing from a **registered** workspace is a FAIL (the sync creates it); a
missing file in a scan-only folder, and a missing `AGENTS.md` in a department
role folder (U053), are allowed.

## Relationship to N19

**N19** (ZHC `agents/` layout) is a **separate rule with separate
implementing code** (`agents/_shared/*` + its own symlink validator) and is
**unchanged by this amendment** — N19 is not being modified here. Before this
amendment, N29 was described as the box-wide generalization of N19's symlink
model. That description no longer holds mechanically: N29 now copies rather
than links, specifically because the mechanism it generalizes runs across
**every** agent + sub-agent workspace on the box (not just the ZHC
`departments/` tree N19 governs), which is exactly the surface the runtime's
workspace-root boundary guard polices. N29 remains N19's conceptual
descendant — the same "one canonical source, per-agent identity stays
separate" model — just realized with a mechanism the runtime actually honors
at that broader scope.
