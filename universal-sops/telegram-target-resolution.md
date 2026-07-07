# Telegram Target Resolution — A Send Goes To A chat_id, Never A Phone Number
**Version:** 1.0 | 2026-07-07
**Applies to:** Master Orchestrator / CEO Agent AND every Department Director + specialist that sends Telegram messages (Communications owns messaging sends; all installs, Mac and VPS)
**Status:** CANONICAL, fleet standard
**Owning department:** Communications
**Runtime resolver:** `shared-utils/resolve-client-chat-id.sh`

---

## Why this SOP exists

A Telegram bot can deliver a message ONLY to a numeric Telegram **chat_id**
(shape `/^-?\d+$/`). The Bot API has **no** phone-number-to-chat lookup: there is
no endpoint that turns `+15551234567` into a chat_id. A phone number is therefore
**never** a valid Telegram send target, no matter how correct the number is.

This rule exists because a send target was, in practice, sometimes taken from a
CRM contact's **phone** field and handed to a Telegram send. That can never
deliver, and a blind retry just burns attempts. The fix is to resolve the correct
numeric chat_id from the fleet's OWN registry **before** the send, and to escalate
(not guess) when no chat_id is on file.

---

## The doctrine (binding)

1. **A Telegram send target is a numeric chat_id, full stop.** It matches
   `/^-?\d+$/`. Anything else — a phone number, an email, a contact name — is the
   WRONG TYPE and must never be passed to a Telegram send.

2. **Never pass a phone number as a Telegram target.** Not an E.164 number (e.g.
   `+15551234567`), not a CRM contact's `phone` field, not any dialable string.
   A phone number is not a fallback for a missing chat_id — it is a different
   thing entirely.

3. **Resolve the chat_id from the fleet registry FIRST.** BEFORE any send, and
   BEFORE any CRM-phone-number consideration, resolve the numeric chat_id from the
   fleet's own registry:

   ```
   shared-utils/resolve-client-chat-id.sh "<client name>"
   ```

   On a single confident, valid match it prints the numeric chat_id to stdout and
   exits 0 (for a synthetic example roster entry
   `{"client":"Wibble Widgets","chatId":"1234567890"}` it prints `1234567890`).
   On any miss it prints nothing to stdout and exits non-zero
   (`1` not found / unconfirmed, `2` ambiguous, `3` roster not found, `4` usage).
   The registry holds real chat ids and lives only on the operator box
   (`$HOME/clawd/fleet-prover/fleet-roster.json`); the resolver reads it at
   runtime and never ships those values in this repo.

4. **No chat_id found => BLOCKED + escalate, never a wrong-type send.** If the
   resolver returns empty / non-zero (unknown client, `chatId` still
   `unconfirmed`/`TBD`, or the roster is unavailable), the send has NO valid
   target. Do NOT substitute a phone number or any other value. Follow the
   Blocked-vs-Return doctrine
   (`23-ai-workforce-blueprint/master-orchestrator-dept/SOP-01-Blocked-vs-Return.md`):
   the worker hands the task back to the orchestrator (status=backlog with a
   structured note); the orchestrator, after the four-way test, marks it
   **BLOCKED** on a human — the operator confirms or supplies the client's chat_id
   — and escalates immediately. A missing chat_id is a
   credential/access item, not an agent-fixable error, and not grounds to send to
   the wrong target.

5. **The core error is a backstop, not the gate.** The OpenClaw core now returns
   an actionable error when a phone number is passed to a Telegram send, so a
   blind retry is caught rather than silently dropped. That backstop does NOT
   replace this SOP: the resolution in Rule 3 must happen BEFORE the send. Relying
   on the core error means the wrong target already reached the send path — the
   whole point here is to resolve the right chat_id first so it never does.

---

## Where this is wired

- **Runtime resolver:** `shared-utils/resolve-client-chat-id.sh` — reads the fleet
  registry at `$OPENCLAW_FLEET_ROSTER` -> `$HOME/clawd/fleet-prover/fleet-roster.json`
  -> `/data/clawd/fleet-prover/fleet-roster.json`, matches the client name, and
  prints only a valid numeric chat_id (empty + non-zero on any miss). Companion to
  `shared-utils/resolve-owner-chat.sh` and `shared-utils/operator-chat-id.sh`.
- **Owner-facing pointer:** the Communications department guide
  (`23-ai-workforce-blueprint/templates/role-library/communications/how-to-use-this-department.md`)
  carries a short "messages go to a chat ID, never a phone number" section that
  points back at this SOP and the resolver.
- **Blocked-vs-Return:**
  `23-ai-workforce-blueprint/master-orchestrator-dept/SOP-01-Blocked-vs-Return.md`
  governs the escalation path when no chat_id resolves.

---

*This SOP is the human-readable doctrine; the runtime truth is the fleet registry,
read only on the operator box by `resolve-client-chat-id.sh`. Resolve the numeric
chat_id first; if none is on file, block and escalate — never send a Telegram
message to a phone number or any other wrong-type target. Examples here use ONLY
the sanctioned placeholder `1234567890` and synthetic names.*
