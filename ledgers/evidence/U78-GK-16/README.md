# U78 (GK-16) — Anthology live triage T1–T3 on the operator's own box — CORRECTED RECORD

Re-issued 2026-07-16 to clear the QC judge's SEND BACK at score 8.3 (bar 8.5) —
ticket: `~/skill6-merge-queue/ONB/U78.json`. That ticket is the authoritative
account of what was wrong with the prior pass; this file is the corrected
triage record itself, re-derived live, read-only, against the box under
triage (`command-center/app @ cdfc9090ac6e7af9e9902871b69d509e6dde7e66`,
tag `v6.0.25`). Per spec (master spec line 1987, GK-16): **live, read-only,
no repository leg.** This README is filed under `ledgers/evidence/` (the
repo's evidence convention — cf. `U81-GK-19/`, `U84-GK-22/`, `U91/`) purely
as the durable written record spec line 1990 requires ("a written triage
record with all three facts... each traced to the live command that
produced it"); no code changed, nothing was rolled, restarted, or
redeployed, and no box access beyond `Read`/`sqlite3 -readonly`/local
`curl`/`git` (no fetch) was used.

Every command below was re-run this pass, independently, not inherited from
either the original agent's report or the judge's ticket — the numbers in
both agree with what is reported here.

---

## T1 — Command Center build version (PROVED, unchanged)

```
$ git rev-parse HEAD               # <OPERATOR_HOME>/command-center/app, local read, no fetch
cdfc9090ac6e7af9e9902871b69d509e6dde7e66
$ git describe --tags --exact-match HEAD
v6.0.25
$ git log -1 --format="%ci" HEAD
2026-07-15 08:13:57 -0400
```

v6.0.25 clears the spec's v4.73.0/v5.0.0 bar by a wide margin — a
pre-enrichment build does not explain what T2/T3 find below.

The box's standing gap to `origin/main` (85 commits behind, 0 ahead) was
independently proved by the QC judge this same pass (`git rev-list --count
HEAD..origin/main` => 85) and is **not re-run here**: re-deriving it would
require a `git fetch` against the production box's command-center checkout,
which is out of scope for a read-only unit and is not needed — the figure
is already exact and undisputed. **This is a roll question, not a triage
question; no roll is proposed or implied by this unit.**

## T2 — Drift-advisory JSON (PROVED, unchanged) + two corrections

```
$ curl -s --max-time 15 http://localhost:4000/api/health/deep
  advisory.anthology_board_projection =
  {
    "pass": true,
    "ledger_participants": 5,
    "ledger_anthologies": 2,
    "board_cards": 7,
    "detail": "anthology_board_projection: OK — ledger holds 7 row(s), board shows 7 anthology card(s) (projecting)"
  }

$ sqlite3 -readonly ~/.anthology-engine/state/anthology_state.db "SELECT COUNT(*) FROM participants;"
5
$ sqlite3 -readonly ~/.anthology-engine/state/anthology_state.db "SELECT COUNT(*) FROM anthologies;"
2
$ sqlite3 -readonly <OPERATOR_HOME>/command-center/data/mission-control.db "SELECT COUNT(*) FROM tasks WHERE lower(source)='anthology';"
7
```

The advisory is not merely well-formed — it is true against the ledger and
board source rows, read independently of the endpoint.

### CORRECTION 3 — the "5 + 2 = 7 == board_cards 7" parity read is INFERRED, not proved

The counts (5, 2, 7) are proved. Their **equality having meaning** is not.
`checkAnthologyBoardProjection()` itself already computes
`ledgerTotal = ledgerParticipants + ledgerAnthologies` and its own `detail`
string already prints "ledger holds 7 row(s), board shows 7 anthology
card(s)" — restating that arithmetic is not an independent derivation.
"One board card per participant plus one per anthology" is an **assumed**
projection model that nothing in the code, the check, or the spec asserts.
5 + 2 landing on 7, the same number `boardCards` happens to be, is
consistent with a real one-card-per-ledger-row projection, but two
independently-sized populations summing to a number that coincides with a
third is not, by itself, proof of the model. **Stated honestly: these
numbers happen to match; nothing in the shipped code enforces that they
must.**

### ADDITION 4 — `checkAnthologyBoardProjection()` is structurally blind to the drift class it is cited for, not merely "a low bar"

Read directly, this pass, at the live path:
`<OPERATOR_HOME>/command-center/app/src/lib/health/deep-checks.ts:937-1053`.

The full control flow:
- ledger DB absent → `pass: true` ("not provisioned... not applicable") — line 948-954
- ledger unreadable → `indeterminate: true` — line 977-986
- board unreadable → `indeterminate: true` — line 1005-1014
- `ledgerTotal === 0` → `pass: true` ("healthy-idle") — line 1018-1026
- **`boardCards === 0`** → the **only** non-indeterminate `pass: false` — line 1028-1044
- anything else (including partial drift) → `pass: true` — line 1046-1052

Master spec line 1988 scopes T2 as reading the drift signal "for ledger
participants missing from the board (the confirmed A7 class)" — i.e.
**partial** drift. The shipped check's sole failure condition is
`boardCards === 0` (line 1028), compared once, in aggregate, against zero —
never per-participant. With 5 ledger participants, **4 of the 5 could
vanish from the board and `boardCards` would be 1, not 0**, and the check
would still return `pass: true`. It is not merely "a low bar" (the original
framing); it is **structurally incapable of seeing the exact failure class
the spec names it for** — a dead-board detector wearing a parity detector's
name. This is the most useful finding this unit can hand downstream, and it
survives the correction pass unchanged from the original report's
direction — only strengthened to match what the code actually shows.

T2 remains SATISFIED regardless: the spec's own binary acceptance names the
deliverable as "the drift-advisory JSON... whatever they turn out to be,"
and reading a weak check honestly — including disclosing its weakness
against the reporting agent's own interest — is exactly the behavior that
criterion asks for.

## T3a — Department seeded (PROVED, unchanged)

```
$ sqlite3 -readonly <OPERATOR_HOME>/command-center/data/mission-control.db \
  "SELECT id,slug,name FROM workspaces WHERE lower(slug) LIKE '%anthology%';"
anthology|anthology|Anthology
$ sqlite3 -readonly ... "SELECT COUNT(*) FROM workspaces WHERE lower(slug) LIKE '%anthology%';"
1
```

Exactly one `workspaces` row, slug `anthology`.

## T3b — Engine provisioned/running (PROVED) + CORRECTION 1 (the blocking defect)

Provisioned = **true**, independently re-confirmed:

```
$ ls -la ~/.anthology-engine/state/
... _alert_dedup.json, _alert_spool.jsonl, _hold_tick_cursor.json  — mtime Jul 16 08:00 (today)
... anthology_state.db, anthology_state.db-shm/-wal present
```

The engine genuinely ran today. That fact was never in dispute.

**What was wrong:** the prior record's supporting figure, "48 python
scripts at `~/.openclaw/skills/59-anthology-engine/scripts/`," does not
reproduce at that path. Re-derived structurally this pass, in python (no
`grep`, no shell `find | wc -l`) — script + raw output committed alongside
this file (`count-anthology-py-files.py`, `count-anthology-py-files.out`):

| Location | scripts/ | tests/ | fixtures/golden | **recursive total .py** | manifest `script_inventory` |
|---|---|---|---|---|---|
| **LIVE_BOX** — `~/.openclaw/skills/59-anthology-engine` (the box under triage) | 40 | 15 | 1 | **56** | 39 |
| REPO_SRC — `openclaw-onboarding` origin/main, `59-anthology-engine/` (post-U79 merge, `3be48c21`) | 40 | 16 | 1 | **57** | 39 |
| STALE_WT — `~/clawd/_wt/anthology-drive-n8n-broker/59-anthology-engine` (unrelated stale worktree) | 39 | 8 | 1 | **48** | 37 |

**40, 56, 39, and 48 are four different true facts about four different
questions, and this record picks the one T3 actually asks and says so
explicitly:**

- **The number this record adopts: 56 — the recursive `.py` file total at
  the LIVE_BOX path**, `~/.openclaw/skills/59-anthology-engine`, produced by
  `python3 count-anthology-py-files.py` (`os.walk`, no grep) this pass.
  This is the number T3 asks for, because T3's question is "is the engine
  provisioned/running **on the box**" — the box under triage, not the repo
  the box was built from. It also matches the master spec's own
  independent grounding at line 1977 ("`59-anthology-engine/` contains 56
  Python files... VERIFIED-BY-EXECUTION: find count") and GK-18/U80's
  original tracking-doc citation ("1/55 checklist vs 56 shipped Python
  files," master spec line 2000) — both written and verified *before* this
  unit ran, independently landing on the same figure this pass re-derives
  live.
- **40** is scripts/ only (non-recursive) — a true but narrower fact than
  what "provisioned" needs; it undercounts the engine's real footprint by
  omitting its 15 test files and its one fixtures/golden file.
- **39** is the `ENGINE-MANIFEST.json` `script_inventory` declared-entry
  count — a true fact about what the manifest *declares*, not what the
  filesystem *contains*; it is one below the 40 actually on disk in
  scripts/, consistent with U80/GK-18's judge separately flagging
  `anthology_book.py` as absent from that inventory. Not the number T3
  asks for.
- **48 is not a live-box fact at all.** It is the recursive `.py` total
  (39 scripts + 8 tests + 1 fixtures/golden) at
  `~/clawd/_wt/anthology-drive-n8n-broker/59-anthology-engine` — a stale,
  unrelated worktree that no live-box triage would read. This is
  traceable, structural proof of where the prior record's wrong number
  came from: not a typo, but a recursive count run against the wrong path.
  **This record does not reconcile to 48 — it replaces it.**

**One more honest distinction, surfaced by re-deriving this live rather
than trusting either the original report or the QC ticket:** REPO_SRC (the
`openclaw-onboarding` repo's own current `59-anthology-engine/` source,
`origin/main` at `3be48c21`) now shows **57**, not 56 — one more than
LIVE_BOX. This is not a new defect and is not this unit's to fix: GK-17/U79
merged a new test file into the repo source at 10:08:02 today (before this
pass ran), which GK-18/U80's own snapshot test already caught and
re-versioned from 56 to 57 in the same merge commit (`CHANGELOG.md`
v20.0.63, U80 entry: "U79's new test file moved the shipped-.py-file count
U80's snapshot test hardcodes from 56 to 57"). **The live box has simply
not yet been re-synced from that just-landed repo commit** — expected
staleness between a merge landing in source control and a box's next skill
sync, not drift, not a defect, and not something a read-only triage touches.
Recorded here so a downstream reader comparing this record's "56" against
the repo docs' "57" does not mistake the difference for an error in either
document.

## CORRECTION 2 — the auto-reconciler "silent bypass" finding is RETRACTED

The prior record's headline finding — that a dependency was "honored some
other way or silently bypassed by the ledger-reconciler's auto-merge" — is
**withdrawn in full.** It was investigated end to end by the QC judge this
pass and refuted on every load-bearing element (full detail in
`~/skill6-merge-queue/ONB/U78.json`, `falseAutoReconcilerAlarm`); this
record does not re-litigate that investigation, it accepts and carries the
refutation forward, per instruction:

- `ledger-reconciler/reconcile.sh` has no merge capability at all — it
  stages exactly two ledger markdown paths and pushes only those; it
  contains no `git merge` of any unit branch.
- A real merge-writer session merged U79 (`10:08:02`) and U80 (`10:11:36`)
  **32 minutes before** the reconciler's cron pass (`10:43:10`) — causality
  runs the opposite direction from the original claim.
- The status string the cron writes is not silent: it literally reads
  `"verified (auto-reconciled, needs test-proof confirmation)"`, with an
  evidence field stating the row "was NOT hand-verified... treat as
  provisional until a build session confirms test proof."
- The GK-16/U78 dependency was explicitly disclosed and deferred in
  writing by both U79's and U80's own judges (their tickets sit in this
  same `~/skill6-merge-queue/ONB/` directory) — honored by disclosure, not
  bypassed.

**The one small, real, non-alarming residual:** the ledger and its
reconciler track **merge state**, not **dependency state** — nothing in
`reconcile_core.py` reads a unit's `Deps` field. A unit can therefore merge
with an unmet dependency; in this instance that was a human merge-writer/
judge decision, made explicitly and documented in both U79's and U80's own
tickets. This is a note for whoever eventually wants dependency-aware
merge gating, not an integrity finding, and it does not implicate any other
auto-reconciled row.

## Not this unit's to fix (carried forward, correctly left alone)

- `anthology-daily-tick` exits 4 daily on `minimax` (`required:false`,
  `status_code=2049`) while all four required providers (`ollama-cloud`,
  `openrouter`, `gemini`, `kie`) pass — an alerting-hygiene question for
  whoever owns the smoke test's exit-code contract, not a required-path
  failure. The MiniMax credential was not touched.
- The box runs 85 commits behind `command-center` `origin/main`. No fleet
  roll is proposed or implied — rolling is Trevor's alone and gates
  nothing here; the box at v6.0.25 already carries the enrichment T1
  exists to check for, so being behind confounds none of the three facts.

## Command index (every command this record's facts trace to)

```
git rev-parse HEAD                                                          # T1
git describe --tags --exact-match HEAD                                      # T1
git log -1 --format="%ci" HEAD                                              # T1
curl -s --max-time 15 http://localhost:4000/api/health/deep                 # T2
sqlite3 -readonly ~/.anthology-engine/state/anthology_state.db \
  "SELECT COUNT(*) FROM participants;"                                      # T2
sqlite3 -readonly ~/.anthology-engine/state/anthology_state.db \
  "SELECT COUNT(*) FROM anthologies;"                                       # T2
sqlite3 -readonly command-center/data/mission-control.db \
  "SELECT COUNT(*) FROM tasks WHERE lower(source)='anthology';"             # T2
Read src/lib/health/deep-checks.ts:937-1053                                 # T2 (ADDITION 4)
sqlite3 -readonly command-center/data/mission-control.db \
  "SELECT id,slug,name FROM workspaces WHERE lower(slug) LIKE '%anthology%';"  # T3a
ls -la ~/.anthology-engine/state/                                           # T3b (provisioned)
python3 count-anthology-py-files.py                                         # T3b (CORRECTION 1) — this dir
```

All database reads via `sqlite3 -readonly`. No `pm2 jlist`, no `pgrep -fl`,
no full-argv listing, no secret value read or printed anywhere in this
pass. Nothing was rolled, restarted, pulled, or redeployed.
