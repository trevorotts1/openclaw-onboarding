# Shared Core Files — Zero-Human-Workforce File Model

> **Status:** binding (N29). **Amended 2026-07-31** (authorized by Trevor,
> operator) from symlink to copy-on-run — see *Why a copy, not a symlink*
> below. Implemented by `link_shared_core_files()` in `install.sh` (Step 10a)
> and `update-skills.sh` (post-wiring), enforced by QC check `9.9` in
> `scripts/qc-system-integrity.sh`.

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

## Nested workflow agent exemption

Internal **workflow micro-agents** — any workspace path matching
`*/workflows/*/agents/*` (for example `workflows/bug-fix/agents/triager`) — are
**EXEMPT** and are **never touched**. They are ephemeral internal workers of a
workflow, not account agents, and must keep their own files.

## Backups & content preservation (never destructive)

When an agent workspace has a **real** `AGENTS.md` / `TOOLS.md` / `USER.md`
whose content **differs** from canonical, the unifier:

1. **Backs it up** to `<file>.bak-unify-<timestamp>` — the original is **never
   deleted**.
2. **Preserves unique content**: any block in the agent's file that is **not
   already present** in `CANON_DIR/<file>` is **appended** (additive only) to
   that agent's **own `IDENTITY.md`**, under a guarded marker:

   ```
   <!-- PRESERVED FROM <agent> <file> (unification <timestamp>) -->
   ```

   (If the agent has no `IDENTITY.md`, one is created.) This guarantees no
   agent-specific notes are lost when its file is overwritten with the shared
   content.
3. **Overwrites** the file with a real-file copy of `CANON_DIR/<file>` — never
   a symlink — and **verifies the write by content hash** before counting it
   as a success.

A pre-existing **symlink** (a relic of the pre-amendment behavior) is
**migrated**: deleted and replaced with a verified real-file copy, always —
no preservation step runs for it, since a symlink has no content of its own
to preserve.

A file that is **absent** is left absent (no churn).

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
- An absent file → left absent.

A **second run produces no new backups and no churn** — the preservation
marker prevents re-appending, and already-correct copies are skipped by their
content hash. Every action is logged with the `[link-shared]` prefix.

## Where it runs

- **Install:** `install.sh` Step 10a — after the workspace is resolved and the
  bootstrap files exist in `CANON_DIR`.
- **Update:** `update-skills.sh` — after skills + workspaces are set up,
  `CORE_UPDATES.md` is merged, and the workforce migration runs.

## QC enforcement

`scripts/qc-system-integrity.sh` check **9.9** asserts that, for **every
non-workflow-agent workspace**, `AGENTS.md` / `TOOLS.md` / `USER.md` **exist
as real files and are byte-identical (content hash) to `CANON_DIR`**. A
**symlink is itself a FAIL** now, regardless of what it resolves to — a
symlink that happens to point at the right canonical bytes would still be
rejected by the runtime's boundary guard, so a pure content check without the
symlink test would let that exact failure mode go green again. Files that
differ in content, or are unreadable, also emit a QC failure line. Absent
files are allowed.

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
