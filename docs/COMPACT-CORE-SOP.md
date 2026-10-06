# SOP: Compacting a bootstrap file (compact core)

This is the one procedure for shrinking any of the six always-loaded bootstrap files on any box on
the fleet without losing a word. Long content moves out to the box's reference root **verbatim** and
leaves a four-line pointer behind. Nothing is summarized away, merged, or deleted.

It exists because those six files are re-billed to the model on **every turn**. Text stamped or
written into them is paid for forever, on every box, on every message, until something takes it back
out. Nothing ever did.

Two tools implement it, and they split the work by **who owns the text**:

| Tool | Owns | Runs |
|---|---|---|
| `scripts/bootstrap-pointerize.py` | SCRIPT-OWNED blocks the fleet roll stamps | during a roll, from `apply-fleet-standards.sh` and `update-skills.sh` |
| `scripts/compact-bootstrap.py` | OWNER-AUTHORED sections | daily check, weekly compaction (`scripts/bootstrap-compact-weekly.sh`) |

They write the **same pointer**. `compact-bootstrap.py` imports `build_pointer` and
`POINTER_SENTINEL` from `bootstrap-pointerize.py` rather than re-implementing the format, so a box
can never end up with two pointer shapes and a validator that only resolves one of them.

---

## 1. Scope: six files, every workspace, one procedure

| File | Lean target (chars) |
|---|---|
| AGENTS.md | 60,000 |
| TOOLS.md | 60,000 |
| MEMORY.md | 32,000 |
| USER.md | 32,000 |
| SOUL.md | 32,000 |
| IDENTITY.md | 32,000 |

The lean targets live in exactly one place: `DEFAULT_BUDGET` in
`scripts/validate-core-references.py`. Both tools and the daily check read them from there, and each
of them accepts the same override chain (`OPENCLAW_BOOTSTRAP_BUDGETS`, `--budget-file`,
`--from-config`, `--budget NAME=CHARS`). Change a target in one place and everything follows.

**The hard limits are different and are never touched.** A box truncates a bootstrap file past
`agents.defaults.bootstrapMaxChars`, and all of them together past
`agents.defaults.bootstrapTotalMaxChars`, both set in that box's `openclaw.json`. Never edit those.
The lean targets exist so the files never approach the cliff.

### 1a. Workspaces are read from config, never assumed

A box can run one workspace or several. `compact-bootstrap.py` takes them from `openclaw.json`:
`agents.defaults.workspace`, plus every `agents.entries[].workspace`. `agents.entries` is a
dictionary keyed by agent id on a current box and a list in older configs, and both shapes are
handled.

The list is then **deduplicated by resolved real path**, which is load-bearing rather than tidy. On a
Mac client box `~/clawd` is a symlink to `~/.openclaw/workspace`. Treating those as two workspaces
would compact the same file twice in one run, write the ledger twice, and stamp the second pointer
over the first. Two genuinely distinct directories both survive the dedupe, which is what an operator
box with a second root workspace needs.

To see exactly what a box would act on, without acting:

```
python3 scripts/compact-bootstrap.py --list-workspaces
```

---

## 2. Per-platform paths

Verified live on the fleet on 2026-09-18. Nothing below is hardcoded in the tools; it is listed here
so a human can check what a tool resolved.

| | Mac client | Hostinger VPS container | Contabo container |
|---|---|---|---|
| HOME | `/Users/<clientuser>` | `/data` | `/home/node` |
| OpenClaw root | `$HOME/.openclaw` | `/data/.openclaw` | `/home/node/.openclaw` |
| Config | `$HOME/.openclaw/openclaw.json` | `/data/.openclaw/openclaw.json` | `/home/node/.openclaw/openclaw.json` |
| Workspace | `$HOME/.openclaw/workspace` (`~/clawd` is a **symlink** to it) | `/data/.openclaw/workspace` | `/home/node/.openclaw/workspace` |
| Reference root | `$HOME/Downloads/openclaw-master-files/References 4 Bootstrap/` | `/data/openclaw-master-files/References 4 Bootstrap/` | `/home/node/.openclaw/master-files/References 4 Bootstrap/` |
| Persistent scripts | `$HOME/.openclaw/scripts/` | `/data/.openclaw/scripts/` | `/home/node/.openclaw/scripts/` |
| python3 | 3.9 | 3.14 | present |
| jq | present | present | **ABSENT** |
| Gateway log | `$HOME/Library/Logs/openclaw/gateway.log` | `docker logs <container>` | `docker logs oc-<slug>` |

