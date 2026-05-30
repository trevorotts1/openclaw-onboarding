# Aggression Detection Protocol (F50) — Step 9.37

This protocol **extends** the bot/abuse safeguard family in
`protocols/conversational-safeguards.md`. It does NOT rebuild bot detection —
Safeguard 3 there already owns bot detection (now emitting `ZHC-bot-suspected`
going forward; see "Reuse" below). This protocol adds a **two-tier aggression
classifier** that runs PRE-routing, before any workflow match and before any LLM
spend, so a hostile inbound is caught and handled cheaply at the front door.

## Where it runs in the turn

AGENTS.md **Step 1.35** (inserted by `scripts/05-update-agents-md.sh`, marker
`STEP_1_35_AGGRESSION_PRE_ROUTING`) — AFTER the Step 0.7 compliance hard-gate and
the Step 1.4 safeguard check, but BEFORE Step 1.75 workflow match / routing and
BEFORE the agent spends a reply-drafting LLM call. The classifier itself is a
cheap keyword/pattern pass over the raw inbound text — it does not require a model call.

```
Step 0.5 quiet hours → Step 0.7 compliance → Step 1.4 safeguards (bot/paused)
   → Step 1.35 AGGRESSION (this protocol)  ← PRE-routing, pre-LLM-spend
   → Step 1.75 workflow match / routing → draft + send
```

## The two tiers

### Tier 1 — Tension (LOW)

Heightened attention; NO reroute. The customer is irritated but still engaging
in good faith. Signals (any of):

- **Multiple irritation words** in one message (e.g. "frustrated", "annoyed",
  "ridiculous", "fed up", "come on", "seriously", "ugh", "this is a joke").
- **Sustained irritation across 3+ consecutive messages** (read the conversation
  log — a rising-tone pattern over the last 3 inbounds, not just this one).
- **Emphatic punctuation**: `!!!` or `???` (repeated `!`/`?`).

On a Tier-1 firing:

1. Apply the tag `ZHC-tension-detected` to the contact (created programmatically
   → `ZHC-` prefix per zhc-tag-prefix-protocol.md).
2. Continue the NORMAL reply path (no reroute) but with **heightened attention**:
   slow down, acknowledge the frustration explicitly, lead with empathy, avoid
   anything that reads as dismissive or scripted.
3. Log the firing (see "Logging").
4. Do NOT notify the operator for Tier 1 alone (avoid alert fatigue).

### Tier 2 — Aggression (HIGH)

Route to the dedicated aggression-handler sub-flow and notify the operator.
Signals (any of):

