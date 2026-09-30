# Intake acceptance test (JEV-505)

This folder holds the acceptance test from the JGT-401 review, section 4. It checks whether a CEO model, given the real intake rule, makes exactly one card per job. It should make no card for a question, small talk, or a message about work already underway.

It calls models, and each call can cost money. **Run it only when Trevor gives the go.** The offline self-test (`tests/unit/test_intake_acceptance_harness.py`) uses a fake model and costs nothing.

## Files

| File | What it is |
|---|---|
| `corpus_train.json` | Train split (about 2/3). You may read it while writing or tuning the rule. |
| `corpus_frozen.json` | **FROZEN** split (about 1/3). Never tune a rule, prompt or model on it. |
| `corpus_frozen.sha256` | Pins the frozen file. The unit test fails if one byte changes. |
| `run_intake_acceptance.py` | The harness. It uses only the Python standard library and calls the model API directly. |

## Corpus

- **295 converted messages.** These are all the `intent` rows of `tests/unit/test_decision_corpus.py`. A message that needs context is sent with a short earlier exchange (`history`), such as a pending question or a task already on the board. The label mapping:
  - `task_request` and `mixed_answer_and_task` map to `task`.
  - `answer_only` maps to `question`.
  - `social_conversation` and `unresolved` map to `small_talk`.
  - `existing_task_control` and `clarification_response` map to `existing_task`.
- **252 new owner-voice messages.** These cover typos, run-ons, polite requests, messages with two or three jobs, delegations ("tell the customer..."), small talk, "hold on", questions with filler, and follow-ups on existing tasks.
- Each item has these fields:
  - `expected`: `question`, `task`, `small_talk` or `existing_task`.
  - `jobs`: how many cards the message should make. It is 0 unless `expected` is `task`.
  - `acceptable`: other labels that are also fine, used only for truly ambiguous non-task items. A task never has one, so a task can never go without a card.
  - `label_a` / `label_b` / `disagree`: two labeling passes, compared.
- **How the labels were made.** Pass A was written with the messages. Pass B was a blind relabel of a shuffled list that showed no labels. Where the two passes disagree, the item has `disagree: true`. The disagreement is left in place, not resolved. `expected` always equals pass A.
  - Both passes were made by the same AI session, so pass B is not independent.
  - The review asks for labels made by a person, so a human relabel is still owed. Look at the `disagree` items first.
- **How the split was made.** Items are grouped by source and label. Within each group, every third item goes to the frozen split.

## Endpoints

Any OpenAI-compatible `/v1/chat/completions` endpoint works. Set it with environment variables for a single model:

```bash
export INTAKE_ACCEPT_BASE_URL=http://localhost:20128/v1   # operator 9Router
export INTAKE_ACCEPT_MODEL=<model id exactly as 9Router lists it>
export INTAKE_ACCEPT_API_KEY_ENV=<NAME of the env var holding the key>   # default INTAKE_ACCEPT_API_KEY
```

To test several models, use a JSON config file instead:

```json
{"endpoints": [
  {"name": "9router-<model>", "base_url": "http://localhost:20128/v1", "model": "<model id>", "api_key_env": "<KEY_VAR_NAME>"},
  {"name": "ollama-cloud-<model>", "base_url": "https://ollama.com/v1", "model": "<model id>", "api_key_env": "OLLAMA_API_KEY"}
]}
```

The config holds only the **name** of the environment variable that stores each key. The harness never prints the key, and it refuses any Telegram host.

## Run

```bash
python3 tests/acceptance/intake/run_intake_acceptance.py --config eps.json --dry-run   # checks the setup, makes no calls
python3 tests/acceptance/intake/run_intake_acceptance.py --config eps.json --out report.json
```

The defaults are `--split frozen` and `--runs 3`, which is the official test. Use `--split train` while tuning.

A `--limit N` run is a smoke test only, and it can never pass. A run with fewer than 3 runs can never pass either.

The harness reads the rule text from `shared-utils/ceo_execution_policy.py` (`POLICY`) each time it runs. If that text does not contain `mc-route.sh task` (the V4 rule), the harness exits with code 2. `--allow-legacy-policy` scores an older rule anyway.

## What is sent and what is scored

- **What the model sees:**
  - System context: a one-line CEO persona plus the rule text.
  - The item's earlier turns, then the owner's message.
  - One tool, `exec`, which takes a shell command.
- **Nothing is executed.** An `mc-route.sh` call gets a canned `ROUTED ...` line back, and any other command gets `sandbox: command not executed`. The conversation continues until the model gives a final reply, for at most 4 rounds.
- **What counts as a card:** each `mc-route.sh` call in `task` mode, in slug mode, or in legacy `auto` mode. The report counts `auto` calls separately.
- **The scores:**
  - `dropped`: a task with no card.
  - `double`: more cards than jobs.
  - `extra`: a card for a non-task item whose `acceptable` list does not include `task`.
  - `under_carded` (for information only): a multi-job message that got some cards, but fewer than it has jobs.
  - `disagreement_failures`: failures on items where the two labeling passes disagree. Review these by eye.
- **The pass mark.** A model passes only if all 3 runs on the frozen split meet every condition:
  - 0 dropped
  - 0 double
  - 0 errors
  - extra cards on at most 3% of non-task items
- The exit code is 0 when every model passes, 1 when any model fails, and 2 for a setup error.

This harness does not measure whether a card goes to the right department. The review's 90% department check is a separate unit.
