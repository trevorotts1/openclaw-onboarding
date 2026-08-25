# Book Writer — REPAIRS (porting decision register)

Seeded from PRD §15 (`projects/Book-Writer-Skill/PRD/PRD.md`), source-cited. Each row is a source
behavior/anomaly and the decision the skill implements. `--strict-source` on the foreman documents any
divergence at runtime.

| # | Source behavior / anomaly (cite) | Decision |
|---|---|---|
| 1 | Airtable prompt library — 3 tables, ~40 fetches/run (ANALYSIS §1.1) | BAKE as versioned `prompts/<stage>/` assets; Airtable dies. |
| 2 | LLM-chain + HTTP-twin `\|\|` fallback pairs (ANALYSIS §1.2, §9.7) | COLLAPSE to one call per stage; orphan twins (Title/Chapter agents) DROP. |
| 3 | HTML→Google-Doc 5-node chains ×~10 (ANALYSIS §1.3) | REPLACE with markdown artifacts + deterministic assembly/PDF; the 50+-readability personas → the pinned `assets/print-style.css`. |
| 4 | Gmail `sendAndWait` gates — titles/outline/approve/updates ×2 (ANALYSIS §1.4) | REPLACE with in-chat checkpoints (GATE-1/2/3/4), exact order preserved + gate receipts. |
| 5 | Sequential chapter batches with prior-chapter injection (§5.4) | PRESERVE exactly (no parallel flag) + `AF-BK-CONTINUITY` proves the injection happened. |
| 6 | Personal-stories verbatim placement mandate ("we must use it for sure") | PRESERVE + `AF-BK-STORIES` enforces intake → outline → manuscript. |
| 7 | Anthology GHL opportunity pipeline | OUT OF SCOPE here — anthology is the SEPARATE sibling **Skill 54**; ids preserved inert for a future Skill 44 hook; this skill never calls GHL. |
| 8 | Missing companion exports ("Avatar Agent", "Single Chapter Cover Image Gen") (ANALYSIS §4) | RECONSTRUCT: the AVATAR-ANALYST role IS the monolith's Phase B; the cover is stages 22–23. Source exports requested P2. |
| 9 | Google Slides template population (4x3x3) (ANALYSIS §3.4) | REPLACE with schema-valid `433_Deck_Data.json` + deck outline → **Skill 51**. |
| 10 | `gpt-4o-search-preview` web research (stage 02) | REPLACE with the client's search path + a `degraded:search` receipt if the box has no search (never silent fabrication). |
| 11 | OpenAI image cover | client IMAGE tier; `degraded:image` receipt + always-delivered prompt file if absent (the book still ships). |
| 12 | Client names in source workflow titles / raw pinned data | NEVER carried over; `prove_bw_anon.py` in CI + delivery; raw exports are SOURCE-ONLY. |
| 13 | Trailing-space webhook keys / misspellings (`firstname `, `Idealavatar `, `Stories_quotes_facts `) | DIE at the G0 normalization boundary; never reach a prompt. |
| 14 | Slack ops notifications + hardcoded channel | DROP (gateway-only notification posture); the source's Slack posts die here. |

## Reconstruction flags (P2 fidelity)

- **"Avatar Agent"** standalone export absent from the 8 digests — reconstructed from monolith Phase B
  (role AVATAR-ANALYST). Request the original export as a P2 check.
- **"Single Chapter Cover Image Gen"** referenced by `executeWorkflow` but absent — covered by stages
  22–23. Request the original export as a P2 check.
