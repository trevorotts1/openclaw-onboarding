# SOP-DIU-606 — Semantic Style Retrieval & Dedupe Index

**ID:** SOP-DIU-606
**Classification:** ZHC SOP — thin wrapper
**Owner Role:** Style Analyst (Registrar duty; formalizes base plan E.5.2)
**Section 9 slot:** 9.4
**Version:** 1.0 | **Date:** 2026-06-12
**Status:** CANONICAL
**Library-version pin:** MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0 (§-refs verified 2026-06-12)

---

## Role Mission

The Style Analyst runs this SOP to make the growing card library semantically findable — answering "do we already have a card like this?" before any new analysis is commissioned — and to enforce a dedupe gate that prevents near-duplicate cards from fragmenting the library into an unmanageable sprawl. On every card registration or version bump, the Analyst embeds the card's summary, mood, and palette via the fleet-standard embedding engine and stores the result in the vector index. Fuzzy and natural-language lookup requests resolve to a ranked shortlist that the CDO or requesting role confirms before any generation fires. The embedding index is strictly derived and rebuildable from the card files; INDEX.md is the sole authority on what cards exist and at what status. No generation fires from an embedding match alone — retrieval is a hint, not a route. This SOP also owns the mechanical Registrar activation counter: the Analyst counts production cards on each registration, and once the count reaches or exceeds 50 it raises a CDO activation ticket for the Library Registrar role.

---

## Governing Library Files (source-of-truth — do NOT duplicate content)

| File | Sections used | What it governs |
|---|---|---|
| `_system/INDEX.md` | Registration rules header; status column definitions; retire-never-delete rule | Authority rule: INDEX.md is the single source of truth for card existence and status; the embedding index is a derived layer |
| `_system/STYLE-CARD-TEMPLATE.md` | §1 (Summary field — one-line card description); §11 (Mood/Energy Keywords field); §4 (Color Palette table, Palette Notes column) | Which fields feed the embed payload; field naming and location |
| `_system/MASTER-SOP.md` | §6 steps 6–7 (card registration in Workflow A context); §3.2 (variable system) | Where in the card-creation workflow this SOP is invoked; registration order |
| `shared-utils/embedding_engine.py` | Full file (pinned to gemini-embedding-2 @3072) | Embedding call interface; model pin enforcement; vector storage contract |

All embedding calls go through `shared-utils/embedding_engine.py`. Do not call gemini-embedding-2 directly — the engine enforces the model pin and the 3,072-dimension contract. The `gemini-embedding-001` slug is hard-forbidden (EOL shutdown 2026-07-14); the engine rejects it at the call site.

---

## Procedure (ordered)

### A. Embedding a Card (on registration or version bump)

1. **Extract the embed payload.** Pull three fields from the card file:
   - STYLE-CARD-TEMPLATE §1 Summary field — one-line description of the style
   - STYLE-CARD-TEMPLATE §11 Mood/Energy Keywords field — keyword list
   - STYLE-CARD-TEMPLATE §4 Color Palette table, Palette Notes column text

   Concatenate into a single text block. Target length: 200–600 characters. Do not truncate to fit this target — if the concatenated payload exceeds 600 characters, return to the card author to trim the Palette Notes column; do not silently shorten the payload.

2. **Include thumbnail if available.** If a stored source thumbnail or the card's winning test image exists on disk at `_local/results/{job-id}/` or `_local/references/`, include it as the multimodal input to the embedding engine. If no image is available, text-only embedding is acceptable. Record which input type was used (`text_only` or `multimodal`) in the embedding entry.

3. **Call the embedding engine.** Invoke `shared-utils/embedding_engine.py` with the text payload (and optional image path). The engine calls `gemini-embedding-2` @3072. Record the returned values:
   - `vector` — the 3,072-dimension float array
   - `checksum` — sha256 of the vector bytes
   - `model_id` — must be `gemini-embedding-2`; abort if any other model ID is returned
   - `dimensions` — must be 3072; abort if different
   - `run_date` — ISO 8601
   - `input_type` — `text_only` or `multimodal`

4. **Write the embedding entry.** Store: `{card_id: {vector, checksum, model_id, dimensions, run_date, card_version, input_type}}` in the index store. Update the index manifest's `coverage_count` and `last_run_date`.

5. **Record the checksum in the receipt file.** Write `embedding_checksum` to the card's per-card receipt file at `_local/receipts/{card-id}.json`. This enables the Healer-Graphics SOP-DIU-615 sweep to verify coverage without recomputing embeddings.

