# How to Use the Rescue Rangers Department 🚑

**Department:** Rescue Rangers
**Department head:** Director of Rescue Rangers (Dispatcher)
**Folder:** `departments/rescue-rangers/`
**Scope:** **OPERATOR-ONLY — internal fleet operations, not client-facing**
**Generated for:** {{COMPANY_NAME}}
**Last updated:** {{GENERATION_DATE}}

> This is the plain-language guide to the Rescue Rangers department. It is
> **operator-only**: it is the fleet's emergency room, not a service a client asks
> for. Clients never summon Rescue Rangers. Other agents ESCALATE to it when they
> hit a wall they cannot climb. This document explains what it is, how the
> escalation path works end-to-end, and who inside the department does what.

---

## 1. What This Department Does (in plain language)

In one sentence: **When any box in the fleet gets stuck and cannot fix itself, its
distress call lands here, gets triaged and worked, and an answer goes back — and no
call is ever dropped.**

Rescue Rangers is the **terminal escalation channel** for the whole fleet. It is
where Skill 61 (Loop Protection) sends an unresolved P1, where Skill 60 (Early
Warning) sends a broken-config alert, where the Command Center's silent-failure
sweeps report, and where every client box's AGENTS.md tells a stuck agent to go.

**This department is NOT client-facing.** It carries **no intent triggers** and must
**never** appear in a client's intent-routing catalog. A client never says "use
Rescue Rangers"; a client's own AGENT escalates to it on the client's behalf, and
the client's own agent relays the outcome back to the owner.

---

## 2. When It Is Used (who escalates, and when)

Rescue Rangers is reached by ESCALATION, not by request. A box's agent escalates
when it has genuinely exhausted its own competence:

- Triple-failure on the same symptom it cannot resolve.
- A schema/validation error `openclaw doctor --fix` did not resolve.
- An unknown error class it cannot match in `docs.openclaw.ai` or the repo.
- Anything needing a credential rotation, a Hostinger/Cloudflare/DNS change, or
  another box (one-way doors it is not allowed to open itself).
- Skill 61 Tier-3 fixes and unacked P1s; Skill 60 broken-config alerts; Command
  Center dispatch-block / stuck-in-progress / silent-failure sweeps.

It is NOT used for routine work a competent agent handles itself (silence is the
correct signal for a healthy box).

---

## 3. How the Escalation Path Works (end-to-end)

1. **Client side (the distress call).** The stuck agent POSTs a **nine-field**
   escalation to the Rescue Rangers Relay webhook (`RESCUE_RANGERS_WEBHOOK_URL`,
   with `X-Rescue-Secret`). The nine fields are: `person`, `clientName`,
   `agentName`, `boxName`, `boxType`, `openclawVersion`, `problem`, `alreadyTried`,
   `returnTo`. The canonical instructions live in each box's AGENTS.md (rendered
   from `scripts/rescue-escalation-section.md.tpl`). Hard cap: **25 exchanges per
   client per day.**
2. **Relay (cloud).** The n8n "Rescue Rangers Relay" workflow authenticates the
   secret, runs the **Relay Brain** (validates the nine-field contract, routes
   `escalate | pending | answer | status`, holds the transport-buffer queue), posts
   the ticket to the Rescue Rangers HQ Telegram group (Fixer topic), and runs the
   return leg back to the client agent.
3. **Operator runtime (the brain).** Two transports on the operator Mac: a **push
   receiver** (over a dedicated Cloudflare tunnel) that runs ONE turn of the rescue
   agent per ticket, and a **pull poller** (cron) that drains pending tickets. A
   watchdog keeps the receiver alive with a bounded restart cap (anti-crash-loop).
4. **The department does its work** (see Section 4): triage → diagnose → structured
   fix (DRY-RUN then live, within a fix budget) → answer posted back through the
   relay → the client's own agent tells its owner the outcome (a/b/c).
5. **Durable record + board.** Every ticket is written to the SQLite ledger (system
   of record) and boarded on the Command Center Kanban, so the open-ticket, aging,
   and SLA views exist.

---

## 4. The Roles Inside This Department

Five seats, each with one job. The Dispatcher runs the show; the other four do the
hands-on work under dispatch.

| Role | What it is for |
| --- | --- |
| **Director of Rescue Rangers (Dispatcher)** | Triage, tier assignment, SLA ownership, the 25/day cap policy, and the when-to-page-a-human call. Owns the policy; drops no ticket. |
| **Diagnostician** | Evidence-first root-cause analysis. Names the failure class with proof (log line / config value / doc citation). Never guesses; cheap checks first. |
| **Structured-Fix Operator** | Applies the sanctioned `remediate.sh` fix for the diagnosed class, DRY-RUN first, live only on explicit opt-in, within the tier's fix budget. Refuses never-auto classes (credentials/DNS/deletion/model-sovereignty). |
| **Ticket Clerk** | Owns the durable ledger, the Command Center board sync, the aging/SLA sweep, and the weekly digest. Every ticket leaves a durable trace. |
| **QC / Postmortem Specialist** | Turns every P1 and 3-strike ticket into fleet prevention — a Skill-61 fix-class proposal or a repo issue — and audits that answers were correct and actually delivered. |

---

## 5. What Comes Back (the outcome contract)

Every rescue ends with the **client's own agent** telling its owner one of exactly
three things (never leaving the owner in the dark):
- **(a) We solved it** — what was fixed and confirmation normal operation is back.
- **(b) Here is what you should do** — the actionable next step the owner must take.
- **(c) Here is the answer** — the informational response relayed verbatim.

A ticket answered in the operator group but never returned to the client agent is an
**incomplete dispatch** — the department chases the return leg (which is exactly why
the VPS-safe `status`-poll return leg exists).

---

## 6. Tools This Department Operates

See `TOOLS.md` for the full inventory. In brief: the n8n Relay + Relay Brain (with
the nine-field validation patch), the push receiver + pull poller + watchdog on the
operator Mac, the durable ledger (`rescue_ledger.py`), the Command Center board
caller (`rescue_cc_board.py`), the staticData migration (`migrate-rescue-staticdata.py`),
and the onboarding AGENTS.md stamper (`stamp-rescue-escalation-section.sh`).

---

## 7. Quick Questions (operator)

- "What is the state of the rescue queue?" → Ticket Clerk: `rescue_ledger.py digest`.
- "Is client X at the daily cap?" → `rescue_ledger.py count-today --client X`.
- "What is aging past SLA?" → `rescue_ledger.py aging --older-than-minutes N`.
- "Did this ticket's answer reach the client?" → check `return_delivered` on the row.

---

*This department is operator-only fleet infrastructure. It is generated for
{{COMPANY_NAME}} by the AI Workforce Blueprint (Skill 23) and is never surfaced in a
client's intent-routing catalog.*
