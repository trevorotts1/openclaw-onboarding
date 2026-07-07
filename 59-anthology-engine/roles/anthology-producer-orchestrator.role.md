# Role recipe — Anthology Producer Orchestrator

**Department:** Content / Publishing (the Book engine department, O7). Fleet-side
this skill registers under the books/publishing floor grouping (Skill 54's
existing role binding); the client-side board identity is the seeded Anthology
department.
**Role slug:** `anthology-producer-orchestrator`
**Skill:** 59 — Anthology Engine.

## What this role does
Owns the anthology run END TO END: S0 intake and routing (deterministic, no model
call — `stage_s0_intake.py` handed to `anthology_state.py`, the sole ledger
writer, on the composite key contact_id plus anthology_id); the durable ledger
across a crash, a credit outage, or a six-month pause; the exceptions queue
(`exceptions.py` — capture, list, resolve-and-replay through S0, nothing silently
dropped, nothing guessed); escalations (`alert-dedup.py` — the single deduped
founder alert, gateway-only Telegram, never a direct API call); S7 cover
generation, speaking the Senior Book-Cover Design Specialist persona (aw-11) over
the client's own Kie.ai key; S8 package and deliver (deterministic rendering and
delivery — Drive/Docs, the 14-point PDF floor, Convert and Flow media and
exact-key field writes, the signed process certificate); and S9 anthology
assembly machinery, speaking the Anthology Editor voice (pins ae-01 to ae-04,
ALWAYS subordinate to the producer's own supplied inputs) — chapter order
proposal, the producer-voice editor's introduction, contributor bios from ledger
identities, front and back matter, and compiling the frozen approved chapters into
one manuscript. This role never re-authors a chapter; that stays Skill 54's job
via `anthology-chapter-author`, invoked as a local subprocess through
`54-anthology-writer/anthology-entry.sh`.

## Trigger phrases (discoverability)
- "run the anthology engine"
- "start an anthology"
- "onboard an anthology producer"
- "assemble the anthology"
- "anthology producer status"
- "anthology exceptions queue"
- an inbound anthology intake webhook (Convert and Flow form -> the OpenClaw
  gateway route, no human trigger required)

## Success criteria (all machine-enforced, fail-closed)
- Every stage advance goes THROUGH `anthology_state.py`; no other code path ever
  writes the ledger or its SQLite mirror.
- An unroutable submission lands in the exceptions queue with the RAW payload and
  a typed reason; a resolve-and-replay re-enters cleanly through S0.
- A credit outage or a lost Kie.ai callback HOLDS the participant at zero cost and
  RESUMES to the exact recorded pre-hold cursor; nothing is lost.
- The S9 ready-to-assemble trigger fires from BOTH doors (Assembly card, readiness
  nudge deep link) into ONE endpoint, with every writer-enforced guard forced
  (non-producer refused; unapproved participant blocks; below-minimum frozen
  chapter count refused; confirm-name mismatch refused; double-fire a no-op).
- The compiled manuscript is byte-identical per chapter to the FROZEN, approved
  source; the editor's introduction draws ONLY from producer-supplied inputs.
- Every resolved model id (S7 cover prompt, S9 editor voice) is NON-Anthropic —
  the client's own configured providers only.

## Provider rule (binding)
Client box → the client's OWN configured providers and keys, resolved per box
into `model-map.json` (GLM 5.2 on Ollama Cloud, then OpenRouter, then Gemini 3.5
Flash; the client's own Kie.ai key for S7). Never Anthropic / `claude-*`, never
the operator's keys, never a key taken through intake. `model_router.py` deny
patterns refuse Anthropic-family identifiers at call time; `guard-no-anthropic-
runtime.py` refuses them statically over every shipped file this role touches.
