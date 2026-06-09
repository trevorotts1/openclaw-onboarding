# Shared Core Files — Zero-Human-Workforce File Model

> **Status:** binding (N29). Implemented by `link_shared_core_files()` in
> `install.sh` (Step 10a) and `update-skills.sh` (post-wiring), enforced by QC
> check `9.9` in `scripts/qc-system-integrity.sh`.

## The rule, in one sentence

On **every box**, **all** of that account's agents and sub-agents **share that
box's ONE canonical `AGENTS.md`, `TOOLS.md`, and `USER.md`** — via **symlink**,
not by duplicating the files. Each agent keeps its **own** `IDENTITY.md`,
`SOUL.md`, `MEMORY.md`, and `HEARTBEAT.md`.

## Shared vs per-agent

| File | Scope | How it lives in an agent workspace |
|------|-------|-------------------------------------|
| `AGENTS.md` | **SHARED** (one per box) | symlink → `CANON_DIR/AGENTS.md` |
| `TOOLS.md` | **SHARED** (one per box) | symlink → `CANON_DIR/TOOLS.md` |
| `USER.md` | **SHARED** (one per box) | symlink → `CANON_DIR/USER.md` |
| `IDENTITY.md` | **per-agent** (own real file) | the agent's own file — never touched* |
| `SOUL.md` | **per-agent** (own real file) | the agent's own file — never touched |
| `MEMORY.md` | **per-agent** (own real file) | the agent's own file — never touched |
| `HEARTBEAT.md` | **per-agent** (own real file) | the agent's own file — never touched |

\* `IDENTITY.md` is only ever **added to**, never overwritten — see *Backups &
content preservation* below.

### Why these three are shared

`AGENTS.md` (operating procedures / protocols), `TOOLS.md` (local tool notes /
conventions), and `USER.md` (the human being served) are **the same for every
agent on the box**: the operating rules, the tooling, and the owner do not
change agent-to-agent. Sharing one canonical copy means a single edit
propagates to every agent and sub-agent instantly, with zero drift. The
per-agent files (`IDENTITY`, `SOUL`, `MEMORY`, `HEARTBEAT`) encode *who that
specific agent is* and *what it remembers* — those must stay distinct.

## CANON_DIR — what the symlinks point at

`CANON_DIR` is **the box's default agent workspace** — resolved with the same
precedence used everywhere else (`install.sh` Step 10 / `obs_resolve_workspace`):

1. per-agent `main` override: `agents.list[<main>].workspace`
2. `agents.defaults.workspace`
3. canonical default: `~/.openclaw/workspace` (Mac) / `/data/.openclaw/workspace` (VPS)

The canonical `AGENTS.md` / `TOOLS.md` / `USER.md` live in `CANON_DIR`. Every
other agent workspace links **to those**.

## Co-mingling guard (CRITICAL — N0)

The symlink target is **always the LOCAL box's own canonical** — i.e. that box's
default agent workspace, resolved from **that box's own `openclaw.json`**. It is
**NEVER** a hardcoded path and **NEVER** a cross-box / cross-account path.

A client box links to the **client's own** files. The client is the USER. A
client agent must **never** be linked to Trevor's files, to the operator's
files, or to another client's files. The resolver reads only the local box's
`openclaw.json` and resolves only the local workspace, so a foreign path can
never be written into a client's symlink. This is the
[NO-COMINGLING-RULE](../NO-COMINGLING-RULE.md) applied at the filesystem layer.

## Nested workflow agent exemption

Internal **workflow micro-agents** — any workspace path matching
`*/workflows/*/agents/*` (for example `workflows/bug-fix/agents/triager`) — are
**EXEMPT** and are **never touched**. They are ephemeral internal workers of a
workflow, not account agents, and must keep their own files.

## Backups & content preservation (never destructive)

When an agent workspace has a **real** `AGENTS.md` / `TOOLS.md` / `USER.md`
(not yet a symlink), the unifier:

1. **Backs it up** to `<file>.bak-unify-<timestamp>` — the original is **never
   deleted**.
2. **Preserves unique content**: any block in the agent's file that is **not
   already present** in `CANON_DIR/<file>` is **appended** (additive only) to
   that agent's **own `IDENTITY.md`**, under a guarded marker:

   ```
   <!-- PRESERVED FROM <agent> <file> (unification <timestamp>) -->
   ```

   (If the agent has no `IDENTITY.md`, one is created.) This guarantees no
   agent-specific notes are lost when its file is replaced with the shared link.
3. **Replaces** the real file with a symlink → `CANON_DIR/<file>`.

A file that is **absent** is left absent (no churn).

## Idempotency

The unifier is fully idempotent:

- A symlink that **already** points at `CANON_DIR/<file>` → **no-op**.
- A symlink pointing at the **wrong** target → repointed (logged).
- A real file → backed up + preserved + linked (once).
- An absent file → left absent.

A **second run produces no new backups and no churn** — the preservation marker
prevents re-appending, and correct symlinks are skipped. Every action is logged
with the `[link-shared]` prefix.

## Where it runs

- **Install:** `install.sh` Step 10a — after the workspace is resolved and the
  bootstrap files exist in `CANON_DIR`.
- **Update:** `update-skills.sh` — after skills + workspaces are set up,
  `CORE_UPDATES.md` is merged, and the workforce migration runs.

## QC enforcement

`scripts/qc-system-integrity.sh` check **9.9** asserts that, for **every
non-workflow-agent workspace**, `AGENTS.md` / `TOOLS.md` / `USER.md` are
**symlinks resolving to `CANON_DIR`**. Any that are real files (or point
elsewhere) emit a QC failure line. Absent files are allowed.

## Relationship to N19

This is the box-level realization of **N19** (ZHC `agents/` layout — role
workspaces share `AGENTS.md` / `TOOLS.md` / `USER.md` via symlink while keeping
their own `IDENTITY` / `SOUL` / `MEMORY` / `HEARTBEAT`). N29 generalizes the same
model to **every** agent + sub-agent on the box and makes it install/update-time
automatic and QC-enforced.
