# REPAIRS — auditable, reversible source dispositions (R1–R7)

Every source anomaly is explicitly dispositioned (KEEP / REPAIR / DROP). The repairs R1–R6 are
**OFF BY DEFAULT** so a run is **FAITHFUL to Trevor's original LIVE Avatar Alchemist workflow output**.
They are applied only when the run opts in with **`aa_director.py --apply-repairs`** (or
`intake.apply_repairs=true`). Faithful-by-default, repaired-on-request — never silently changed.

> **R7 is different.** R7 (the Anthropic ban) is a client-path COMPLIANCE rule, not a fidelity
> repair. It is **ALWAYS enforced on every client box (`G-NOANTHROPIC`) and is NEVER reverted**,
> regardless of `--apply-repairs`. The client runtime is never Anthropic.

## How the gating works

- **Foreman** (`aa_director.py`): `--apply-repairs` (default OFF) records the mode in
  `RUN-LEDGER.json` and prepends a **mode banner** to every dispatched stage — the banner tells the
  sub-agent to reproduce the live behavior (default) or apply the baked `REPAIR R#` directives (opt-in).
- **Content gate** (`aa_build_check.py`): the only content invariant tied to a repair is
  **G-ADSET-CAT (R4)**; it is enforced **only when the run set `apply_repairs=true`**. In the default
  faithful-to-live run it is not enforced (the source froze every ad set on "category 2").
- The DAG **topology is identical** in both modes — repairs change the dispatched prompt CONTENT and
  the R4 gate, never the schedule. In the default run the extra upstream artifacts are still computed
  (faithful "dead compute"); the live prompt simply does not consume them.

## Repairs (opt-in; default OFF)

| Repair | Source defect (LIVE / default behavior) | What `--apply-repairs` does | Where enforced |
|---|---|---|---|
| **R1** | Blended Tone was passed only the tone-style NAMES, so the 4 tone chains were dead compute | `08-blended-tone` receives the four tone-style ANALYSIS documents (`artifact.04..07`) in its `<tone_style_N>` tags | baked `prompts/08-blended-tone/user.md` `REPAIR R1`; DAG `depends_on`; dispatch banner |
| **R2** | Solution-Aware pt2 injected the Problem-Aware doc (copy-paste bug) | `12-solution-aware-pt2` injects `artifact.11-solution-aware` and says "Solution Aware" | prompt header `REPAIR R2`; dispatch banner |
| **R3** | Facebook Audience Generator's `<audience_targeting_cheat_sheet>` tag was empty | it references the Black CEO Method 7-Tier framework in `methodology.md` | baked `prompts/15-facebook-audiences` `REPAIR R3`; dispatch banner |
| **R4** | Ad Sets 2–13 all froze on "category 2" | each of the 13 ad sets gets its TRUE category brief restored | baked ad-set `user.md` `REPAIR R4`; **`G-ADSET-CAT` / `AF-AV-ADSET-CAT` (enforced only under `--apply-repairs`)** |
| **R5** | Facebook headline writer's "Name of product/offer/mission:" line was empty | filled from `{{intake.offer_name}}` / `{{intake.product_info}}` | baked `prompts/37-fb-headline-copy` `REPAIR R5`; dispatch banner |
| **R6** | `Answer 9 Questions` output was generated then unused | now feeds the hero page (`39` `depends_on` `38`) | prompt header `REPAIR R6`; dispatch banner |
| **R7** | Hero page was hardcoded to `anthropic/claude-sonnet-4` via OpenRouter | **ALWAYS ON** — re-pointed to the client TIER-A model; the Anthropic chain is removed (client-path rule) | `preflight.sh` model-map; `G-NOANTHROPIC` (never gated, never reverted) |

## Other dispositions

- Orphan `o3` node → **DROP** (disconnected in source).
- Disabled Go High Level write-back → **OUT** (hook preserved via optional `contact_id`; the skill
  never calls GHL).
- Reported Drive folder-name mismatch → **RETRACTED + MOOT** (digest-truncation artifact).
- Awareness records' `System`-field leftover blended-tone persona → **KEEP verbatim** (behavioral
  fidelity; the working instructions live in methodology/user).
- Empty Facebook cheat-sheet tag / empty product line → live defect by default; repaired by R3 / R5
  under `--apply-repairs`.
- Cosmetic leftovers (`Book-titles-N.html`, "HTML Test 3", the misspelled `brand-intellegence`
  webhook path) → **die with the plumbing**.
- Strictly sequential 41-call relay → **REPLACED** by the digest-verified DAG (20 waves,
  `AA-PIPELINE-MANIFEST.json`); the ad-set harmony chain stays sequential by design (`--fast-ads`
  is an opt-in fidelity trade-off).

## Golden reference

The shipped golden (`examples/golden-lumen-rise/`) is built as a **`--apply-repairs` reference run**
(`apply_repairs=true` in its `RUN-LEDGER.json`) so it exercises the repair-gated `G-ADSET-CAT`
invariant. A default client run is faithful-to-live (repairs OFF).