Everything in the tooling is pure `python3` with no `jq`, and nothing uses syntax newer than 3.9,
because the oldest interpreter on the fleet is the Mac's 3.9.6 and the Contabo container has no `jq`
at all.

**The operator box is the exception that proves the rule.** It runs a main workspace and a second
root workspace. That is exactly why workspaces come from config instead of from a convention.

**Two traps worth naming.** On a Mac, `$HOME/.openclaw/master-files` exists and is **not** the
reference root; it holds analytics, design library and tune-up material. On a Hostinger VPS,
`/data/.openclaw/master-files` likewise exists and is **not** the reference root. The reference root
is the `References 4 Bootstrap/` directory in the table above.

### 2a. How the reference root is resolved

`resolve_reference_root()` in `scripts/compact-bootstrap.py`, first match wins:

1. `$OPENCLAW_BOOTSTRAP_REFERENCE_ROOT`
2. `agents.defaults.bootstrapReferenceRoot` in `openclaw.json`
3. the first of these that **exists** on the box:
   `$OPENCLAW_MASTER_FILES_DIR/References 4 Bootstrap`,
   `$HOME/Downloads/openclaw-master-files/References 4 Bootstrap`,
   `$HOME/openclaw-master-files/References 4 Bootstrap`,
   `/data/openclaw-master-files/References 4 Bootstrap`,
   `$OC_ROOT/master-files/References 4 Bootstrap`
4. the platform default, created if nothing exists yet

Probing for what exists rather than branching on a guessed platform is deliberate: the three live
layouts do not follow one rule, and a box whose master-files root sits somewhere a prefix list did
not anticipate would otherwise get a silent blind spot.

---

## 3. What moves, and why: one decision per section

Size is the trigger, never the reason. Every section gets a class and a recorded reason, and the tool
prints both for every section it looked at.

| Class | Meaning | What happens |
|---|---|---|
| **script** | Stamped into the file by a fleet script | Never moved here. Made lean at the source. See section 9. |
| **pointer** | Already compacted | Left alone. |
| **hot** | Fires every turn | Never auto-moved. Becomes a proposal. |
| **archive** | Historical: what happened, not what to do | Moves to `history.md`. |
| **dedupe** | A reference doc already carries a section with this heading | Moves, and a reconcile proposal is written. |
| **cold** | Procedural or reference detail | Moves. |

**Hot** is anything the agent must obey without being told to look it up: reflexes, non-negotiables
and enforcement rules, routing trigger tables, safety and credential rules, identity essentials, and
the pointer table itself. Hot stays no matter how big the file gets.

**Cold** is anything that only matters once you are already doing that specific job: procedures and
step lists, tables of detail (model names, endpoints, field lists), anything whose first line is
effectively "when you are building X".

**Archive** is dated and finished: self-correction logs, incident write-ups, install receipts,
root-cause notes, timelines. It is evidence, not instruction. `history.md` takes archive-class content
**and nothing else**. Never file a live procedure there.

**Dedupe** is the same heading already living in a reference doc. Both copies are kept verbatim under
separate anchors and a reconcile proposal is written. See section 6.

The test for hot versus cold: *if this were missing, would the agent do the wrong thing on an ordinary
turn?* Yes, hot. Only wrong once it is already deep in that one job, cold.

Worked example. A nine-step orchestration procedure that only applies after the owner says a specific
phrase splits cleanly: the **trigger phrase is hot** and stays in the core inside the pointer, the
**nine steps are cold** and live in the reference. The agent still reacts to the phrase; it just reads
the steps when the phrase actually fires.

The class rules are the six tables at the top of `scripts/compact-bootstrap.py`. Disagreeing with a
classification is an edit to a rule table, never a hand edit to a bootstrap file.

---

## 4. Verbatim or nothing

Moved text is copied **byte for byte**. Not paraphrased, not tightened, not merged with a similar
section elsewhere, not cleaned up in passing.

If two sections share a heading but differ in content, they stay two separate blocks with two separate
anchors. Merging them is a rewrite of the owner's words. That is section 6's job, and it is a
proposal, never an edit.

