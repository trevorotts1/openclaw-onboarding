# Anthology Engine -- REPAIRS register (KEEP / REPAIR / DROP)

The faithful-or-repaired defect register for the legacy n8n anthology stack (PRD
Section 9 gap register plus SPEC Section 5 node mapping). Each row records how a
legacy behavior was carried forward (KEEP), corrected (REPAIR), or removed (DROP),
and which engine gate now enforces it. The legacy n8n stack stays ALIVE and
UNTOUCHED until the retirement criteria pass AND the operator OKs; the engine edits
no legacy workflow and ships no bridge or migration tooling.

| # | Legacy behavior | Disposition | Enforced by |
|---|---|---|---|
| D1 | Four largest prompts existed only inside the JSON exports (truncation risk) | REPAIR -- ingested verbatim at Wave 0, sha256-pinned, zero truncation proven by byte count | guard-prompt-pins.py (AF-AE-PROMPT-PIN) |
| D2 | Book-to-HTML formatter carried 10 literal [UNCHANGED] placeholders | REPAIR -- full text restored from the CSV HTML Book record before pinning; a pin containing [UNCHANGED] hard-fails; content rules distilled into the deterministic house templates | guard-prompt-pins.py + config/pdf-house-style |
| D3 | Live keys in the exports (an image-API Authorization header; a routing key in customData) | REPAIR -- both keys rotated at Wave 0; the payload-carried key re-homed as an ENV credential by label; the nine JSONs never committed; a merge-gate export scan | AF-AE-EXPORT-LEAK + caf_credential_gate.py |
| D4 | Write Chapter word-count contradiction across sources | REPAIR -- normalized to 2,000 to 3,500 MEASURED words everywhere | prove_aw_chapter.py (AF-AE-CHAP-BAND) |
| D5 | Make.com and n8n variable syntax inside prompt bodies | REPAIR -- deterministic mapping to canonical field names; the composer refuses any unresolved slot | AF-AE-SLOT-UNRESOLVED |
| D6 | Brief ordered a from-scratch skill and a BookWriter deprecation | REPAIR -- Skill 54 promoted to the authoring core and extended; Skill 53 untouched; both are scored build failures if violated | Skill 53 untouched check + no-duplicate-anthology-skill scan |
| D7 | One fragile blocking execution (45-day sendAndWait, zombie waits, credit deaths) | REPAIR -- durable ledger; idempotent one-stage jobs; fallback chain; hold-and-resume; alert dedup | anthology_state.py + hold_queue.py + alert-dedup.py (AF-AE-CREDIT-HOLD) |
| D8 | Hardcoded test inbox receiving real participants' forms | REPAIR -- no literal recipient exists anywhere; recipients resolve from the ledger row | nudge_send.py (ledger-resolved recipient) |
| D9 | Single-client hardcoding (pipeline and stage identifiers in nodes) | REPAIR -- the registry binds per anthology per client at provisioning; the standard pipeline must pre-exist (snapshot-shipped or hand-built in the UI) and is found-and-bound BY NAME with the client's own token, STOPPING with AF-AE-PIPELINE-UI-CREATE if absent | anthology_registry.py + provision-anthology-client.sh |
| D10 | Opportunity lookup race (getAll limit 1) | REPAIR -- contact_id keying everywhere; no opportunity list-then-filter | intake_router.py + anthology_state.py |
| D11 | One-shot rewrite; duplicated branches | REPAIR -- rewrite budget 2 with gate re-entry; a single code path per stage | qc-strike-gate.py (AF-AE-REWRITE-BUDGET) |
| D12 | Manual outline re-upload | DROP -- deleted; the ledger carries the approved outline forward; a static route check proves no upload path exists | S4 gate contract |
| D13 | No anthology-level product | REPAIR -- stage S9 assembly plus the Assembly card and the producer trigger | stage_s9_assembly.py + anthology_state.py (AF-AE-S9-GUARD) |
| D14 | Skill 53 cards to a never-seeded books department (CEO catch-all) | REPAIR -- the engine SEEDS its own Anthology department first, idempotent, verified by reading it back | provision-anthology-client.sh (department seed) |
| D15 | No participant-facing surface in the Command Center | REPAIR -- a new token-scoped public route; foreign, expired, and replayed tokens refused | gate_engine.py (AF-AE-TOKEN-REFUSED) |
| D16 | Five HTML-formatter LLM calls | DROP -- formatting is deterministic Python; there is NO formatter model tier | config/pdf-house-style + guard-font-floor.py |
| D17 | The cover render on a 16:9 presentation recipe with a literal key | REPAIR -- the client's own Kie.ai GPT-image-2 PORTRAIT 1024x1536 via the verified text-to-image portrait endpoint through Skills 07 and 46; the literal-header class forbidden | cover_render.py + caf_credential_gate.py |

## Source gaps carried forward (recorded, not invented)

- G1 -- WEB SEARCH: Avatar Questions 31 and 32 use the auto-detected client search
  tool (Perplexity preferred). Absent a tool the run CONTINUES with an honest
  limitation note and ONE deduped founder flag; fabricated links are refused by Gate
  B Tier 1. Enforced by `search_detect.py` and `qc-tier1-anthology.py`.
- G2 -- LONG CONTEXT: the S9 whole-manuscript compile uses the optional 1M-context
  tier ONLY when the client configured a key; otherwise it chunks on HEAVY-WRITER.
- G3 -- LEGACY RECONCILIATION: out of core scope. The only sanctioned path is a
  manual operator-initiated entry through the exceptions queue (reason
  legacy_reconciliation); no bridge or migration tooling ships.

## Change discipline

Editing any gate is a four-step change: add the gate and its AF-AE code to
`ENGINE-MANIFEST.json`, add or adjust the enforcing script, add a golden and attack
fixture, and record the disposition here.
