# PD-042 — BUILD REPORT

- **Unit:** PD-042 (lane FL05) — "Give the client what they need in the style-pick and finished messages"
- **Branch:** `pd/fl05-engine-reporting`
- **Base (branch head at start):** `f8cfbef105079b2bddde06f29580a3fbb96ff63e`
- **Commit:** the commit whose sha is printed in the build-room return message
- **Times:** reported in US Eastern, 12-hour

## Pre-existing work on this branch (named, not undone)

PD-018b was ACCEPTED at **`f8cfbef105079b2bddde06f29580a3fbb96ff63e`**. That unit established, and this unit leaves untouched:

- every rendered step carries a real client label (`_render_client_report_msg` fills `{client_label}`);
- hidden and no-step phases render the empty string rather than a stray separator;
- `N` is the number of RENDERED phases (`_client_rendered_phases`), not the client-visible total;
- the fallback tests require a NON-EMPTY label between the em-dash separators.

## File overlap with PD-018b, stated exactly

PD-018b touched `phases.py`, `report.py`, `tests/test_engine_client_report.py`, `tests/test_pd_engine_client_copy.py` and `tests/test_pd_report_sanitize.py`. **PD-042 edits `phases.py` only** among those, and touches neither `report.py` nor PD-018b's three test files.

- PD-018b's lines remain: `_client_need_line` (now at ~728), `CLIENT_INTERNAL_SENTENCE`, `_render_client_report_msg` (unchanged), `_client_rendered_phases` / `_client_phase_index` / `_phase_client_meta` (unchanged), and the three `blocked` sends with `CLIENT_INTERNAL_SENTENCE` in `close()` (unchanged).
- PD-042's added lines sit **between** `_client_need_line` and `_first_check_reason` (new constants + helpers), and in `_run_human_phase`'s DELIVER block, in `_block`'s signature and its one `to_requester("blocked", …)` call, in a new `_send_done_message` method, and at `close()`'s re-gate DONE path where the old `"All quality checks passed."` send was replaced by the call to `_send_done_message()`.

## The delivery finding the spec asked for

The spec's step (1) says: read `build_deck.py`'s style-preview path and DEPT `sops/brand-steward-sops.md` for the delivery step, and report what I found.