The proof is the sha256 in the ledger, taken over the exact bytes written to the reference doc. Each
stored block is bracketed so those bytes stay recoverable even after later appends:

```
<!-- source: workspace/AGENTS.md:1091-1133; migrated 2026-09-18; sha256 8d6d39a2... -->
<a id="big-project-mode-v2"></a>
## BIG PROJECT MODE (v2)
...verbatim...
<!-- end-block big-project-mode-v2 -->
```

Everything between the `<a id>` line and the `<!-- end-block -->` line hashes to the ledgered digest.
`compact-bootstrap.py --check` re-hashes it and fails on any drift.

---

## 5. Where it lands: existing doc first, always

The destination is decided by topic, not by filename string matching, in this order:

1. **Archive class** goes to `history.md`. Nothing else ever does.
2. **A destination override** in the tool's `TOPIC_OVERRIDES` table, if one has been set for that
   topic.
3. **An existing doc that already has a section with this heading.** The tool builds its map by
   reading the H1 and every H2 of every doc under the reference root, so the map is derived from the
   docs themselves and can never go stale.
4. **The existing doc with the strongest topic overlap**, scored on the shared terms between the
   section and that doc's headings. Two or more shared terms wins.
5. **A new doc**, only when nothing above matched.

Rules that bind every one of those steps:

- **Append under a new H2 that is the moved heading, verbatim.** The heading is how people and greps
  find it; changing it breaks both.
- **Never create a near-duplicate doc.** No `ghl.md` beside `tools/ghl.md`. Before creating anything
  the tool looks for an existing doc with the same or an overlapping stem and uses that one instead.
- **A new doc gets registered twice**: as a bullet in `INDEX.md` at the reference root, and as a row
  in the bootstrap file's own `## On-demand references` pointer table. A reference nobody is routed to
  is a reference nobody reads.
- **Anchors are explicit.** An `<a id="...">` is written above the moved heading, so anchors never
  depend on how a renderer slugifies an emoji or a dash.

### 5a. The collision rule

Two blocks can carry the same heading and different words. That is a **collision**, and it is never
resolved by picking a winner, merging them, or starting a new doc to keep them apart.

1. The arriving block goes into **the same doc** that already has that heading.
2. It gets a **suffixed anchor** so both are separately addressable: `#big-project-mode-v2` for the one
   that was already there, `#big-project-mode-v2-2` for the one that just arrived.
3. Both stay **verbatim**. Neither is edited.
4. A **reconcile proposal** with a diff between them is written to `pending-updates.md`. Section 6
   covers that.

A suffix therefore **means something**: it says a real collision happened. That is why the doc's own
H1 title is deliberately not counted when picking an anchor. A brand-new doc is titled after the block
it was created for, and counting that title would stamp a `-2` on every first move, making a real
collision indistinguishable from a fresh file.

The case this rule was written from: a first pass moved a section into a brand-new document because
another doc already held a differently worded block under that exact heading, and a new file looked
like the tidy way to avoid a duplicate title. That was wrong twice over. It created a near-duplicate
doc for a topic that already had a home, and it split one topic across two files, so a reader who
opened the original doc on that heading would never learn the other version existed. Same heading
means same document. A suffixed anchor is how two versions coexist until the owner decides which
survives.

---

## 6. Improve-on-move: the two-copy rule

Moving content is a good moment to make it stronger. It is never the moment to change it quietly.

**Copy one, always first: verbatim.** The reference doc gets the exact bytes, anchored, ledgered with
its sha256. This happens before any improvement is even described.

**Copy two: a proposal, never an edit.** Any tightening, dedupe, corrected fact, or stronger wording
is written to `pending-updates.md` as a diff against the verbatim copy. It is not applied. The owner
approves or rejects it. Until then both blocks stay exactly as they are.

The tool writes dedupe proposals itself: when it files a block whose heading already exists in the
destination, it emits a unified diff between the two copies under a heading naming both anchors.
Improvements that need judgement are written by hand into the same file, in the same shape: state what
changes, why, and show the diff against the verbatim block.

**Approving one.** A proposal is a file for a human to read, and applying it is a deliberate act.
Where a box carries the writer-review guard (`core-reference-guard.py`, an operator-box tool that this
repo does not ship to clients), approval is by exact hash and executes nothing by itself:

