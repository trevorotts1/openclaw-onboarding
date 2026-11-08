# Skill 6 recovery and continuation ledger

Updated: November 8, 2026. Owner: Trevor Otts.

## Start here in a new chat

Read this file, PLAYWRIGHT-RECIPES.md, PLAYWRIGHT-REQUIREMENTS.md,
and tools/playwright_recipes/catalog.json.
Inspect actual source and rerun tests before reporting completion. Preserve existing
location/page/form IDs from each client's state.json. An uncertain mutation must
be reconciled by read-back before another create. Never infer completion from chat.

Repository: https://github.com/trevorotts1/openclaw-onboarding
Recovery branch: skill6/recovered-recipes-20261108
Original branch: skill6/playwright-recipes-20261108
Recovery base: 6edc66a74d01b4a77e592df4f50241487ba4a6ee (original branch at d50b3841a contained no new recipe implementation).

## Recovered and checked

The previous workspace survived at /workspace/scratch/59aa6a7ca6e6.
The package under 06-ghl-install-pages/tools/playwright_recipes is the maintained
copy. The separate skill6-playwright directory was a development copy.

- Recovered shared executor, compiler, router, host adapter, preflight, catalog,
  example inputs and source tests, plus the recipe guide and Skill 6 instructions.
- Recovered Firebase bridge origin guard change for Convert & Flow.
- Reran all 18 recovered offline tests: PASS. This proves offline behavior only.
- 22 catalog routes: 21 executor entries and 1 API-first course handoff.
- Historical live-path observations are recorded in the catalog/guide; they were
  reported by the prior chat, not independently repeated in this recovery.
- No final Python end-to-end Mac or VPS run was recovered.
- Added 3 checkpoint tests; recipe and checkpoint suite: 21/21 PASS.
- This Linux workspace lacks Playwright and the OpenClaw/Agent Browser CLIs;
  preflight returns HOST_SETUP_REQUIRED. No live Python run claimed.
- Run-state JSON now flushes and fsyncs before atomic replacement.
- Added checkpoint.py to export source, requirements summary, progress and a
  per-file SHA-256 manifest to ~/Downloads/BlackCEO-Skill6 on the executing host.

## Recovery verification details

- Recipe/checkpoint suite: 21 passed. Python and JSON syntax: PASS.
- Auth/manager combined pytest: 63 passed, 1 teardown timeout at 60 seconds.
  Unchanged baseline isolated test: PASS. Candidate isolated retest also timed out at 60 seconds; unresolved.
  The browser-manager implementation differs only by its release version marker.
- Release-bundle checks passed, but the root release roll was removed to keep this
  recovery limited to Skill 6. No release/merge performed. Skill 6 changelog and
  version carriers are updated; release integration remains for the merge train.
- Split-test capture retried on the existing probe funnel/page:
  named ZHC Skill 6 Playwright Funnel Probe 2026-11-08. Create variation opened a
  JavaScript alert; browser connection timed out attempting dismissal. No variant
  creation or allocation was verified. Reconcile the screen before another click.

## Remaining work, in order

1. Save source to a remote commit and draft PR; resolve the host teardown timeout
   before declaring host integration clean. Checkpoint integrity tests pass.
2. Capture native split variant creation and traffic allocation. Prior browser alert
   prevented reliable capture. Do not substitute guessed selectors.
3. Capture all advanced form choices/options, survey branches, quiz scoring/results
   with persisted read-back assertions.
4. Verify native checkout products, bumps and one-click bindings under the existing
   Skill 44/79 payment contract. Component insertion alone is not payment proof.
5. Recover community portal access through the actual account flow. Prior portal
   showed expired password. Group creation was exercised; settings were blocked.
6. Finish meeting creation/read-back and integrations. Prior controls were inspected;
   final room creation/read-back was not verified. Recheck official documentation.
7. Exercise API-first course dispatch; capture genuinely UI-only course settings.
8. Run final Python process on client Mac and Linux VPS, then independently verify
   desktop/mobile render, form submission, quiz branches and test-payment behavior.

## Checkpoint discipline

After each completed script/profile or meaningful correction:

1. Update this ledger and catalog evidence levels with actual outcomes and next step.
2. Run appropriate tests; record their command, counts, failures and limitations.
3. Commit and push the feature branch. Do not wait for the end of the chat.
4. Run checkpoint.py on the client host for a dated Downloads archive.
5. Keep client state.json and handoff.json in that client's protected persistent run
   directory. They contain object IDs and last-step intent. Do not put credentials,
   browser storage, seed files or client evidence into the source archive or repo.

The archive's manifest records exact bytes even if edits have not been committed.
It does not upload anything or automatically run after every edit. The executor
already writes state before and after mutations; this is separate from source backup.

## Commands

```bash
python3 -m unittest discover -s 06-ghl-install-pages/tools/playwright_recipes -p 'test_*.py' -v
python3 06-ghl-install-pages/tools/playwright_recipes/preflight.py
python3 06-ghl-install-pages/tools/playwright_recipes/checkpoint.py
```

## Resume instruction

Continue the existing Skill 6 Playwright job from PLAYWRIGHT-PROGRESS.md. Verify
the latest remote branch and source manifest, read the catalog, rerun tests and
continue the first unfinished item. Do not recreate existing live test objects or
claim PROFILE/CAPTURED entries are verified. API/MCP/Skill 44 first when the exact
operation is supported; ready Playwright recipe next; current OpenClaw extension,
Agent Browser, then computer control. Publish and payment actions retain their
existing authorization requirements.

## Continuation: native form settings

Added forms.settings for seven explicit native settings: save progress, submission
document, recommendations, sticky contact, create conversation, timezone and font.
Captured the actual eight-switch order and each containing row label in the live
form editor. The script checks both before clicks, saves and reloads the editor
to compare persisted values. Scheduling is excluded because it requires dates
and messages. Python end-to-end execution remains pending, not marked LIVE_PATH.

The private handoff now links to the original owner attachment in full. The
repository was verified public; the full conversation is not published there.

Continuation validation: 23 recipe/checkpoint/settings tests passed. Native form
settings controls captured live; no settings mutation performed in that capture.
