# AF-SHARE-U2 — spoken share on the choice card and in the docs (D15 retarget)

Source: Decision log 37 (D15 retarget) 2026-10-07; plan 6.7; SPK001 retarget 2026-10-08.
Acceptance: *card/docs updated; 5-minute reference note present; mocked tests
green; module files in the owned dir; zero paid calls; no media files or
operator paths; Skill 74 only KIE path; ships only via the batch train.*

## What the owner ordered

> "Okay, let's go to your recommendation that cut it to about 20-25%."
> (Trevor, 2026-10-08.) Spoken share 22.5% of the runtime (20-25%); singing
> measured against voice time, sung / (sung + spoken), target 77.5% (75-80%);
> within 5 points accept, 5 to 10 accept with a flag, past 10 redo. Same for
> every length and style, the spoken opener stays short, and the first real
> singing (measured on the vocal stem) is targeted at 15% of the runtime. It
> replaces the earlier 45 percent target, its 40-to-55 band and the
> per-length targets.

## Canonical strings (`share_card_docs.py`)

| constant | value |
|---|---|
| `SPOKEN_TARGET_PCT` | `22.5` |
| `SPOKEN_BAND_PCT` | `(20, 25)` |
| `SUNG_VOICE_TARGET_PCT` / `SUNG_VOICE_BAND_PCT` | `77.5` / `(75, 80)` |
| `SPOKEN_MAX_PCT` / `SPOKEN_MIN_PCT` | `32.5` / `12.5` (redo edges) |
| `FIRST_SUNG_TARGET_PCT` | `15` |
| `CARD_LINE` | `Spoken:      22.5% of the runtime (20-25%)  /  sung 77.5% of voice time (75-80%)  /  short spoken opener  /  first real singing at about 15% of the ad` |
| `DOCS_STATEMENT` | the SPK001 paragraph: target 22.5%, singing 77.5% of voice time, the 5/10 band, every length and style, rap counts as spoken, opener short, first real singing at about 15% of the ad, replaces the earlier target and the per-length targets |
| `REFERENCE_NOTE` | the 5-minute reference note (below) |

`CARD_LINE` follows the plan 4.1 card column: the label plus padding puts the
body at column 13, exactly like the `Style:` / `Music:` / `Voice:` lines.

## The 5-minute reference note

`REFERENCE_NOTE` states, in one paragraph:

- the owner-approved **5-minute** One Check Chanel reference ad measures
  **57.0% spoken** (170.9 s of 300 s — `qualification/hybrid-one-check-chanel/storyboard-5min.md`);
- that is **over the new 32.5% redo limit**, so it does not set the spoken share and
  no new ad may copy that number;
- its **recipe still stands for everything else**: story, beats, look, timing
  map, voices and the C3 audio method.

`reference_is_over_limit()` and `reference_within_retired_band()` are the two
halves of that sentence: 57% fails the new band and passed the retired band
(40 percent floor to 70 percent ceiling), which is exactly why it was never
flagged before.

## Fail-closed readers

`check_card_text(text)` and `check_docs_text(text)` return the list of
requirements the text is missing (empty list = the text carries D15 plus the
note). `find_stale(text)` names any retired-band wording. The tests plant
known-bad text (old band, gutted percentages) and prove both readers refuse
it, and prove clean text passes — a check that cannot fail is not evidence.

## Wiring (deliberate, not this unit)

The canonical line and paragraph live here. Dropping them into the rendered
choice card (`core/style_defaults/card.py`) and into the skill's
`references/choice-card-spec.md` copies is a one-line paste of `CARD_LINE` /
`docs_statement()` at merge time — this wave runs concurrent units that edit
the same card and docs files, so this unit ships the strings instead of
racing them onto disk.

ponytail: no validator reads a live card or docs file from disk. Add a
read-only scanner only when a later unit needs to prove a specific doc file
already carries the wording.

## Mocked tests (stdlib only, zero spend, no provider import)

```
python3 core/spoken_share_card_docs/test_share_card_docs.py
```

Socket is stubbed to raise, the shipped module is scanned for network /
provider / URL code, the package is scanned for media files and for absolute
operator paths (both needles assembled at run time so the suite never stores
what it bans), and the build root is found by walking up from this file.

## Owner rules observed

- no `SWARM-PLAN.json`, `launch-*.json` or `workflow-*.js` touched;
- `qualification/` and the owner's read-only input packet read only;
- no media file, no absolute operator path, no spend, no provider call;
- KIE access: none in this unit — no request is built here; if a later unit
  calls KIE for this rule, it goes through the Skill 74 live adapter path only;
- ships only via the batch merge train (build workspace is staged, not a git
  repository — the commit happens when the train carries it).