```sh
python3 "$OC_ROOT/scripts/core-reference-guard.py" approve-updater \
  --file /absolute/path/to/reviewed-writer.sh \
  --sha256 EXACT_REVIEWED_SHA256 \
  --reviewed-core-writers
```

```sh
python3 "$OC_ROOT/scripts/core-reference-guard.py" run-approved-updater \
  --file /absolute/path/to/reviewed-writer.sh
```

A hash mismatch, a missing contract line, a missing attestation, broken shell syntax, or a modified
approved copy all refuse to run. On a box without that guard the proposal is applied by hand after
review, and the review is still the gate. Either way, nothing in the weekly job ever applies a
proposal on its own.

---

## 7. The pointer writing standard

Exactly four lines. No more, ever. One standard, written by one function
(`build_pointer()` in `scripts/bootstrap-pointerize.py`), used by both tools.

```
<the original heading, verbatim>
<one sentence saying what is inside>
**Triggers:** <the exact trigger phrases or situations that should make you open it>
**Full text:** <ONE absolute path> §<anchor>
```

Filled example, an owner-authored section moved by `compact-bootstrap.py`:

```
## BIG PROJECT MODE (v2)
9-step procedure: ECHO-BACK GATE (always first); Orchestrator pastes, owners send files; Identical bytes first, unique assignment last.
**Triggers:** the owner says "big project mode" or hands you a large, multi-part build with many deliverables
**Full text:** /data/openclaw-master-files/References 4 Bootstrap/operations.md §big-project-mode-v2
```

Second example, showing the shape for a tool topic:

```
## Zoom meeting automation
How to create, list and delete meetings, which credential each call needs, and the retry rule for a 429.
**Triggers:** scheduling, listing or cancelling a Zoom meeting, or debugging a Zoom API error
**Full text:** /Users/<clientuser>/Downloads/openclaw-master-files/References 4 Bootstrap/tools/zoom.md §zoom-meeting-automation
```

Binding rules:

- **Line 1 is the heading, unchanged.** Greps and readers still find it where it always was.
- **Line 2 says what is inside**, not why it left. A step list describes itself best through its own
  step titles.
- **Line 3 is the whole reason the pointer works.** A pointer without triggers is a dead end the agent
  never opens. Use the words that actually appear in a request. For a script-owned block stamped by
  the roll, this line carries the prohibitions and hard gates that must keep binding inline, since a
  pointer that hides a prohibition is a downgrade.
- **Line 4 is ONE absolute path.** Never two paths, never "x.md and y.md", never a relative path,
  never `~`. The stamper refuses to write a relative pointer and the validator resolves literal
  absolute paths only.

---

## 8. How pointers are checked

Two layers, and they check different things. Neither writes to a bootstrap file.

**The validator** enforces the size targets, the `<!-- CORE_REFERENCE_POLICY_V1 -->` stamp, marker
pairing and fence balance, that every backticked absolute path exists, and that every
`**Full text:**` pointer resolves:

```
python3 scripts/validate-core-references.py --workspace <workspace> --from-config <openclaw.json>
```

**`compact-bootstrap.py --check`** verifies what the validator cannot see:

```
python3 scripts/compact-bootstrap.py --check
```

- (a) the **anchor** named by the pointer is really in the target doc
- (b) the **ledgered sha256** still matches the block sitting in the reference doc, which catches a
  block edited after the move
- (c) no pointer targets an **empty file**

It reports one line per pointer and per ledgered block, and exits non-zero on any failure. Ledger
entries written before this tool existed carry no anchor and are reported as **not verifiable**, which
is the honest answer rather than a false pass. `--apply` runs the check automatically afterwards.

**A negative from either layer is only worth as much as its control.** `--check` returns `ok` on a
healthy tree, and the unit test proves that before it proves any failure, so a `FAIL` is a fact about
the box and not a broken instrument.

---

## 9. Script-owned blocks are fixed in the repo, never on the box

Most of a live `AGENTS.md` is not the owner's prose. It is stamped in by fleet scripts, and **they
re-inject it in full on their next run**. Deleting it by hand buys nothing and loses the marker that
stops the next update appending a second copy.

Script-owned by marker:

