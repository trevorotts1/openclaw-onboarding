<!-- OPERATOR HEADER (5 lines) — DO NOT EDIT BELOW -->
<!-- Source: openclaw-cloudflare-tunnel-prompt (1).md v5.14 — lines 1804-1993 (verbatim) -->
<!-- Section: Step 9.4 — Install Conversation Log Protocol, PLUS preferred_language header field per Step 9.10.B -->
<!-- ONLY ADDITION to the verbatim source: one `Preferred language:` line inserted into the File Anatomy header block. -->
<!-- Patch source: skill-38-patch-1 agent — 2026-05-28 -->

# Conversation Log Protocol

This document defines the rules for logging, summarizing, and purging
customer conversation history. The agent reads this on every reply turn
to know what to do.

## Folder structure

- Location: `<MASTER_FILES_DIR>/conversational-logs/`
- One file per contact: `<contact_id>__<sanitized_name>.md`
- Sanitize name: replace spaces with underscores, strip any character
  that isn't alphanumeric, underscore, or hyphen.

## File anatomy

Each contact's log file has this structure, top to bottom:

```
# Conversation Log — <Full Name>
Contact ID: <id>
First contact: <ISO date>
Last activity: <ISO date>
Preferred language: <BCP-47 code, e.g. en, es, fr-CA — populated on first contact per Step 9.10 multi-language detection. The agent reads this on every reply turn so a returning customer keeps getting replies in the language they originally wrote in.>

## Historical Summary (older than 14 days)
[Rolled-up summaries of all activity older than 14 days. Never deleted.
Each summary entry is dated and concise — 1-3 sentences capturing what
was discussed, what was decided, what's pending.]

## Daily Summaries (3 to 14 days ago)
[Per-day rollups for the 3-to-14-day window. Each entry dated. Written
by the 11:30 PM cron job once activity has aged out of the 72-hour
verbatim window.]

## Verbatim — Last 72 Hours
[Full back-and-forth in this active conversation window. Each entry has
timestamp, channel, direction (customer/agent), and the exact text.]
```

## Logging rules (real-time, on every reply turn)

When the agent processes an inbound webhook AND decides to reply (passes
the classification filter in AGENTS.md):

1. Compute the log file path: `<MASTER_FILES_DIR>/conversational-logs/<contact_id>__<sanitized_name>.md`

2. If the file does not exist, create it with the header section
   (Contact ID, First contact date, empty Historical Summary, empty
   Daily Summaries, empty Verbatim section).

3. Append TWO entries to the "Verbatim — Last 72 Hours" section:
   - The customer's inbound message (timestamp, channel, "customer →
     agent", full text)
   - The agent's outbound reply (timestamp, channel, "agent → customer",
     full text)

4. Update the "Last activity" date in the header.

5. Before drafting the reply, read the ENTIRE log file (Historical
   Summary + Daily Summaries + Verbatim) to inform the response. A
   returning customer should feel recognized: "Good to hear from you
   again, Sarah — did the consultation we discussed last month work
   out?"

## Daily summarization (11:30 PM nightly via OpenClaw cron)

A scheduled job runs every night at 11:30 PM local time. For each file in
`conversational-logs/`:

1. Find any verbatim entries older than 72 hours (3 days) from current
   time.

2. Group those entries by calendar day.

3. For each day with verbatim entries past the 72-hour cutoff:
   - Generate a short summary (2-5 sentences) capturing: what the
     customer asked, what the agent said, any commitments made (e.g.,
     "agent promised follow-up Tuesday"), and any unresolved items.
   - Append the summary to the "Daily Summaries (3 to 14 days ago)"
     section with the day's date.
   - Delete the corresponding verbatim entries from the "Verbatim —
     Last 72 Hours" section.

4. Find any daily summary entries older than 14 days from current time.
   For each:
   - Append them to "Historical Summary (older than 14 days)" as-is
     (they're already summarized).
   - Delete them from "Daily Summaries (3 to 14 days ago)".

5. Find any daily summary entries (now in Historical Summary) older than
   90 days. These stay forever — they ARE the long-term memory. Only
   verbatim entries get truly deleted (after the 72-hour cutoff during
   summarization). Daily summaries promote to historical and persist.

## Cron job definition

Add this to OpenClaw's cron configuration so the daily summarization
runs automatically:

```json
{
  "cron": {
    "jobs": [
      {
        "id": "conversation-log-summarizer",
        "schedule": "30 23 * * *",
        "agentId": "<ROUTING_AGENT_ID>",
        "message": "Run the daily conversation log summarization per the protocol at <MASTER_FILES_DIR>/conversation-log-protocol.md. Process every file in <MASTER_FILES_DIR>/conversational-logs/. Apply the 72-hour, 14-day, and 90-day retention rules. Report a brief summary of what was processed."
      }
    ]
  }
}
```

## Safety rules

- Never delete the Historical Summary section. Those entries persist
  forever.
- Never delete a daily summary before it has spent its full 11-day window
  in the Daily Summaries section.
- Never modify a daily summary once written (append-only history).
- Verbatim entries older than 72 hours are deleted ONLY after they have
  been successfully rolled up into a daily summary in the same run.
- If the agent crashes mid-summarization, the next 11:30 PM run will
  pick up where it left off (the rules are idempotent — running the
  same logic twice produces the same result).
```

### C. Update AGENTS.md to reference the conversation log protocol

Locate the "Inbound Webhook Message Classification" section in AGENTS.md (added in Step 7). Insert this new sub-section right after Step 1 (Classify before replying) so the agent reads the log BEFORE drafting any reply:

```markdown
### Step 1.5 — Read the contact's conversation log for continuity

Before drafting a reply, read the conversation log for this contact at:

  <MASTER_FILES_DIR>/conversational-logs/<contact_id>__<name>.md

The file contains the customer's full history: a historical summary, daily
summaries from the past 3-14 days, and verbatim back-and-forth from the
last 72 hours.

If the file exists: use the context. Recognize the customer, reference
prior conversations naturally, follow up on open items.

If the file does NOT exist: this is the first contact. Greet them
appropriately and the log file will be created when you log this turn.

After drafting your reply AND sending it via the GHL skill, append both
the inbound and outbound messages to the log file per the full protocol at:

  <MASTER_FILES_DIR>/conversation-log-protocol.md
```

### D. Schedule the daily summarization cron job

Add the cron entry to `~/.openclaw/openclaw.json` (the cron config block, not the hooks block). Use the existing Backup Protocol fallback before editing. If the cron block doesn't exist, create it:

```json
{
  "cron": {
    "enabled": true,
    "jobs": [
      {
        "id": "conversation-log-summarizer",
        "schedule": "30 23 * * *",
        "agentId": "<ROUTING_AGENT_ID>",
        "message": "Run the daily conversation log summarization per the protocol at <MASTER_FILES_DIR>/conversation-log-protocol.md. Process every file in <MASTER_FILES_DIR>/conversational-logs/. Apply the 72-hour, 14-day, and 90-day retention rules. Report a brief summary of what was processed."
      }
    ]
  }
}
```

Validate the config and confirm the cron job appears in `openclaw status`:

```bash
openclaw config validate
openclaw cron list | grep conversation-log-summarizer
```

### E. Tell the operator what was set up

Add to the Client Reference Sheet and the final chat summary:

- Folder: `<MASTER_FILES_DIR>/conversational-logs/`
- Protocol: `<MASTER_FILES_DIR>/conversation-log-protocol.md`
- Cron: runs nightly at 11:30 PM
- Retention: 72 hours verbatim → 14 days daily summary → 90 days historical summary (summaries kept forever)
