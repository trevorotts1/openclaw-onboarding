# 🔴🔴🔴 NO-COMINGLING RULE — BINDING, NON-NEGOTIABLE, REPO-WIDE 🔴🔴🔴

> **This is a hard violation rule. It outranks convenience, speed, and "just for now."**
> It applies to EVERY agent, EVERY sub-agent, EVERY skill, EVERY install, EVERY build,
> and EVERY runtime action — at build time and forever after. There are NO exceptions.

---

## THE RULE

**EVERY client gets their OWN isolated resources. Period.**

Every client gets their **own**:

- **Notion** workspace / page tree
- **GoHighLevel (GHL)** location / sub-account
- **Google Drive / Google Workspace** folder and account
- **Telegram bot** (own token, own chat, own supergroup/Command Center topics)
- **Command Center** dashboard (own deployment, own URL, own CF Access app)
- **KIE / API keys** and every other API credential (OpenRouter, Ollama, Fish, Vercel, GitHub, etc.)
- **n8n** workflows, webhooks, and data stores
- **Workspace** folder, memory store, and core files
- **everything** — if it holds, routes, or represents a client's data or identity, it is theirs alone.

---

## WHAT IS FORBIDDEN

You **NEVER**:

- **Share** one client's resource with another client.
- **Reuse** a resource created for client A when working for client B.
- **Borrow** "temporarily" from another client's workspace, location, bot, key, or page.
- **Default to** another client's resource as a placeholder, scaffold, or example container.
- **Co-mingle** any client's data, files, credentials, contacts, or outputs with another client's.

Co-mingling client data or resources — for ANY reason, even briefly, even "just to test," even
"because the real one isn't ready yet" — is a **HARD VIOLATION**. Discard the work and redo it correctly.

---

## WHAT TO DO WHEN A RESOURCE DOES NOT EXIST YET

If a client does **not yet have** a given resource (no Notion page yet, no GHL location yet,
no Command Center yet, no API key yet):

### → **STOP and WAIT.**

- Do **NOT** substitute another client's resource as a placeholder.
- Do **NOT** point the work at a "generic" or "operator" workspace that actually belongs to a specific client.
- Do **NOT** invent or borrow a key/location/bot to "unblock" yourself.
- Surface the gap to the operator and **wait** until the client's own resource is provisioned.

A missing resource is a **blocker to escalate**, never a reason to co-mingle.

---

## WHY THIS RULE EXISTS

Every client is a separate business with separate data, separate customers, separate privacy
obligations, and separate trust. One client's data leaking into — or being managed inside —
another client's workspace is a confidentiality breach, a data-integrity breach, and a betrayal
of the done-for-you promise. There is no "small" co-mingling. The blast radius is the whole
client relationship.

**Real incident this rule codifies:** an operator's named workspace (e.g. a Notion workspace that
belongs to a *specific* client) was treated as a generic "operator workspace" and another client's
reference material was placed inside it. That is co-mingling. It is exactly what this rule forbids.

---

## WHERE THIS RULE IS ENFORCED / REFERENCED

- **`AGENTS.md`** (master template) — the binding block is injected at the very top so it is
  impossible to miss at build time.
- **Skill 23 — AI Workforce Blueprint** (`23-ai-workforce-blueprint/SKILL.md`) — references this rule;
  the workforce build provisions each client's OWN departments/workspace, never shared.
- **Skill 32 — Command Center Setup** (`32-command-center-setup/SKILL.md`) — references this rule;
  each client gets their OWN Command Center deployment, Telegram bot, and dashboard URL.
- Every skill that touches a client resource (Notion, GHL, Drive, Telegram, KIE, n8n, keys)
  inherits this rule via `AGENTS.md`.

**If you are an agent reading this: you have now read the rule. You cannot claim you did not know.**
