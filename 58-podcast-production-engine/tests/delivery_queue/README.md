# Delivery-and-queue slice tests (Skill 58)

Independent tests for the delivery-and-queue slice of the Podcast Production Engine
(PRD Steps 16 to 18 and Section 5 cross-cutting). System under test:

- `scripts/delivery_report.py` (W1.26): builds the OPERATOR-ONLY delivery report,
  reproduces CHECKLIST Part A honestly, and hard-refuses any client-facing
  destination.
- `scripts/credit_queue.py` (W1.27): credit-out queue mechanics: hold with full
  payload plus partial state, daily age-check, 60-day age-out with payload purge,
  resume from resume_stage. Delegates all persistence to the sole writer
  (`podcast_state.py`) and all alerts to `alert-dedup.py`; creates no cron.
- `scripts/personal_spreadsheet.py` (W1.28): Personal-mode running spreadsheet:
  create-at-setup (idempotent), append-per-episode, custom-field link storage,
  Interview-mode hard refusal.

## Run

    ./run-delivery-queue-tests.sh

`conftest.py` puts `../../scripts` on `sys.path`. No network, no real services, no
client box is touched; the queue and spreadsheet run against an in-memory backend
and a temp-dir CSV backend respectively.

## Interfaces this slice depends on (owned by other slices)

- `podcast_state.py` (W2.1): the sole writer of `podcast-engine.db`. `credit_queue`
  shells to it via `PodcastStateBackend` (subcommands hold, resume, sweep-aged-out,
  purge-payload, list). This slice never opens the DB read-write.
- `alert-dedup.py` (W2.6): the only founder-alert path. `credit_queue` routes holds,
  age-outs, and restores through an injected alert hook; the default is an
  operator-only stdout note.
- The Convert and Flow field layer (W1.18): `personal_spreadsheet.store_spreadsheet_link`
  accepts an optional field writer and a caller-supplied field key (no standardized
  key is invented here).