- **Profanity directed AT the agent** (profanity + a direct address: "you", "your
  company", the agent's/brand's name) — profanity ABOUT a third party is not this.
- **Threats** — legal ("my lawyer", "I'll sue", "small claims"), physical, or
  public ("I'll post this everywhere", "blast you on social", "1-star review
  campaign", "report you to the BBB/FTC").
- **ALLCAPS + profanity + direct-address** in the same message.
- **3+ aggression signals in a single message** (any combination of the above).

On a Tier-2 firing:

1. Apply the tag `ZHC-aggression-detected`.
2. **Route to the aggression-handler workflow** — this is a DETOUR (F44 smart
   playbook switching, `smart-playbook-switching-protocol.md`): SAVE the current
   workflow state, hand the turn to the aggression-handler sub-flow (de-escalate,
   set boundaries, offer a human), and on resolution RETURN to the saved state
   (tag `ZHC-aggression-handled-and-resumed`) OR escalate to a human if
   unresolved. If no aggression-handler workflow is registered yet, fall back to:
   send a calm de-escalation holding reply and hand to the operator.
3. **Notify the operator** immediately (primary admin channel) with: contact name
   + ID, channel, the triggering message, and which signals fired.
4. Log the firing.

### CRITICAL — ALL CAPS ALONE does NOT fire

A message in all caps with NO profanity, NO threat, and NO other aggression
signal is **not** aggression — many people shout in caps when excited, on mobile
with caps-lock on, or out of habit. ALLCAPS only contributes when combined with
profanity + direct-address (a Tier-2 signal) or counts toward the 3+-signals
rule. On its own it fires neither tier.

## Severity is per-message, but tension can accumulate

The classifier reads the conversation log so a sustained 3+-message frustration
streak escalates Tier-1 even when no single message is loud. A single Tier-2
signal always wins over Tier-1.

## Reuse — bot detection is NOT rebuilt here

Bot detection already lives in `conversational-safeguards.md` Safeguard 3
(AGENTS.md Step 1.4, Step 9.5). This protocol does not touch that logic. The only
change is the **tag**: NEW bot-suspicion firings tag `ZHC-bot-suspected` (the
`ZHC-` namespace, per zhc-tag-prefix-protocol.md). The legacy `bot-detected` tag
is not migrated (the prefix rule is not retroactive); going forward the agent
creates and applies `ZHC-bot-suspected`.

## openclaw.json configuration

```jsonc
{
  "skill38": {
    "aggression_detection": {
      "enabled": true,                 // default true — on for every client
      "sensitivity": "standard"        // "lenient" | "standard" | "strict"
    }
  }
}
```

- **`enabled`** (default `true`) — master switch. If `false`, Step 1.35 is a no-op
  and the turn proceeds straight to routing.
- **`sensitivity`** (default `"standard"`) — tunes the firing thresholds:

| sensitivity | Tier 1 (tension) fires when… | Tier 2 (aggression) fires when… |
|---|---|---|
| `lenient`  | 2+ irritation words in one msg, OR `!!!`/`???` sustained over 4+ msgs | profanity-AT-agent + 1 more signal, OR an explicit threat, OR 4+ signals in one msg |
| `standard` | multiple irritation words in one msg, OR sustained irritation over 3+ msgs, OR `!!!`/`???` | profanity-AT-agent, OR a threat (legal/physical/public), OR ALLCAPS+profanity+direct-address, OR 3+ signals in one msg |
| `strict`   | a single irritation word, OR any `!`/`?` doubling | profanity-AT-agent, OR a threat, OR ALLCAPS+direct-address (even without profanity), OR 2+ signals in one msg |

Defaults documented so the operator can dial the classifier per their audience
(a B2B SaaS line may want `lenient`; a high-emotion support line may want
`strict`). ALL-CAPS-alone still never fires Tier 2 at any sensitivity.

## Logging (the data contract — F52)

Every firing (both tiers) is recorded in TWO places:

1. **Human-readable log** — appended to
   `<MASTER_FILES_DIR>/aggression-detection-log.md` with the firing, the tier,
   the signals, and the agent's reasoning (one short paragraph per firing).
2. **Structured JSONL** — one line appended to
   `<MASTER_FILES_DIR>/aggression-detection-log.jsonl`:

```json
{"timestamp":"2026-05-30T14:22:07Z","event_type":"aggression_detected","tier":2,"contact_id":"<CONTACT_ID>","channel":"sms","signals":["profanity_at_agent","threat_legal"],"tag_applied":"ZHC-aggression-detected","action":"route_aggression_handler","operator_notified":true,"sensitivity":"standard","reasoning":"profanity directed at the agent plus an explicit legal threat in one message"}
```

```json
{"timestamp":"2026-05-30T14:25:41Z","event_type":"tension_detected","tier":1,"contact_id":"<CONTACT_ID>","channel":"email","signals":["multiple_irritation_words","emphatic_punctuation"],"tag_applied":"ZHC-tension-detected","action":"heightened_attention","operator_notified":false,"sensitivity":"standard","reasoning":"two irritation words and repeated question marks; customer still engaging"}
```

JSONL schema (one object per line):

| field | type | meaning |
|---|---|---|
| `timestamp` | string (ISO-8601 UTC) | when the firing occurred |
| `event_type` | string | `tension_detected` (Tier 1) or `aggression_detected` (Tier 2) |
| `tier` | number | `1` or `2` |
| `contact_id` | string | GHL contact id |
| `channel` | string | inbound channel (sms/email/facebook/instagram/whatsapp/live_chat) |
| `signals` | array of string | which signals fired |
| `tag_applied` | string | `ZHC-tension-detected` / `ZHC-aggression-detected` |
| `action` | string | `heightened_attention` / `route_aggression_handler` |
| `operator_notified` | boolean | whether the operator was alerted |
| `sensitivity` | string | the configured sensitivity at firing time |
| `reasoning` | string | one-line natural-language justification |

The JSONL schema is also documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## Tags this protocol creates (all ZHC-prefixed, per MEMORY Rule 20)

- `ZHC-tension-detected` (Tier 1)
- `ZHC-aggression-detected` (Tier 2)

Reuses existing bot detection's tag, now `ZHC-bot-suspected` going forward.

## Operator override

The operator can clear an aggression flag the same way as the other safeguards
(conversational-safeguards.md "Operator override"): edit the contact log header
to remove the `ZHC-aggression-detected` line, or tell the agent "resume contact
<id>". The agent updates the log accordingly.

## MEMORY.md (Rule 21)

A hostile message is screened BEFORE routing and BEFORE the model. Tension (irritation,
not abuse) heightens care without rerouting; aggression (profanity-at-agent, threats,
shouting-with-profanity) routes to the de-escalation handler and notifies the operator.
ALL CAPS alone is never aggression. See MEMORY Rule 21, appended by
`scripts/06-append-memory-rules.sh`.

## Cross-references

- Extends: `protocols/conversational-safeguards.md` (Safeguard family, Step 9.5).
- Routing detour mechanism: `protocols/smart-playbook-switching-protocol.md` (F44).
- Tag namespace: `protocols/zhc-tag-prefix-protocol.md`.
- AGENTS.md Step 1.35: `scripts/05-update-agents-md.sh` (marker `STEP_1_35_AGGRESSION_PRE_ROUTING`).
- INSTRUCTIONS.md Step 9.37.