6. **Increment the Registrar counter.** Update the running count of tested + production cards in the INDEX.md summary header. If the new count is >= 50, immediately proceed to step 7; otherwise this step completes the embedding flow.

7. **Registrar activation ticket (when count >= 50).** Raise a CDO ticket: "Library Registrar activation threshold reached ([N] tested+production cards). Per SOP-DIU-606 step A.7, the Library Registrar role is eligible for activation. Please schedule `add-role.sh --dept graphics --role 'Library Registrar'` and confirm INDEX write ownership transfer." Do not activate the role or transfer INDEX ownership without CDO confirmation.

### B. Dedupe Gate (before ID assignment on new card)

Run this gate BEFORE assigning a card ID. Do not skip it when INDEX is empty — an empty result is a valid clean result.

1. **Compute the candidate embed payload** using the same three-field extraction in step A.1 above. If the card is in early draft and §11 or §4 are not yet filled, defer the gate until those fields are complete. Do not run dedupe on an incomplete payload.

2. **Query the index for top-5 nearest neighbors** (production + tested + draft statuses included; retired excluded). Use cosine similarity.

3. **Apply the score thresholds:**
   - **Score >= 0.92:** HALT. Do not assign a card ID. Flag to CDO with the full similarity report: "Candidate card resembles [CARD-ID] (similarity: X.XX, status: [STATUS]). Options: (a) version bump the existing card; (b) register as a sibling with cross-links; (c) proceed as independent card with written rationale. Decision required before ID assignment." Do not proceed without a written CDO decision.
   - **Score 0.80–0.91:** Proceed to registration with mandatory sibling cross-links. Add a `sibling_cards: [{id, similarity_score}]` entry in the new card's Model Notes section and in each matched card's Model Notes section. Record the scores in the new card's receipt file.
   - **Score < 0.80 (or index empty):** Proceed to registration without flags.

4. **Record dedupe scores in the receipt file.** Whether flagged or clean, write `dedupe_scores: [{card_id, similarity_score}]` (top-5 results) into the new card's receipt at `_local/receipts/{card-id}.json`. A receipt without this field means the gate did not run — the Healer-Graphics SOP-DIU-615 sweep treats it as a coverage gap.

### C. Style Lookup (fuzzy/NL/image query)

1. **Receive the lookup request.** Accept from: CDO, Generation Operator, Photo Shoot Director, or Brainstorming Buddy. Request form: free-text description, mood keywords, or an attached reference image.

2. **Compute the request embed.** Use the same embedding engine call (text or multimodal). Do not treat a lookup query as a card — no entry is written to the index.

3. **Query for top-3 nearest neighbors.** Default scope: production cards only. If the requester explicitly asks for historical or draft candidates, include tested and draft status rows. Never include retired cards in results without explicit instruction.

4. **Return the shortlist.** Format:
   ```
   [{card_id, card_name, category, status, similarity_score}]
   ```
   Prepend the mandatory disclaimer: "These are retrieval suggestions. INDEX.md is the authority. No generation should fire from this list without an INDEX-verified card ID confirmed by the CDO."

5. **Log the query.** Append a query log entry to `_local/index-query-log.md`: timestamp, requestor, query type (text/image/keywords), top-3 results with scores, requester-confirmed card ID (fill in after CDO responds, or leave null if no confirmation received).

### D. Coverage Check (weekly and on Healer trigger)

1. Count the number of card files in the library (all statuses except retired).
2. Count the number of embedding entries in the index with a non-null, non-PENDING checksum.
3. If coverage count < card count: identify the card IDs with missing or PENDING embeddings. Run step A (embedding flow) for each. Log the rebuild in `_local/index-manifest.json` under `rebuild_events`.
4. If the embedding engine is unavailable during the coverage check: do not block card operations. Mark affected cards as `embedding: PENDING` in their receipt files. The Healer-Graphics SOP-DIU-615 sweep surfaces PENDING entries.

---

## Inputs

| Input | Required | Source |
|---|---|---|
| Card file (draft or registered, all required fields complete) | Yes | Style Analyst (Workflow A analysis via SOP-DIU-101) |
| STYLE-CARD-TEMPLATE §1 Summary, §11 Mood/Energy Keywords, §4 Palette Notes | Yes | Must be filled in the card before this SOP runs |
| Stored thumbnail or winning test image (optional) | No | `_local/results/{job-id}/` or `_local/references/` — text-only embedding if absent |
| `shared-utils/embedding_engine.py` (pinned gemini-embedding-2 @3072) | Yes | Fleet shared utility |
| Per-card receipt file at `_local/receipts/{card-id}.json` | Yes | Created by SOP-DIU-101 at draft emission; must exist before this SOP writes to it |
| INDEX.md current state (for coverage check and Registrar counter) | Yes | `_system/INDEX.md` |
| Lookup request (text/keywords/image) | Conditional | CDO, Generation Operator, Photo Shoot Director, or Brainstorming Buddy |

