# Item-level stage gates: specification (fix plan Item 20)

Delivered as `scripts/stage-gate-item-commands.patch` against S1's
`scripts/stage_gate.py` and `references/stage-contract.json`. The patch is the
deliverable; this document is its contract. Nothing in the S7 tree edits
`stage_gate.py` or the contract in place.

## What this cuts

Before this item, `image-inventory-prompts` and `image-generation-qc` moved
only as whole stages: generation for image 1 could not start until every
prompt was written, validated, and reviewed, because the stage gate knows
only stages. The old swarm plan already promised per-image flow ("generation
begins per image as its prompt passes"), which the stage gate forbade. That
contradiction is resolved here, at the gate, in favor of per-item flow:

**An image's generation may start the moment ITS prompt item closes. The
prompt stage as a whole does not need to be closed.**

Stage-level `check` is unchanged and still requires the full dependency
chain. Stage-level `close` for an itemized stage gains one fan-in check and
otherwise runs exactly the same verifications as before (artifacts,
validators, Review Receipt v2 files, cost, transport). Item commands add a
finer path; they loosen nothing.

## Which stages are itemized

A stage is itemized when its contract entry carries `"itemized": true`. The
patch adds that flag to exactly two stages:

- `image-inventory-prompts` (per-file glob `image-inventory-prompts/IMG-*.txt`)
- `image-generation-qc` (per-file glob `image-generation-qc/Image-*.png`)

Both have `per_file_glob` and a `count_of` inventory. The gate also recognizes
the two stage names if the flag is absent (defensive), but the flag is the
contract of record.

## Item identity

- The canonical item id space is the inventory id space from the stage's
  `count_of` file (`desktop-wireframe/image-inventory.json`), for example
  `IMG-001`. Item ids are identical across both itemized stages: generation
  item `IMG-001` is fed by prompt item `IMG-001`.
- An item's artifact is located by matching the stage's `per_file_glob` and
  comparing the trailing number: `IMG-001.txt` and `Image-001.png` are both
  item `IMG-001`.
- An item's Review Receipt v2 file keeps the gate's existing naming: the
  review item id is the artifact's file stem (`IMG-001` for prompts,
  `Image-001` for images), at
  `private/reviews/<stage>/<review-item-id>.review.json`, written by
  `scripts/write_review.py` from the reviewing session. Review files are
  never written by hand.

## State schema

Item state lives inside the existing `private/state.json`, alongside
`stages` and `receipts` (older state files load unchanged; the `items` key
defaults to empty):

```json
"items": {
  "image-inventory-prompts": {
    "IMG-001": {
      "status": "closed",
      "closed_at": "2026-10-13T14:02:11+00:00",
      "artifact_hashes": {"image-inventory-prompts/IMG-001.txt": "<sha256>"},
      "review": "private/reviews/image-inventory-prompts/IMG-001.review.json",
      "review_item": "IMG-001",
      "review_hash": "<sha256>"
    }
  }
}
```

A blocked item instead carries `status: "blocked"`, `blocked_reason`, and
`blocked_at`. Every item transition also appends one JSON line to
`private/run-events.jsonl`:

```json
{"event": "item_closed", "stage": "image-inventory-prompts", "item": "IMG-001", "artifact": "image-inventory-prompts/IMG-001.txt", "at": "..."}
{"event": "item_blocked", "stage": "...", "item": "...", "reason": "...", "at": "..."}
```

Item 24 formalizes the run-event feed schema; these two event names are the
ones the swarm runner (Item 21) emits and consumes today.

## Subcommands

All three exit 0 on pass and 1 with named failure lines on stdout, matching
the gate's existing convention. All three refuse a non-itemized stage with a
failure naming the itemized stages and directing the caller to `check` /
`close`.

### `check-item <run_dir> <stage> <item-id>`

Answers "may this item start now?" using only the item's own dependencies:

- Unknown item (not in the inventory universe): fail, naming the universe
  source.
- Already closed: pass. Blocked: fail, naming the recorded blocked reason.
- Prompt items (`image-inventory-prompts`): every stage in the contract's
  `depends_on` is closed (with its dep-receipt hash verification, the same
  `verify_dep_receipt` the stage check uses) and every `requires_artifacts`
  entry exists.
- Generation items (`image-generation-qc`): the upstream item with the same
  number is closed in item state, and the upstream stage's structural
  (non-per-file) artifacts exist (for example `prompt-manifest.json`). The
  upstream stage itself need not be closed. This is the weld cut.

### `close-item <run_dir> <stage> <item-id>`

