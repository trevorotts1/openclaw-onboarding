# ZHC Buildout Experience — The Standard Every Client Gets

This is the single, standardized Zero Human Company (ZHC) buildout experience.
Every client who goes through Skill 23 receives the SAME five stages, in the same
order, to the same quality bar. Read this end-to-end before you start a build, and
use the **ZHC BUILDOUT CHECKLIST** at the bottom to QC your own work.

The five stages: **Interview → Build → Wire → Closeout → Operations.**

---

## Stage 1 — Interview (the AI Workforce interview)

You learn the business well enough to staff it. This is a conversation, not a form.

> ### HARD RULE — ONE QUESTION AT A TIME
> Ask **exactly one question at a time. Never batch questions.** Wait for the
> answer, acknowledge it, then ask the next one. Batching questions overwhelms the
> owner and **overwhelm = failure** — it is the fastest way to lose the build.
> A wall of ten questions is a violation even if every question is good.

Interview discipline:
- Plain English only. No jargon, no acronyms the owner did not use first.
- Check what you already know first ("We already know you run a med spa — still
  correct?") before asking. Confirm, don't re-ask.
- Offer research instead of guessing ("Not sure what KPIs matter for your
  industry? I can look up best practices — want me to?").
- Flush state after EVERY answered question (`update-interview-state.sh`), and
  update the handoff file, so a session limit never loses progress.
- Show progress at milestones ("That's marketing done — 3 of 16 departments.").

What you must come out of Stage 1 with: company name, industry, mission, the
owner's values + communication style, the connected systems, and per-department
activities / KPIs / tools / challenges for each department the client confirms.

---

## Stage 2 — Build (the floor is mandatory, the library does the writing)

`build-workforce.py` stands up the company tree against a HARD floor — never a
reduced workforce.

- **The canonical floor** (run `scripts/list-canonical-departments.py` for the current count)
  of mandatory departments PLUS the 7 universal-primary vertical-pack departments
  (one per pack — fires for EVERY client regardless of industry),
  MINUS only departments the client explicitly declined. Industry keyword matching
  adds additional vertical extras on top of the floor but never reduces it.
  The floor is enforced on DISK by `department-floor.py` (build-state JSON is
  never trusted as proof). A 3-dept, 6-dept, or reduced-dept ship is a bug, not a
  "lean build." See `department-naming-map.json` vertical_packs for the 7 packs
  and their universal_primary departments.
- **Directors are real agents.** Each department gets a first-class OpenClaw agent
  registered in `openclaw.json` `agents.list[]` (id `dept-<id>`, own workspace,
  own `agentDir`, model, and a `subagents` block so it can spawn at runtime).
- **Specialists are role folders instantiated FROM the role library.** Each
  specialist is a folder under its department (`NN-role-slug/`) with
  `IDENTITY.md / SOUL.md / MEMORY.md / HEARTBEAT.md / how-to.md / SOP/` and
  symlinked `AGENTS/TOOLS/USER`. Their `how-to.md` is **token-filled from the
  233-template role library + SOP library** — minimal token burn, identical
  across clients. **Do NOT regenerate a doc with an LLM when a template exists.**
  LLM/free-form writing is reserved ONLY for roles with no comparable template
  (and those are tracked — see Stage 3, PENDING-SOPS.md).

---

## Stage 3 — Wire (rosters, routing, read-the-SOP — the fixes this file documents)

A staffed tree is not a working company until the agents are wired to USE it.
The build now emits all three:

1. **Per-department `ROSTER.md`** — the machine-readable When-to Reference Map.
   One row per specialist role folder with a one-line *when to use* and the exact
   read-in-order path a spawned sub-agent follows.
2. **`universal-sops/00-ROUTING.md`** — the company-wide master routing file
   (task type → owning department → that department's ROSTER).
3. **Read-the-SOP Operating Protocol** baked into every agent's OWN first-read
   files (director `IDENTITY.md`/`SOUL.md`, specialist stubs, and the master
   orchestrator), so the rule does not depend on the shared `AGENTS.md` being
   loaded. The protocol, verbatim, is:

   > **Before executing ANY task:** (a) consult the department `ROSTER.md` /
   > When-to Reference Map to pick the right specialist role; (b) spawn a
   > sub-agent and instruct it to fully adopt that role by reading the role folder
   > IN ORDER — `00-START-HERE.md` → `IDENTITY.md` → `SOUL.md` → `how-to.md`
   > (the SOPs) → `governing-personas.md` — then execute per the how-to; (c) the
   > director reviews results against the how-to before reporting. If no procedure
   > covers the task, do NOT guess — fire the department SOP-Writer
   > (INSTRUCTIONS.md Moment 3.7).

4. **`PENDING-SOPS.md`** at the company root — every role whose `how-to.md` is a
   PENDING stub (no library template matched) is collected here with a one-shot
   token-fill instruction. A missing template is **never** a silent empty stub;
   the orchestrator works PENDING-SOPS.md to zero before declaring complete.

---

## Stage 4 — Closeout delivery (what the client MUST receive)

A build is not done until the client has been DELIVERED to. Every client gets the
identical closeout (per the ZHC closeout doctrine):

- **Telegram celebration sequence** to the client's own chat, including the
  **Command Center link announcement** (the live CC dashboard URL).
- **Notion page tree in the CLIENT'S OWN workspace** — never co-mingled with
  another client's workspace. (9-section tree: org chart, departments, SOP index,
  operating cadence, etc.)
- **Org chart / flowchart** of the company structure (`ORG-CHART.md` rendered).
- **Command Center explainer doc** — how the owner reads the board, the Triad
  Rule, and where SOPs live.

---

## Stage 5 — Operations (how the company runs itself afterward)

- **Triad Rule.** No task leaves backlog without a description, an SOP, and a
  persona. The Command Center enforces this gate.
- **Auto-SOP drafting.** When a task needs a procedure that does not exist, the
  missing SOP is drafted rather than the agent guessing.
- **Self-disabling build crons (NON-NEGOTIABLE).** Every build/library/resume
  cron MUST self-disable on completion. A cron that fires forever after the build
  is done is the **token-runaway failure mode** — it silently burns the client's
  budget. Each such cron checks a disk-verified completion gate and removes itself
  once met (the "BELT" pattern). Verify this before you walk away.
- **Big Project Mode.** Any large multi-part build or document the owner hands
  off afterward runs under the BIG PROJECT MODE standard appended to the agent's
  AGENTS.md (shared document pasted byte-identical at the top of every worker,
  warm-up then fan-out, skinny orchestrator, independent QC). Full reference:
  `BIG-PROJECT-MODE.md`.

---

## ZHC BUILDOUT CHECKLIST

Follow top to bottom; QC your build against the same list.

**Stage 1 — Interview**
- [ ] Asked ONE question at a time — never batched (overwhelm = failure)
- [ ] Confirmed known facts instead of re-asking; offered research over guessing
- [ ] Flushed interview state + handoff after every answer
- [ ] Captured company name, industry, mission, owner values + comms style
- [ ] Captured per-department activities / KPIs / tools / challenges

**Stage 2 — Build**
- [ ] The canonical floor of departments present on DISK (run `scripts/list-canonical-departments.py` for the exact list; run `department-floor.py --json` to verify the live client install meets it)
- [ ] Industry keyword matching added any extras on top of the 23 (check `verticalPacks.addedDepartments` in build-state)
- [ ] No department declined except where the client explicitly declined it
- [ ] Each department has a real director agent in `openclaw.json` agents.list[]
- [ ] Specialists are role folders instantiated FROM the role library (token-fill)
- [ ] No LLM doc regeneration where a template existed (check library-fill %)

**Stage 3 — Wire**
- [ ] Every department has a `ROSTER.md` (When-to Reference Map)
- [ ] `universal-sops/00-ROUTING.md` generated
- [ ] Read-the-SOP protocol present in directors, specialists, and master orchestrator
- [ ] `PENDING-SOPS.md` exists and is worked to ZERO (no silent stubs)

**Stage 4 — Closeout**
- [ ] Telegram celebration sequence sent, incl. Command Center link
- [ ] Notion page tree built in the CLIENT'S OWN workspace (not co-mingled)
- [ ] Org chart / flowchart delivered
- [ ] Command Center explainer doc delivered

**Stage 5 — Operations**
- [ ] Triad Rule active on the Command Center board
- [ ] Auto-SOP drafting path in place (no guessing on missing SOPs)
- [ ] EVERY build/library/resume cron self-disables on completion (token-runaway guard)
- [ ] BIG PROJECT MODE section present in the agent's AGENTS.md (see `BIG-PROJECT-MODE.md`)
