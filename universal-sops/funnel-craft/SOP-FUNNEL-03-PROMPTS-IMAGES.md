# SOP-FUNNEL-03: IMAGE PROMPTS (MODEL BUDGET) + GENERATION + PROVENANCE

**Cluster:** Funnel-Craft Rules (`universal-sops/funnel-craft/`)
**Master authority:** `49-signature-funnel/MASTERDOC.md` §4 (the 8-block order + Signature Grade Block) and `07-kie-setup/references/kie-common-rules.md` (KIE rules; wins on any KIE disagreement)
**Owning role:** Signature Funnel Specialist
**Stage:** P2-PROMPTS (author) + P3-IMAGES (generate: policy Skill 66, transport Skill 74)
**Produces:** `working/copy/prompt_ledger.json`, `working/media/media_ledger.json`, `receipts/kie74/*.json`
**Provers:** `49-signature-funnel/scripts/prove_sf_prompt_floor.py` (prompts) + provenance gate (images)

---

## 0. WHY THIS SOP EXISTS

A short or generic prompt produces a flat, off-brand image. Prompt length is SACRED and is measured, not
declared: a prompt uses **95 to 100 percent of the chosen model's character maximum and never falls below 80
percent of it** (owner order 2026-10-05, `kie-common-rules.md` rule 12). That replaced the earlier 5,000 to
19,000 band. A two-floor gate (length floor + structure/excellence floor) plus the Skill 74 budget check mean
a failing prompt physically CANNOT reach a paid Kie call.

## 1. THE 8-BLOCK BUILD ORDER (every prompt)

1 Subject & Wardrobe · 2 Composition & Shot · 3 Typography (text-bearing sections only; dominant for
Sec 11) · 4 **Signature Grade Block (verbatim)** · 5 Lighting · 6 Quality & Render · 7 Facial
Intelligence · 8 Brand-Style + Negative Block (final paragraph). Front-load subject/emotion/composition;
end-load the negative block.

## 2. HARD RULES

- **Length budget:** the maximum comes from `python3 74-kie-live-adapter/scripts/kie_live_adapter.py prompt-budget --model <id>`
  (live schema, registry fallback), never from memory. Target 95 to 100 percent, floor 80 percent, ceiling 100
  percent. Check each prompt with `prompt-budget --model <id> --check --prompt-file <file>`: exit 3 prints the
  exact characters to add, exit 4 the exact characters to cut. `prove_sf_prompt_floor.py` (AF-FUN-PROMPT-FLOOR /
  AF-FUN-PROMPT-CEILING) enforces the stripped-length gate and must agree with rule 12; where the two ever
  differ, rule 12 wins and the prover is the item to fix, never a reason to pad or truncate.
- **Signature Grade Block** (~1,290 chars) embedded verbatim in block 4 of EVERY prompt (AF-FUN-PROMPT-GRADE).
- **Negative block** present in the final paragraph (AF-FUN-PROMPT-NEGATIVE).
- **No em dashes** anywhere in an image prompt (AF-FUN-PROMPT-EMDASH) — the model-safety rule.
- **Distinct-word density** floor (AF-FUN-PROMPT-DENSITY) — padding attacks fail.
- **Sec 11 is typography-as-art:** three spelling-locked words in quotes (AF-FUN-PROMPT-TYPO); no-text
  sections state "no text anywhere" explicitly.

## 3. GENERATION (P3): POLICY THEN TRANSPORT, THE ONLY APPROVED KIE PATH

Skill 74 is the single approved KIE path (rule 1 authority order; rule 2 endpoints). Nothing in a run calls KIE
any other way.

**Policy (Skill 66 for images, Skill 67 for video):** picks the model from its registry. The GPT Image default is
the newest GPT Image generation in KIE's live catalog, resolved by
`kie_live_adapter.py latest-family --family gpt-image` (rule 13; GPT Image 2.5 Sunburst today; every automatic
switch writes a receipt and is reported). A department pin or an explicit client model request overrides it.
Never write a model id from memory (rule 10). Ratios follow N43 (rule 11): the funnel's 16:9 slots and Sec 12's
3:4 are served as asked on the default model; 5:4 becomes 4:3, 4:5 becomes 3:4, 2:1 becomes 16:9, 1:2 becomes
9:16; 3:1, 1:3 and 9:21 use the legacy route only.

**Transport (Skill 74), per image, from the `74-kie-live-adapter` folder, each dispatching call with `--mode active`:**

1. `validate --model <id> --payload input.json` (live schema; blocks out-of-limit requests before dispatch).
2. `preflight --model <id>` (balance must cover price x 1.30; prices are never typed into any file: ask `price`).
3. `prompt-budget --model <id> --check --prompt-file <prompt.txt>` must exit 0.
4. `submit --request req.json --mode active` (or `run --request req.json --save-dir DIR --mode active`).
5. `wait --task-id <id>` then `save --task-id <id> --save-dir DIR`: save immediately (links can expire within
   24 hours, rule 8). The `reference_images` hook uploads each reference with `upload` and puts its URL in the
   reference field the live schema names; the mandatory style-only guard is appended to the prompt.
6. Record the evidence: `python3 49-signature-funnel/scripts/kie74_receipt.py --run-dir <RUN_DIR> --phase P3-IMAGES --result result.json`.
   It refuses a shadow, skipped or failed result, stores the adapter result under `<RUN_DIR>/receipts/kie74/`
   and appends the provider receipt that `delegation_receipt.py` checks.

Account limit: 20 createTask requests per 10 seconds, shared by every agent (rule 3). Stop on a 401 or 403 and
report once (Skill 74 makes one attempt). The key is the client's own and is never printed (rule 9). Skill 74 never
retries createTask after a network error. Paid-call approval (USD announce plus budget cap) still comes first.

NEVER hand-roll a Kie `createTask`, copy `kie_live_adapter.py` or an older KIE client script (`kie_image.py`,
`kie_generate.py`) into the run dir, or call `curl` against the API: that is AF-FUN-CANONICAL-BYPASS. The entry
shell's bypass scan allow-lists only Skill 74's own result files directly inside `receipts/kie74/`, and
re-checks each one.

## 4. PROVENANCE

Every generated image MUST carry a real Kie `taskId` (AF-FUN-IMG-PROVENANCE) — no native/placeholder
image. An empty image set for a page is AF-FUN-IMG-EMPTY. (Host resolution to the GHL media library is
gated at P4 by AF-FUN-IMG-HOST — see SOP-FUNNEL-04.)

## 5. VERIFY BEFORE ADVANCING

```
python3 49-signature-funnel/scripts/prove_sf_prompt_floor.py --ledger working/copy/prompt_ledger.json
```

Exit 0 = every prompt cleared both floors and P3-IMAGES may run. Any `AF-FUN-PROMPT-*` code = fix the
prompt and re-run. Never pad to length — the density floor rejects it.