- `build_deck.run_style_preview_samples` (line 14008–14119 at the spec's base) writes nine PNGs under `working/style-preview/variant-<V>-slide-<NN>.png` plus `style_samples_manifest.json`. Its manifest carries a note telling the OWNER to route the samples to the client's own gateway — but **nothing in either file sends or attaches them.**
- `sops/brand-steward-sops.md` SOP 9.5b describes only the *recording* of the pick (`deck-intake-driver.py --style-pick … --owner-msg-id …`); it does not describe delivering the images.
- The reporter transport (`presentation_job/report.py` `dispatch3`) posts a JSON object `{chat_id, kind, message}` to `PRESENTATION_NOTIFY_CMD`. **It carries text only — it cannot carry an image.**

So the addendum's fallback branch is the one in force, and the engine now takes it explicitly: it records `phase.style_pick.transport_text_only` with the literal line `BLOCKED: transport cannot carry images` so the operator can decide, and sends **one message per variant** carrying the variant letter, its one-sentence `style_directive` from `working/copy/style_preview_spec.json`, and that variant's three sample file paths. It never sends only letters. When the manifest gives the client nothing to look at (no path and no description) it sends **no pick request at all**, records `phase.style_pick.samples_missing` with the literal line `BLOCKED: samples are not delivered to the client`, and parks.

## What changed

### `presentation_job/phases.py`

1. **Style pick (was `_run_human_phase` DELIVER block).** The old message (`"Your presentation has 3 style directions ready. Please pick ONE by replying A, B or C:\n…\n(Phase P-STYLE-PICK — …)"`) carried the phase id and told the client nothing about the samples. Replaced with one message per variant, each built by the new `_style_pick_messages(run_dir)`:
   ```
   Style <V> — <style_directive from working/copy/style_preview_spec.json>
   Your 3 style samples are ready: <that variant's 3 render paths, comma-separated>.
   Reply A, B or C to pick the look for your whole presentation. I will wait for you.
   ```
   No phase id, no token starting `P-`, never letters alone.

2. **Timeout pause.** The client sentence is now exactly
   `I still need your style pick (A, B or C). Nothing is lost — reply any time and I will pick right back up.`
   via the new `STYLE_PICK_TIMEOUT_SENTENCE` constant and a new `client_text` keyword on `_block` (default `""` keeps PD-018b's generic park sentence byte-for-byte for every other caller).

3. **Finished message.** New module-level `_compose_done_message(run_dir)` plus `Engine._send_done_message()`:
   - one line per destination in `working/checkpoints/delivery_plan.json` whose own `status` is `verified` — an `uploaded`/`planned`/absent status is never named;
   - PD-210: the teleprompter web link is added **only** when the publish record's `status` is `published`; for any other status (e.g. `warned_no_credentials`) the message adds `Your teleprompter file is included. No web link was made for it.` and no address;
   - when no verified destination exists the function returns `""`; `_send_done_message` then sends **nothing** and records `report.done_withheld`;
   - both `to_requester("done", …)` sites in `close()` are now this one path (the re-gate path previously sent the fixed sentence "All quality checks passed.").

### `tests/test_fix29_style_pick_human_stage.py` (pre-existing test, updated for a true reason)

Two assertions encoded the old single-message shape (`len(picks) == 1`, `"style directions" in …`). The pick request is now one message per variant, so the fixture seeds the 3 render paths and the style spec the samples were rendered from, and the assertions count three pick requests and require all three variant letters across them. It still proves exactly what it always proved: one delivery per variant, a resume re-delivers nothing, and nothing is picked by the engine.

### `tests/test_pd_engine_client_messages.py` (new, this unit's acceptance fixture tests)

Seven tests, all stubbed-transport, no network, no model spend.

## Commands run and their real output

All test commands ran with an empty `HOME` (`env`-equivalent `HOME=$(mktemp -d "$TMPDIR/home.XXXXXX")`) and `TMPDIR` on the portable drive (`<BUILD ROOM>/tmp`), per rule 12.

| # | Command | Output |
|---|---|---|
| 1 | `git branch --show-current` / `git rev-parse HEAD` (FL05 worktree) | `pd/fl05-engine-reporting` / `f8cfbef105079b2bddde06f29580a3fbb96ff63e` |
| 2 | `python3 -m py_compile presentation_job/phases.py tests/test_pd_engine_client_messages.py` | `COMPILE_RC=0` |
| 3 | `python3 -m pytest tests/test_pd_engine_client_messages.py -q` (branch worktree) | `7 passed in 0.84s` |
| 4 | `python3 -m pytest tests/test_fix29_style_pick_human_stage.py tests/test_pd_engine_client_messages.py -q` (branch worktree) | `26 passed in 61.26s` |
| 5 | **BEFORE** — `pytest tests/test_pd_engine_client_messages.py -q` on `f8cfbef10` + PD-018a manifest (pre-change code, same test file) | **`7 failed in 1.23s`** (`AttributeError: module 'presentation_job.phases' has no attribute '_compose_done_message'`; the three style-pick tests fail on the old single message) |
| 6 | **AFTER** — same file on the changed code + PD-018a manifest | **`39 passed in 61.62s`** for the five-file set (`test_pd_engine_client_messages`, `test_fix29_style_pick_human_stage`, `test_pd_engine_client_copy`, `test_pd_report_sanitize`, `test_pd_report_throttle`) |
| 7 | `pytest tests/test_pd_engine_client_copy.py -q` on the untouched `f8cfbef10` control tree | `3 failed, 1 passed in 0.28s` — **identical three failures** as on the branch worktree, i.e. the pre-existing PD-018a gap (this branch's manifest carries no `client_label`), not caused by PD-042 |
| 8 | blast radius: `pytest tests/test_item10_park_classes.py tests/test_engine_client_report.py tests/test_presentation_job.py tests/test_auto_resume.py tests/test_item33b_conversation_layer.py -q` | AFTER: `7 failed, 166 passed`; BEFORE (no PD-042 code, same tree/manifest): **`7 failed, 166 passed`** — identical failure lists, so no failure is attributable to this unit |
| 9 | style-pick neighbours: `pytest tests/test_f5_style_pick_passable.py tests/test_style_preview_executor_wiring.py tests/test_pres053_persona_service.py tests/test_slice1_gates.py -q` | `1 failed, 82 passed, 1 skipped`; the one failure (`test_policy_covers_all_manifest_phases`, 3 unclassified phases) also fails on the BEFORE tree (`2 failed, 16 passed` in that file alone) — pre-existing |

Trees used for the pairs, on the portable drive only:
- BEFORE: `<BUILD ROOM>/scratchpads/PD-042/before-tree` (`git worktree add --detach <path> f8cfbef10`, then `git checkout b78085f9e -- <3 PD-018a manifest artifacts>`)
- AFTER: `<BUILD ROOM>/scratchpads/PD-042/after-tree` (same base + manifest, with this unit's changed files copied in)
- HEAD control (no manifest): `<BUILD ROOM>/scratchpads/PD-042/head-control`

The PD-018a manifest (`b78085f9e`) is an unmerged-accepted ancestor and is **not** added to this branch; the behavioural proof runs in the integration trees above, which is the same method PD-018b's repair report documents.

## Statement

Nothing outside this unit's change was edited. No test was deleted, weakened or reformatted; the one updated test was updated for the true reason that the message shape it pinned is the shape this unit's spec replaces, and it still tests the same behaviour. No version bump, no changelog entry, no live action, no model call.
