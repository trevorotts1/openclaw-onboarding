# Changelog - Skill 74 KIE Live Adapter

## [1.1.8] - 2026-10-10 - setup-kie-live-adapter.sh: byte-minimal env.KIE_API_KEY insert, no backup

- New `setup-kie-live-adapter.sh`: installs THIS CLIENT'S OWN `env.KIE_API_KEY` into each Claude config root's `settings.json`. Owner order 2026-10-10.
  - Inserts exactly one key, `env.KIE_API_KEY`. Never an `ANTHROPIC_*` key, never another key, never a base URL (`07-kie-setup/references/kie-common-rules.md` rule 14).
  - Byte-minimal in-place edit: the writer scans the document for byte offsets only and inserts one line, so every pre-existing line keeps its bytes, key order, indentation and trailing-newline style. Dropping the inserted line restores the input byte for byte — the script asserts that before it writes.
  - No backup file of any kind: no `settings.json.bak-kie-*`, no `.bak`, no `.orig`. The write goes through a same-directory temp file that is renamed away and removed on any failure.
  - The key value is never printed to stdout, stderr or any log (SET/NOT SET only) and travels by environment, never by argv. The result is `chmod 600`.
  - The api.kie.ai base URL is printed as copyable text and is never written into `settings.json`.
- New `tests/test_setup_kie_live_adapter.py` (11 tests, hermetic): a reformat plant trips `test_b_pre_existing_lines_stay_byte_identical` (rc 1), a `.bak*` plant trips `test_c_no_backup_file_of_any_kind` (rc 1), the clean edit passes (rc 0).
- Version roll to v1.1.8 (`SKILL.md`, `skill-version.txt`) — the skill 07 docs-port version pin moved with it.

## [1.1.7] - 2026-10-10 - PREREQS names the one allowed settings.json write (env.KIE_API_KEY)

- `PREREQS.json` `kie-api-key` satisfy text: on Claude Code the only settings.json write allowed is `env.KIE_API_KEY` — never an `ANTHROPIC_*` key and never a KIE base URL (`07-kie-setup/references/kie-common-rules.md` rule 14). Presence check only; the value is never printed.
- Version roll to v1.1.7 (`SKILL.md`, `skill-version.txt`) — PREREQS.json and the shared skill 07 docs-port tests changed.

## [1.1.6] - 2026-10-09 - KIE official agent docs absorbed; research row 18 closed; mode-file text corrected

- Research receipt row 18 closed: `https://docs.kie.ai/ai-agent/troubleshooting.md` loads (2026-10-09). The official table (401, key missing, failed task, not enough credits, link expired) is digested at `07-kie-setup/references/kie-official-agent-docs-digest.md`.
- 2026-10-09 re-check line: both vendor archive digests still match the 2026-10-05 approval (kie-models f6247b73..., kie-chat-agents f1cbf185...).
- `references/integration-policy.md`: KIE as a chat provider for coding agents (`kie-chat-agents`) is out of scope; skill 74 never writes settings files.
- `SKILL.md` Modes text corrected to the real mode-file lookup order the code uses: `$OC_CONFIG`, `/data/.openclaw`, `${CLAUDE_CONFIG_DIR:-~/.claude}`, `~/.openclaw`. The code was already right (H7 + M8); the text was behind.
- `PREREQS.json` key entry corrected: the official variable is `KIE_API_KEY` (docs.kie.ai/ai-agent/overview); OpenClaw stores it in `~/.openclaw/secrets/.env` (Mac) or `/data/.openclaw/secrets/.env` (VPS); Claude Code machines read the live environment variable.
- No code change. Version roll to v1.1.6 (`SKILL.md`, `skill-version.txt`).

## [1.1.5] - 2026-10-09 - G3 gate bump (batch MGB010)

- `skill-version.txt` rolled v1.1.4 -> v1.1.5 by the batch MGB010 CI fix (skill 47 embedded KIE client regenerated from this skill's source). No behavior change in this skill; the CHANGELOG entry was missing until now.

## [1.1.4] - 2026-10-08 - INF002

- Install QC reads the version from skill-version.txt instead of a hardcoded v1.1.2 that failed on every box after a bump (INF002 D).

## [1.1.2] - 2026-10-06
- `--allow-host` now also governs the download-url refresh link and every redirect (a handler re-checks each Location: allow-listed host and https), ignores blank values (blank-only fails closed), and any result URL with no hostname is refused.
- Consumer options for the one-KIE-path consolidation of Skills 25, 37, 58 and 59: result downloads send a product User-Agent by default (urllib's default is 403-blocked by the result CDN); `save` and `run` take `--user-agent` (replaces it, result download only) and a repeatable `--allow-host`; `run` saves a direct result link returned by a synchronous endpoint (data.resultUrls or data.response.resultUrls). Tests: `tests/test_consumer_options.py`.

## [1.1.1] - 2026-10-06
- `submit` and `run` accept `--callback-url URL` (overrides `callBackUrl` in the request file; still http or https only). This is the production route for Skill 46 (`kie-callback-relay`): the relay's signed URL is passed on the command line and the normalized result (`task_id`, `model_id`, `data.callback_url`) is what Skill 46 `adoptAdapterTask` consumes. New test `test_callback_url_flag_overrides_request_file`.

## [1.1.0] - 2026-10-05
- Model registry: `scripts/build_model_registry.py` writes `references/kie-model-registry.json` for every model in KIE's live catalog (limits, enums, required fields, prompt field and max, verbatim fields, raw and parsed price). Source live-api, or public-docs when no key resolves.
- One price authority: `price` and `preflight` (balance against price x 1.30). The unit parser is built from every real video, audio and image `pricingDesc` phrasing in the live catalog (credits/s, credits / sec, credits per video second, per 1,000 characters, per image, duration prices such as "A 5-second video costs N credits" stay per-job); registry-wide tests keep per-second models from being labeled per-job.
- Limits authority and prompt budget: `prompt-budget` (80 percent floor, 95 to 100 percent target, exit 3 below the floor, exit 4 above the max); `validate` falls back to the registry and enforces maxLength, enum, minimum, maximum and required.
- GPT Image auto-latest: `latest-family` returns the newest generation with both text-to-image and image-to-image (numeric version order, variant then success rate then price, 6 hour cache, promotion receipt on change). `success-rate` added.
- `callBackUrl` (Skill 46) is recorded in the submit and run result; per-call `--mode off|shadow|active`; default mode unchanged (shadow).

## [1.0.0] - 2026-10-05
- New skill. One standard-library Python entrypoint (scripts/kie_live_adapter.py) that implements the contract KIE documents in its official kie-models skill: live catalog, live schema, schema validation, file upload, createTask, recordInfo polling, result download with link refresh, and credit balance.
- Default mode is shadow: discovery, schema and validation run and write drift receipts, but paid dispatch is refused so nothing is generated twice or charged twice. Modes: off, shadow, active.
- Never picks, rewrites or auto-routes a model. Pinned models (for example the fleet image pin) pass through unchanged.
- Vendor drift probe (probe box only) (scripts/vendor_skill_probe.sh) with an approved fingerprint in vendor-approval.json. The vendor package is never installed on client boxes.
- Hermetic offline tests (qc-74-kie-live-adapter.sh). Live checks are a separate opt-in script (scripts/live_smoke.sh).
