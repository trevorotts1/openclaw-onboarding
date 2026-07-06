# Native Skill Invocation — Departments Operate Skills From Client Intent
**Version:** 1.0 | 2026-07-06
**Applies to:** Master Orchestrator / CEO Agent AND every Department Director + specialist (all installs, Mac and VPS)
**Status:** CANONICAL, fleet standard
**Binding source of truth:** `~/.openclaw/skills/23-ai-workforce-blueprint/skill-department-map.json`

---

## Why this SOP exists

Skills used to be **user-triggered**: a client only benefited from a skill if they
already knew it existed and asked for it by name (or typed its slash command). The
AI workforce did not proactively reach for the right skill from a client's
plain-language need.

This SOP makes skills **native department capabilities**. When a client expresses a
need in plain language — "make me a video," "write my nurture emails," "turn my
brand into ads," "give me a keynote" — the owning department's specialist reaches
for the skill that does exactly that, **without the client naming it** and without a
human operator wiring it per request.

This is the doctrine behind the four wiring layers (Departments-That-Use-Skills
PRD §4). It is a pointer document: the machine binding is the map; the runtime and
role knowledge live where each layer places them.

---

## The doctrine (binding)

1. **Skills are native tools, not user-only features.** A specialist recognizes a
   client's plain-language intent and operates the owning skill **before authoring
   by hand**. The client never has to know the skill exists.

2. **One source of truth.** `skill-department-map.json` binds every skill to its
   owning department(s), owning specialist role(s), plain-language intent triggers,
   and craft-cluster execution SOP. Every consumer feeds off it — never a second
   list.

3. **Dept-scoped selection.** A specialist is offered ONLY its own department's
   skills. A marketing task is never handed the video pipeline. This keeps the
   right tool in the right hands and prevents wrong/expensive reaches.

4. **Fail-closed on paid calls (Rule-Zero).** Operating a skill that spends money
   still requires the USD announce + budget-cap approval. Native invocation never
   bypasses the paid-call gate.

5. **Degrade gracefully.** If the runtime skill catalog is unavailable on a box,
   the specialist's role file still carries the knowledge (Layer B). If the client
   names the skill or types its slash command, that path still works.

---

## The four layers (how the doctrine is realized)

- **Layer A — Runtime keystone (Command Center).** `buildContextPack()` hands every
  dispatched specialist its department's intent-matched skills as a
  `matched_skills[]` / `DocPointerKind: 'skill'` block — skill name, one-line
  description, on-box path, and craft-SOP pointer. The specialist gets the skill
  catalog automatically at dispatch, dept-scoped, with no per-request human wiring.
  (Ships in the `blackceo-command-center` repo — separate PR/CI.)

- **Layer B — Durable role knowledge (this repo).** Each owning role's `how-to.md`
  §8 "Tools You Use" carries a marker-guarded **"Skills You Operate"** block
  (`<!-- SKILLS_YOU_OPERATE_V1 -->`) generated from the map: the skill, the client
  phrasing that should make you reach for it, the on-box path, and the craft-SOP.
  Survives a thin/manual dispatch. Stamped by
  `23-ai-workforce-blueprint/scripts/stamp-skills-you-operate.py`.

- **Layer C — Front-door reflex (CEO).** `SKILL_INTENT_ROUTING_REFLEX_V1` (injected
  into the workspace `AGENTS.md` by `scripts/apply-fleet-standards.sh`, generated
  from the map) teaches the CEO: on a plain-language intent phrase, the FIRST action
  is to route to the owning department via the signed `mc-route.sh` helper and ack —
  never self-intake, never ask "which skill?". Sits alongside the strict
  `PRESENTATION_ROUTING_REFLEX_V2` (which stays REFLEX 0 for presentations).

- **Layer D — The binding.** `skill-department-map.json` is the ONE place the
  skill↔dept↔specialist↔intent binding lives. A feeds off it, B is generated/
  validated against it, C is generated from it. One edit propagates to all three.

---

## No rot (enforcement)

A skill / role / reflex can never silently desync:

- **CONTENT-HASH gate** — editing a role's "Skills You Operate" block changes that
  role's `content_sha`; `hash-content-manifest.py` must be re-run or
  `qc-assert-repo-consistency.py` fails (rc 6). This is what lets
  `detect-stale-artifacts.py` refresh exactly the affected clients.
- **MAP-CONSISTENCY dimension** (of `qc-assert-repo-consistency.py`) — proves the
  map's structure (every client-facing skill → live dept + role, exactly one
  primary, map↔disk coverage, infra ownership, execution-SOPs resolve), that every
  owning role carries a current Layer-B block, and that the Layer-C reflex catalog
  routes every department that owns a client-facing skill.
- **Orphan check** — `scripts/check-skill-department-map.py` runs the same
  structural proof standalone.

---

## Where this is wired

- Map + orphan check + Layer-B stamper + MAP-CONSISTENCY assertion:
  `23-ai-workforce-blueprint/skill-department-map.json`,
  `.../scripts/check-skill-department-map.py`,
  `.../scripts/stamp-skills-you-operate.py`,
  `.../scripts/qc-assert-repo-consistency.py`.
- Front-door reflex: `scripts/apply-fleet-standards.sh`
  (`SKILL_INTENT_ROUTING_REFLEX_V1`).
- CEO routing carve-out: `master-orchestrator-dept/SOP-00-Owner-Task-Routing.md`
  points its request→department table at the reflex catalog.
- Repo doctrine: `AGENTS.md` `NATIVE_SKILL_INVOCATION_V1` block + the N39 rule row.
- Adding a new skill: follow `ADDING-DEPARTMENTS-ROLES-SOPS.md` "Scenario E — wiring
  a skill to a department/role".

---

*This SOP is the human-readable counterpart to the four-layer native-skill-invocation
mechanism. The machine truth is the map; edit the map and re-run the stamper +
content-hash + repo-consistency gates, never hand-edit a consumer out of lockstep.*