Answers "is this item done?" with the full per-item verification:

1. The item's dependencies (the `check-item` core) hold.
2. The item's artifact exists.
3. The stage receipt exists and is not `fail` (the v2 receipt rules are
   S1's, unchanged; item close rides on the stage receipt for author
   identity, cost, and transport, exactly as stage close does).
4. The stage's validators re-run against this item's file only (same
   placeholder substitutions as the stage path).
5. The item's Review Receipt v2 file verifies: artifact named and hash
   matches the bytes on disk, author and reviewer sessions real and
   mutually independent and different from the receipt author session,
   verdict `pass`, every criterion carries a `{score, note}` with a note of
   at least 40 characters.
6. Scoring is per-artifact (Amendment 6 / S1's Item 12 rule): this item's
   mean criterion score must meet `min_scores.average` and every criterion
   must meet `min_scores.each`. One strong item cannot carry a weak one at
   item close.
7. Cost verification (stage-scoped, S1's `check_cost`, unchanged).
8. For transport-required stages, the transport slice for this item: the
   receipt's transport block names an approved route and policy, and its
   `tasks` list carries an entry for this item's file whose Skill 74 task
   verifies (task receipt at `receipts/kie74/<task_id>.json` in `success`
   state from the active adapter, `preflight_ok` true, `budget_exit` 0,
   real `model_id`, valid `model_source`, ratio fields consistent).

On success the gate records the item close in state (schema above) and
appends the `item_closed` event. Closing an already-closed item whose
artifact bytes are unchanged passes (idempotent resume). Closing an
already-closed item whose artifact changed fails: the review must be redone
against the new bytes.

### `block-item <run_dir> <stage> <item-id> --reason <text>`

Records the item as blocked with a named reason and appends the
`item_blocked` event. This is how the swarm runner parks an item that has
spent its retry, so the block is durable, named, and visible to fan-in
instead of a silent stall.

## Fan-in at stage close

`close` on an itemized stage first verifies that every item in the universe
is closed at item level. Blocked items fail the close by name with their
recorded reason; unclosed items fail by name with the instruction to close
them with `close-item`. Only then do the existing full-stage verifications
run (all artifacts, all validators over all files, all review files, cost,
the full transport task list).

One composition note, stated plainly: stage close re-runs S1's
`check_review_scores`, which pools criterion scores across items for the
stage average, while `close-item` applies the stricter per-artifact average
from Amendment 6. Because every item must already have passed the
per-artifact rule at item close, the pooled stage check can only be weaker
in practice; the per-artifact rule is the binding one. If S1's delta pass
moves stage close to per-artifact scoring as well, the two compose
identically.

## Proposed contract text for references/artifact-contracts.md

Coordinator action (S7 does not edit that file): add an "Item state" entry
for the two itemized stages:

> **Item state (itemized stages: image-inventory-prompts,
> image-generation-qc).** Producer: `scripts/stage_gate.py` (`close-item`,
> `block-item`). Consumer: `scripts/stage_gate.py` (fan-in at stage close),
> `scripts/swarm_runner.py`. Location: `private/state.json` under
> `items.<stage>.<item-id>`, plus one JSON line per transition in
> `private/run-events.jsonl`. Item ids are the inventory ids from
> `desktop-wireframe/image-inventory.json` (`IMG-001`, ...). A closed item
> records `status`, `closed_at`, `artifact_hashes` (SHA-256 of the item's
> artifact at close), `review` (the item's Review Receipt v2 path),
> `review_item`, and `review_hash`. A blocked item records `status`,
> `blocked_reason`, `blocked_at`. An item is done only when the gate closed
> it; worker self-report never writes item state.

## SKILL.md note (coordinator action)

SKILL.md is coordinator-owned. The item commands should be named wherever
SKILL.md describes the stage gate's command surface: `check-item`,
`close-item`, and `block-item` operate per item on the two itemized stages;
see `references/item-gate-spec.md`.

## Applying and testing

```bash
cd <repo root>
patch -p1 < 71-blackceo-signature-page/scripts/stage-gate-item-commands.patch
python3 -m unittest 71-blackceo-signature-page/tests/test_item_gate.py
```

`tests/test_item_gate.py` (9 tests) covers: prompt item check and unknown
item naming; generation item held until its own prompt closes; the weld cut
(generation `check-item` passes while stage-level `check` still refuses);
close recording state and the `item_closed` event; idempotent re-close;
per-artifact average enforcement; generation close with a valid Skill 74
transport entry; generation close refused without one; stage-close fan-in
naming a blocked item; item commands refused on a non-itemized stage.