- `<!-- BEGIN skill:NN-...:agents -->` ... `<!-- END ... -->`, from skill installers
- `<!-- BEGIN SKILL38: ... -->` ... `<!-- END ... -->`, skill 38 runtime steps
- `<!-- skill:NN-...:core-update-applied -->`, one-line receipts. Removing one makes the next skill
  update paste the whole instruction block back in.
- any `<!-- NAME_Vn -->` sentinel stamped by `apply-fleet-standards.sh`. The tool matches the
  **shape**, not a list of names, so a reflex that ships next month is covered the day it lands.

Script-owned by heading: anything saying "stamped by apply-fleet-standards.sh, do NOT edit manually",
`## Managed skill blocks (do not remove)`, `## UPDATE PENDING ...`, and the `## Step N.N ...` ladder.

`<!-- CORE_REFERENCE_POLICY_V1 -->` is none of these. It is the stamp the validator looks for. Leave
it alone and never wrap content in it.

**These are made lean at the source, by the writer.** `scripts/bootstrap-pointerize.py` stamps each
managed block as a pointer during the roll and writes the verbatim full text to
`<master-files>/bootstrap-references/<FILE>`, fenced by its own `<!-- BEGIN REF ... -->` pair. Marker
names are unchanged, so every idempotency guard, pair-balance check and dedup pass keeps working. A
box that was already fat converges through the same code path: the sweep lifts the existing full text
into the reference file before replacing the block. The box-level switch is
`config/bootstrap-pointer.conf.example`, default `pointer`.

**A box operator still does NOT:**

- hand-move, hand-trim or delete a script-owned block out of any bootstrap file
- remove a `core-update-applied` sentinel to save space
- edit a stamped block in place to shorten it
- run `compact-bootstrap.py` with a rule table loosened to let it touch those blocks

`compact-bootstrap.py` enforces this three ways: marker match, heading match, and a blanket guard that
refuses to move any section containing an HTML comment of any kind. If all three were wrong, the worst
outcome is that something stays put.

---

## 10. The ledger, and backups

Every move appends to `migration-map.json` at the reference root:

```json
{
 "file": "AGENTS.md",
 "start_line": 1091,
 "end_line": 1133,
 "heading": "## BIG PROJECT MODE (v2)",
 "action": "relocated to on-demand reference",
 "destination": "operations.md#big-project-mode-v2",
 "sha256": "8d6d39a2...",
 "workspace": "workspace",
 "class": "cold",
 "migrated_utc": "2026-09-18T10:41:00+00:00"
}
```

`workspace`, `class` and `migrated_utc` are recorded because a box can have more than one workspace
holding a file called `AGENTS.md`, and the ledger has to say which one, and which decision rule moved
it. No existing entry is ever rewritten.

Keep the pre-move version in `previous/` **only when the file has no other rollback**:

- a bootstrap file tracked in a git repo gets **no backup file**. Git is the rollback.
- every untracked bootstrap file gets `previous/<NAME>-<workspace>-<YYYYMMDD-HHMMSS>.md` written
  before anything changes, and the tool prints the path.

No backup goes anywhere else. Not beside the original, not as a `.bak`.

---

## 11. The gate

The validator must be green before and after, the one allowed exception being a size error on a file
being reduced right now. `--apply` refuses to run if the validator is failing for **any** other
reason. Fix the real error first: compacting on top of a broken file only hides it.

**A move that touches a hot section is never applied automatically.** When movable content runs out
and the file is still over target, the tool writes a proposal into `pending-updates.md` listing the
hot candidates and the script-owned remainder, and moves nothing. That proposal is a question for the
owner, not a plan. It waits.

---

## 12. Cadence, and the switch

Both jobs are registered by `scripts/ensure-pipeline-crons.sh`, which `install.sh` and
`update-skills.sh` both call, so every box gets them. Both are **COMMAND-kind crons**: pure shell and
`python3`, zero LLM tokens, no delivery to any chat, and **no model name anywhere in either job**.
Neither invokes a model at all, which is why neither can hardcode one. The weekly wrapper reads
`agents.defaults.model` and prints it purely so that anyone who ever converts the job to an agent cron
uses the box's own configured default rather than pasting a model name into a script.

