# Price calculator extensions — unit BO-PKG2-U1

Owned output: `core/catalog_calculator/extensions/` (exclusive lane ownership).
Builder artifact only: no merge, no push, no verdict file. The checker
re-runs the tests and reads the source.

## Source

- **Owner BUILD-OUT B**, V2 plan **4.2** (prices are computed, never typed in)
  and **6.14** (book promotion and batch mode, decision D26).
- `references/choice-card-spec.md` section **4**: every number on the card
  comes from Skill 74 `price` - video model, **both shapes, lip-sync
  close-ups, voice packs, clips and the batch total**.
- `references/price-menu.md` section **3** (lip-sync close-ups), **4** (voice
  packs), **6** (batch total).
- Plan **6.3** / decision **33**: lip-sync runs on three to four selected
  lines, about 15-20 seconds **per shape**; roster is Kling avatar first,
  InfiniTalk backup.
- Plan **6.2**: the song is one asset shared by every shape.
- Plan **5.4**: Skill 74 `price --model ID --units N` is the single price
  authority.

## What it does

Extends unit **V2-W0-U2**'s calculator
(`tests/catalog-calculator/catalog_calculator.py`). It never replaces that
module and never re-implements its arithmetic: `base_bridge.py` locates and
imports it, and every line is priced through its `price_line` / its
`credits_to_usd`.

### `price_card_ext(choice, catalog, skill74, approval=None, calculator_path=None)`

Same envelope as the base calculator, with `unit` set to
`catalog-calculator.extensions`. Two optional additions to `choice`:

```json
"lip_sync":    {"model": "kling/ai-avatar-standard", "seconds": 18, "lines": 4}
"voice_packs": {"count": 3}
```

| Line | Skill 74 call | Quantity |
|---|---|---|
| `lip_sync` | `price --model <roster id> --units <seconds x shapes>` | seconds and close-up lines scale with the number of shapes ordered |
| `voice_packs` | `price --model <music model> --units <count>` | one extra Suno generation per pack; the count is decided upstream by the music director, never predicted here |

The card's `line_items` then hold `video`, `music`, `image`, `lip_sync` and
`voice_packs`, and `price_credits` / `price_usd` / `price_label` /
`retake_allowance_usd` / `spending_limit_usd` are re-totalled over **all** of
them. `card.lip_sync` and `card.voice_packs` carry the counts shown to the
client. When neither addition is present the envelope is the base one,
untouched (proved by `test_card_extension.py`).

### `price_batch(ads, catalog, skill74, approval=None, calculator_path=None)`

D26 batch (plan 6.14, price-menu 6): one card per book, then

```text
batch total = sum over books of (Skill 74 price for that book's choices)
              + 20% retake allowance
```

The total is the exact sum of the per-ad card prices (whole cents, so
already-rounded quotes never drift), with `retake_allowance_usd` and
`spending_limit_usd` on top. `batch.items` holds every book's card.

Any book that cannot be priced takes the whole batch down: `state`
`unavailable`, `card` and `batch` null, `failed_ad` set, no number anywhere
and `start_paid` false.

### Fail-closed rules (plan 4.2)

| Condition | State | Reason |
|---|---|---|
| Base calculator not found or not loadable | `unavailable` | `PRICE_CALCULATOR_MISSING` / `PRICE_CALCULATOR_LOAD_ERROR` |
| Lip-sync rate unreadable | `unavailable` | `PRICE_UNAVAILABLE` / `PRICE_UNESTIMABLE` / `PRICE_UNIT_UNSUPPORTED` / `PRICE_RUNNER_ERROR` |
| Voice-pack rate unreadable | `unavailable` | same codes |
| Model outside the D33 roster | `unavailable` | `LIPSYNC_MODEL_NOT_OFFERED` |
| Malformed `lip_sync` / `voice_packs` / choice | `error` | `BAD_LIP_SYNC` / `BAD_VOICE_PACKS` / `BAD_CHOICE` |
| Empty batch / malformed book | `error` | `BATCH_EMPTY` / `BATCH_AD_ERROR` |

`start_paid` is true only when `state == ok` **and** an approval record
exists, exactly as the base calculator decides.

`find_calculator(explicit=None)` reports where the base calculator was found;
an explicit path is authoritative (no silent fall-through to another file).

## Files

| File | What it is |
|---|---|
| `price_extension.py` | the extension: `price_card_ext()`, `price_batch()`, fail-closed envelopes. Stdlib only. |
| `base_bridge.py` | locate / import unit V2-W0-U2's calculator; `REQUIRED_ATTRS` guards the surface it calls. |
| `__init__.py` | public surface. |
| `fixtures/catalog.json` | the catalog the factory's sync produces (copied read-only from unit V2-W0-U2's fixture). |
| `fixtures/skill74-responses.json` | mocked Skill 74 answers: the base fixture's table plus the D33 lip-sync roster snapshot. |
| `_fixtures.py` | `FakeSkill74` (adapter-accurate), choice / roster builders, `walk_numbers`. Not a test. |
| `test_card_extension.py` | totals: lip-sync line, voice-pack line, both shapes, re-totalling, transparent passthrough, fallback card. |
| `test_batch.py` | batch total = sum parts, retake, approval gate, mixed books, one bad book fails the batch. |
| `test_fail_closed.py` | every unreadable rate, refused model, malformed input and missing calculator leaves no number and no start. |
| `test_zero_invented.py` | every line traces to a Skill 74 answer; rate change changes price; no money literals, no rate table, no network. |
| `run_all.sh` | runs each `test_*.py`, writes `<file>.py.log`, prints a summary table. |

## Running

```sh
cd core/catalog_calculator/extensions && ./run_all.sh
```

Last run: 4 files, **175 checks, 0 failed** (`ALL_CATALOG_CALCULATOR_EXTENSIONS_TESTS_PASS`).

The base calculator's own suite stays green untouched: 5 files, 217 checks,
0 failed (`ALL_CATALOG_CALCULATOR_TESTS_PASS`).

## Scope (not this unit)

- Clips (choice-card-spec 3.7) are a free FFmpeg edit; the card shows them at
  zero and no AI rate applies.
- Velvet Voiceover's added text-to-speech line (price-menu 4) - a separate
  line on a separate decision.
- The live catalog sync, the choice-card presentation and the approval flow
  (wave V2-W1-U3) consume this envelope.
- Never-mixed book isolation, per-book folders and ledgers (unit BO-BOOK2-U2).

## Receipt

`BUILDER-RECEIPT.json` in the lane records files, counts and the not-merged
statement. It is a builder artifact, not a verdict: the checker owns
`evidence/BO-PKG2/BO-PKG2-U1.verdict.json`, and this unit never writes it.
