# Aggression Detection Protocol (F50) — Step 9.37

> **This EXTENDS the Conversational Safeguards family** (`conversational-safeguards.md`,
> Step 9.5). It does NOT replace the existing **bot-detection** (Safeguard 3) — bot
> detection stays exactly as-is, now tagging `ZHC-bot-suspected` going forward (per the
> ZHC tag-prefix rule, MEMORY Rule 20). Aggression detection is a NEW, parallel
> two-tier classifier that runs **PRE-routing** — before any workflow match, before any
> LLM spend (AGENTS.md Step 1.35). A hostile message must not burn a model call.

The agent classifies every inbound for hostility on a cheap, deterministic keyword/pattern
pass FIRST. Only if the message is benign does it proceed to routing and the model.

## When it runs

AGENTS.md **Step 1.35 — PRE-routing aggression scan**, after the safeguards check
(Step 1.4) and BEFORE workflow routing (Step 1.75) and BEFORE the model is invoked.
This ordering is deliberate: a Tier-2 hostile message is routed to the aggression handler
WITHOUT spending a reasoning call on a normal reply.

## The two tiers

### Tier 1 — TENSION (low severity)

The customer is irritated / frustrated but NOT abusive. Signals (the agent counts them):

- **Multiple irritation words** in one message ("annoyed", "frustrated", "ridiculous",
  "unacceptable", "fed up", "come on", "seriously", "this is a joke", "waste of time").
- **Sustained tone across 3+ consecutive messages** (rising frustration, terse replies,
  repeated complaints) — read the conversation log to confirm the streak.
- **Emphatic punctuation**: `!!!` or `???` (one or more clusters).

**Tier-1 firing rule:** fires when ANY ONE of the three signals is present
(multiple irritation words in a single message, OR a 3+ message frustration streak,
OR `!!!`/`???`).

**Tier-1 actions (NO reroute — keep helping, just more carefully):**

1. Apply the tag `ZHC-tension-detected` to the contact (GHL skill; per the ZHC
   tag-prefix rule the tag is created programmatically with the `ZHC-` prefix).
2. Heighten attention: the agent continues the CURRENT workflow/reply but with extra
   care — acknowledge the frustration, slow down, confirm understanding, avoid upsell.
3. Do NOT reroute. Do NOT notify the operator. Do NOT pause.
4. Log the firing + reasoning (which signal(s) fired) to the aggression log (below).

### Tier 2 — AGGRESSION (high severity)

The customer is hostile toward the agent or the business. Signals:

- **Profanity directed AT the agent / business** (profanity + a second-person address:
  "you people are…", "your company is…", "screw you", a slur aimed at the agent).
- **Threats** — legal ("I'll sue", "my lawyer", "report you to the FTC/BBB"),
  physical ("I'll come down there", any violence), or public ("I'll post this
  everywhere", "blast you on social", "1-star review bomb").
- **ALLCAPS + profanity + direct address** in the same message (shouting a hostile
  message at the agent).

**Tier-2 firing rule:** fires when ANY of the named Tier-2 signals is present, OR when
**3+ signals fire in a single message** (any mix of Tier-1 and Tier-2 signals reaching
a count of 3 in one message escalates straight to Tier 2).

> **ALL CAPS ALONE DOES NOT FIRE.** A message in all caps with no profanity, no threat,
> and no direct hostility is NOT aggression (some people just type in caps). All-caps is
> only a signal when combined with profanity AND direct address.

**Tier-2 actions:**

1. Apply the tag `ZHC-aggression-detected` to the contact (GHL skill, `ZHC-` prefix).
2. **Route to the `aggression-handler` workflow** (the de-escalation sub-flow). If the
   F44 interrupt layer is installed, this routes via DETOUR-AND-RETURN
   (`smart-playbook-switching-protocol.md`): save state → run the aggression handler →
   on resolution return with `ZHC-aggression-handled-and-resumed`. If F44 is not
   installed, route directly and hold the original topic in the conversation log.
3. **Notify the operator** via the configured operator-notify channel with: contact name
   + ID, channel, the triggering message verbatim, and which signals fired.
4. Do NOT match a sales/marketing workflow. Do NOT upsell. Do NOT argue back.
5. Log the firing + full reasoning to the aggression log (below).

## Severity is per-message, but tension can accumulate

The classifier reads the conversation log so a sustained 3+-message frustration streak
escalates Tier-1 even when no single message is loud. A single Tier-2 signal always wins
over Tier-1.

## openclaw.json toggles

```json
{
  "skill38": {
    "aggression_detection": {
      "enabled": true,
      "sensitivity": "standard"
    }
  }
}
```

- `aggression_detection.enabled` — default **true**. Universal default-on safeguard.
- `aggression_detection.sensitivity` — `lenient` | `standard` (default) | `strict`.
  Documented thresholds:
  - **lenient** — Tier 1 requires 2+ of its signals (not just 1); Tier 2 requires a named
    Tier-2 signal OR 4+ combined signals. Fewer false positives; for high-volume,
    rough-talking audiences.
  - **standard** (default) — the firing rules above (Tier 1 = any 1 signal; Tier 2 = any
    named signal OR 3+ combined).
  - **strict** — Tier 1 fires on a single irritation word; Tier 2 fires on profanity even
    without a direct address. For brands that want zero tolerance.

## Aggression log (dual: human-readable + JSONL data contract)

Every Tier-1 and Tier-2 firing is logged to BOTH:

1. **Human-readable:** `<MASTER_FILES_DIR>/aggression-detection-log.md` — a dated entry
   with the contact, tier, signals that fired, the agent's reasoning, and the action taken.
2. **Machine-readable JSONL** (F52 data contract):
   `<MASTER_FILES_DIR>/aggression-detection-log.jsonl` — one JSON object per line:

```json
{"timestamp":"2026-05-30T14:22:05Z","event_type":"aggression_detected","tier":2,"contact_id":"<contact_id>","channel":"sms","signals":["profanity_at_agent","threat_legal"],"sensitivity":"standard","reasoning":"profanity directed at agent plus legal threat in one message","action":"routed_to_aggression_handler;operator_notified;tag=ZHC-aggression-detected"}
```

Tier-1 example:

```json
{"timestamp":"2026-05-30T14:25:11Z","event_type":"tension_detected","tier":1,"contact_id":"<contact_id>","channel":"sms","signals":["multiple_irritation_words"],"sensitivity":"standard","reasoning":"three irritation words in one message, no profanity or threat","action":"heightened_attention;tag=ZHC-tension-detected"}
```

The JSONL schema is documented in `INSTRUCTIONS.md` (Phase 5 data contract table).

## Tags this protocol creates (all ZHC-prefixed, per MEMORY Rule 20)

- `ZHC-tension-detected` (Tier 1)
- `ZHC-aggression-detected` (Tier 2)

Reuses existing bot detection's tag, now `ZHC-bot-suspected` going forward.

## MEMORY.md (Rule 21)

A hostile message is screened BEFORE routing and BEFORE the model. Tension (irritation,
not abuse) heightens care without rerouting; aggression (profanity-at-agent, threats,
shouting-with-profanity) routes to the de-escalation handler and notifies the operator.
ALL CAPS alone is never aggression. See
`<MASTER_FILES_DIR>/aggression-detection-protocol.md`.