**Daily, zero tokens.** `bootstrap-validate-daily` at 05:00, running
`scripts/bootstrap-validate-daily.sh`. It runs the validator against every workspace, prints sizes
against the live caps read from `openclaw.json`, and exits non-zero on any failure. It never writes to
a bootstrap file.

**Weekly.** `bootstrap-compact-weekly` at **Sunday 04:30 America/New_York**, running
`scripts/bootstrap-compact-weekly.sh`. It runs `compact-bootstrap.py` across every workspace the box
declares, then re-verifies every pointer and every ledgered block. **It only acts when a file is over
its target**; under target it measures and stops.

The timezone is part of the schedule, not decoration:

| Job | Schedule |
|---|---|
| proactive-suggestions | Sat 23:00 |
| weekly-tune-up | Sun 02:00 |
| weekly-onboarding-update (the skill update) | Sun 03:00 America/New_York |
| **bootstrap-compact-weekly** | **Sun 04:30 America/New_York** |

04:30 lands after everything else that rewrites these files. "04:30 local" would not: on a box set to
another zone it can land hours *before* 03:00 New York, compacting a file the skill update is about to
rewrite. So the zone travels with the expression, and a CLI that rejects `--tz` is retried without it
rather than losing the registration. Re-check that order whenever a weekly job is added or moved.

### 12a. The switch

The weekly job is gated, and it **defaults to report**. Resolution order, first match wins:

1. `$OPENCLAW_BOOTSTRAP_COMPACT_MODE`
2. `$OC_CONFIG/bootstrap-compact.conf` (one word)
3. `agents.defaults.bootstrapCompactMode` in `openclaw.json`
4. `report`

| Value | Behaviour |
|---|---|
| `report` | **Default.** Measure, classify, print the plan. Write nothing at all. |
| `apply` | Perform the plan. Hot sections and script-owned blocks are still never touched. |

A box's first scheduled week therefore produces a reviewable plan rather than a surprise edit. Read
the report, confirm the destinations, then flip the switch:

```sh
echo apply > "$OC_ROOT/bootstrap-compact.conf"
```

An unrecognised value is treated as `report` and warns. Honouring a typo as `apply` would write to a
bootstrap file nobody authorised, which is the exact failure this switch exists to prevent. The
template and the full rationale are in `config/bootstrap-compact.conf.example`.

This switch is independent of `config/bootstrap-pointer.conf.example`, which governs the other half of
lean bootstrap: how the roll stamps its own managed blocks.

---

## 13. The checklist

In order. Stop at the first thing that fails.

1. **Measure.** `python3 scripts/compact-bootstrap.py` (dry run is the default). Nothing over target,
   done.
2. **Validator green?** Anything failing that is not a size error, fix that first. `--apply` will
   refuse anyway.
3. **Read the decision table.** The dry run prints a class and a reason for every section. Disagree
   with one? Edit the rule tables at the top of the tool. Never hand-edit the bootstrap file.
4. **Check the destinations.** Every move should name an existing doc. A `NEW DOC` line means nothing
   covered that topic. Confirm that is true before applying.
5. **Confirm nothing script-owned is in the plan.** It should be impossible. Check anyway.
6. **Apply.** `--apply` backs up if there is no git rollback, moves verbatim, writes the pointer,
   appends the ledger, registers any new doc in `INDEX.md` and the pointer table, writes dedupe
   proposals, re-runs the validator, then runs `--check`.
7. **Read the after report**, including the `--check` result.
8. **Spot-check one move by hand.** Open the reference doc, find the anchor, confirm the text is the
   owner's and unchanged.
9. **Still over target?** Read the proposal in `pending-updates.md`. Hot sections and script-owned
   blocks are decisions, not chores. Take them to the owner. Do not move them.
10. **Never commit a box's bootstrap file on the owner's behalf.** Leave the diff.

---

## Related

- `scripts/compact-bootstrap.py` and `tests/unit/compact-bootstrap.test.sh`
- `scripts/bootstrap-pointerize.py` and `tests/unit/bootstrap-pointerize.test.sh`
- `scripts/validate-core-references.py`, `scripts/bootstrap-validate-daily.sh`,
  `scripts/bootstrap-compact-weekly.sh`
- `config/bootstrap-compact.conf.example`, `config/bootstrap-pointer.conf.example`
- `docs/OPERATOR-MAINTENANCE.md`