---

## Outputs

| Output | Location | State at exit |
|---|---|---|
| Embedding entry (on registration/re-embed) | Index store (vector DB or flat index file per install) | Written; `embedding_checksum` recorded in receipt |
| Updated index manifest | `_local/index-manifest.json` | `coverage_count` and `last_run_date` updated |
| Dedupe verdict with similarity scores | Returned to caller (CDO or card author) + written to receipt | Pass or HALT with scored shortlist |
| Sibling cross-links (score 0.80–0.91) | Added to new card's Model Notes + matched cards' Model Notes | Written in both card files |
| Lookup shortlist | Returned to requester | Labeled as hints only; requester must confirm via CDO |
| Query log entry | `_local/index-query-log.md` | Appended |
| Registrar activation ticket (when count >= 50) | CDO notification via `openclaw message send` | Sent; not self-executed |
| Coverage rebuild log (on gap detection) | `_local/index-manifest.json` under `rebuild_events` | Appended |

---

## Handoff Conditions

- **Card embedding complete (step A):** Proceed to INDEX.md row write (SOP-DIU-502 / SOP 9.3). The embedding checksum is available in the receipt. Do not write the INDEX row before the embedding is recorded unless the engine is unavailable (PENDING path — see below).
- **Dedupe gate — clean (score < 0.80):** Card proceeds to ID assignment and registration. Dedupe scores recorded in receipt.
- **Dedupe gate — sibling flag (0.80–0.91):** Card proceeds to registration with cross-links applied to both cards. CDO does not need to approve; Analyst applies the links and records the scores.
- **Dedupe gate — halt (>= 0.92):** Card ID assignment suspended. CDO receives the similarity report and makes the merge/sibling/independent decision. Analyst waits for a written CDO decision before proceeding.
- **Lookup query complete:** Shortlist returned to requester with mandatory hint disclaimer. CDO confirms the selected card ID. Generation Operator may not fire a generation from the shortlist without that confirmation.
- **Embedding engine unavailable:** Mark affected card receipts `embedding: PENDING`. Register the card in INDEX.md (do not block registration). Healer-Graphics SOP-DIU-615 sweep detects PENDING entries and triggers retry.
- **Registrar counter >= 50:** CDO activation ticket raised. Analyst continues executing this SOP until CDO confirms role activation and ownership transfer.

---

## Escalation Triggers

| Condition | Action |
|---|---|
| `gemini-embedding-001` slug returned or requested anywhere | Hard abort. Log the event. Never call this model — hard shutdown 2026-07-14. Route to CDO for engine investigation. |
| Embedding engine returns model_id != `gemini-embedding-2` or dimensions != 3072 | Hard abort. Do not store the vector. Escalate to CDO with the returned model_id and dimensions. This is a pin violation. |
| Embed payload concatenation exceeds 600 characters | Return to card author with specific field trimming instructions. Do not truncate silently. |
| Dedupe score >= 0.92 on candidate card | HALT ID assignment. Escalate to CDO with full scored shortlist and the three decision options. Do not proceed without written decision. |
| Per-card receipt file missing when this SOP is called | Do not proceed. Escalate: "Card [ID] has no receipt file at expected path. This SOP cannot write embedding checksum without a receipt. Please confirm whether card was properly emitted from SOP-DIU-101 step 6." |
| INDEX.md coverage count < card file count (persistent after retry) | Escalate to CDO with the list of cards with PENDING or missing embeddings. Do not silently carry PENDING status across multiple sweep cycles. |
| Registrar counter >= 50 | Raise CDO activation ticket immediately (same session). Do not wait for end-of-day log. |
| Index store write fails (filesystem or database error) | Hard stop embedding for this card. Mark receipt `embedding: FAILED`. Escalate to CDO. Do not mark the card registered in INDEX.md until the embedding path is restored. |
| Lookup returns a card ID not present in INDEX.md | Return an empty shortlist. Log: "Index entry exists without a corresponding INDEX.md row for [CARD-ID]. Possible stale index entry — flagging for Healer sweep." Notify CDO. |

---

*Library-version pin: MASTER-SOP v1.0, STYLE-CARD-TEMPLATE v1.0, INDEX.md v1.0 (§-refs verified 2026-06-12).*
