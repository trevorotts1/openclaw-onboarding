# PD-305 — An approval names its gate, once

**Unit:** PD-305 · **Lane:** FL34 · **Repository:** trevorotts1/openclaw-onboarding
**Branch:** `pd/fl34-approvals--hold-d33`
**Commit:** see `git rev-parse HEAD` in the final message (the branch head is this build's commit; the
report cannot carry its own sha without a second commit, so the sha is in the final message and in the
push receipt below).

## Held by decision D-33 — built and staged, not merged

D-33 default, quoted exactly from `06-DECISIONS-FOR-TREVOR.md`:

> ### D-33 — built and staged, not merged until yes
> - **Question:** What makes an owner message an approval for one gate (PD-305, PD-305b, PD-309)?
> - **Options:** must name the gate, one message one gate / today's rule
> - **Default:** The message must contain the gate name, and one message approves one gate. Needs the
>   Command Center to return message text (PD-305b). Stage; not merged until yes.
> - **Units waiting on a yes:** PD-066, PD-203, PD-305, PD-305b, PD-309, PD-316b

Status: **STAGED, NOT MERGEABLE** — it sits behind an unanswered decision. Per the D-33 default it is
built and pushed; it must not be merged until Trevor answers yes.

## Pre-existing commits on this branch, and their owners

Measured with `git log --oneline origin/main..HEAD` before this build (then the lane base was merged in):

| Commit | Owner | What it is |
|---|---|---|
| `a152d858f` | this lane (merge) | Merge of `origin/pd/fl34-approvals` into `pd/fl34-approvals--hold-d33` |
| `edda7fa8c` | PD-004a (ACCEPTED, QC PASS) | PD-004a qc fix — board row must echo the requested id |
| `190dc0c00` | PD-004a (ACCEPTED, QC PASS) | PD-004a: resolve an owner message id to the message the client sent |
| `1a476d2cb` | batch merge train | Merge pull request #3163 from `batch/openclaw-onboarding/20261112-172032` |
| `9e3bcf93a` | batch merge train | Merge pull request #3159 from `work/skill6-finish-hybrid-v111` |

### Lane base merged in during this build

The lane's base branch `origin/pd/fl34-approvals` had moved ahead of this hold branch. It was merged into
this branch (`git merge --no-edit FETCH_HEAD`, no conflicts) so PD-305 builds on the current base:

| Commit | Owner | What it is |
|---|---|---|
| `3b3464375` | PD-916 (ACCEPTED, QC PASS) | Build report with the sha, the before/after proof and the push receipt |
| `61d82494d` | PD-916 (ACCEPTED, QC PASS) | Style-pick passable test stages the owner message text PD-912 requires |
| `99c98880a` | PD-912 (ACCEPTED, QC PASS) | The three approval consumers require gate-naming owner message text |
| `8928f6b02` | PD-907 (ACCEPTED, QC PASS) | Merge `origin/pd/fl34-approvals` into the lane |
| `04d93d67e` | PD-907 (ACCEPTED, QC PASS) | Approvals require gate-naming message text, not just an id |
| `1e7065d53` | PD-907 (ACCEPTED, QC PASS) | Fixtures stage the owner message text an approval now needs |

**The PD-907 / PD-912 split is not re-litigated here.** Those units already handled the
spec-versus-test conflict that used to BLOCK PD-305. Measured, not assumed: PD-907 retargeted all three
named out-of-lane tests to stage the owner message text
(`tests/negative_fixtures.py`, `tests/test_negative_fixtures.py`, `tests/test_fix29_style_pick_human_stage.py`,
`tests/test_executor_dispatch.py`), and PD-912 added `text_names_gate` and `verify_with_gate_text`.
PD-305 builds only its own remaining rows on top of that.

## Files changed by this build (all three are PD-305's owned paths)

1. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/approvals.py`
2. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/cc_board.py`
3. `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_pd_approvals.py`

No file outside these three was edited.

## What changed, against the unit's five clauses

Clause 1 (the gate-naming text check) and the consumer wiring were already built by PD-912/PD-916 on the
lane base. Measured with `grep -c` before writing anything: `def text_names_gate` and
`def verify_with_gate_text` both present, `approvals_used` absent (0 occurrences), `state.json board.task_id`
absent (0), `"role" in data` gateway branch present (1). PD-305 therefore builds items 2, 3, 4, 5, the
clause-1 board-text half, and its own A1 test.

| Clause | Change made here |
|---|---|
| (1) text names the gate + board returns `{id: text}` | `cc_board.list_owner_message_ids` now returns `{message_id: text}` when the endpoint supplies row text, and still a `frozenset` of ids when it does not. Membership (`owner_msg_id in result`) is unchanged for every existing consumer. `approvals._default_board_text_resolver` reads the board through that same route; an ids-only answer is UNDETERMINED. `approvals` reuses the single oracle answer already fetched, so no second request per approval. |
| (2) `working/checkpoints/approvals_used.json`, one id one gate | New `APPROVALS_USED_REL`, `check_approval_not_reused`, `_record_approval_used`, `_read_approvals_used`. `verify_with_gate_text` records `(owner_msg_id, gate)` on acceptance; the same id on a SECOND gate raises `AF-FORGED-APPROVAL`. The same gate twice is idempotent. An unreadable or unwritable ledger refuses the approval (fail-closed). |
| (3) task id from `state.json` `board.task_id` first | New `resolve_cc_task_id`: `state.json` `board.task_id` first, `process_manifest.json` `cc_task_id` only when they agree (or when only the manifest has a value). Both present and different → `""` (UNDETERMINED) and logs `task_id.sources_disagree`; the oracle then returns None rather than falling through to the manifest-only helper. `_cc_board_oracle` now uses it. |
| (4) gateway accepts `is_owner: true` only | Removed the `role` branch from `_gateway_owner_oracle`. A gateway answer with a role and no `is_owner` flag is now UNDETERMINED, never an approval. |
| (5) self-grant words match whole words | New `_self_grant_marker` uses the shared whole-token regex. `"via "` (with the trailing space) became `"via"`. `validate_schema` calls it. `SELF_GRANT_MARKERS` keeps every marker it had. |

## Commands run, and their results

Builder does not run the acceptance suite (rule 9); QC does. These are the direct proofs of the logic, run
with `TMPDIR=/Volumes/mac mini m4/swarm-contract/pd-fix/tmp`, `python3 -I`, stub transport, no network.

```
$ python3 -I -m py_compile presentation_job/approvals.py cc_board.py tests/test_pd_approvals.py
SYNTAX-OK rc=0

$ python3 -I   # import + whole-word markers
import OK
markers: ('executive strategy', 'via', 'directive', 'auto-approved', 'self', 'auto_approved', 'producing', 'builder')
self_grant(Herself Ordonez): None
self_grant(builder (executive strategy)): executive strategy
self_grant(Trevor): None
text_names_gate exact: True
text_names_gate longer: False
```

A1 acceptance row, proven both directions before and after:

```
# BEFORE this build the ids-only shape was accepted. AFTER:
ROW1 ("ok thanks") refused:
  AF-FORGED-APPROVAL: owner message 'msg-a' does not name gate 'AF-STYLE-UNPICKED'
  (text='ok thanks') ...
ROW2 ("approve AF-STYLE-UNPICKED") accepted once: gate=AF-STYLE-UNPICKED
ROW2 ledger: {'msg-a': 'AF-STYLE-UNPICKED'}
ROW2b same id, second gate refused:
  'one gate' in message: True
  AF-FORGED-APPROVAL: owner_msg_id 'msg-a' already approved gate 'AF-STYLE-UNPICKED';
  it may not also approve 'AF-OCR-READBACK'. One owner message approves one gate ...
IDEMPOTENT same-gate: AF-STYLE-UNPICKED
ROW3 ids-only oracle refused: 'ids-only' in message: True
```

Board oracle shapes and fail-closed behaviour:

```
ids-only type: frozenset | membership: True | is frozenset: True
text shape type: dict | val: {'id-1': 'approve AF-X', 'id-2': 'hi'}
membership on dict: True
http 500 -> None
empty tid -> None
```

Board text wired through `resolve_owner_message` (one fetch per approval):

```
board-text row: {'msg_id': 'msg-a', 'chat_id': '', 'text': 'approve AF-STYLE-UNPICKED', 'received_at': ''}
ids-only board -> resolve returns: None
text-oracle accept: AF-STYLE-UNPICKED
ids-only refused: True
wrong text refused: True
```

Gateway fallback, `is_owner` only:

```
is_owner true -> True
role-only -> None
is_owner false -> False
```

Task-id source (item 3), including the case where the two files contradict each other — the failure mode
that would otherwise fall through to the manifest alone and silently pick one:

```
[approvals] task_id.sources_disagree
task_id: ''
oracle on disagreement: None
agree task_id: same
state-only: s
```

Existing consumers unchanged (this is the regression control the clause-1 change could have broken):

```
split_verified ok: ['G1'] | rejections: 0
verify() still accepts: G1
positive control (PD-907/912 shape, resolver wired): P4-COPY
ids-only refused OK
rsd imports approvals: True
```

Out-of-lane tests: none edited and none needed. PD-907 already retargeted the three that used to assert
ids-only acceptance; measured by reading them, they now stage owner message text
(`inbound_messages.jsonl`) and their flip rows assert the ids-only shape is REFUSED. The one remaining
ids-only assertion on the branch is `test_skip_approval_authenticity.py:397-406`, which asserts the
`owner_message_ids_match` ROUTE still answers with an ids id-set for a board that supplies no text — that
is a true statement about the route (this build keeps returning a `frozenset` in exactly that case), not an
assertion that an approval is accepted from ids alone. It is not a PD-305 blocker and was not touched.

## Files changed, measured

```
 .../role-library/presentations/scripts/cc_board.py |  31 ++-
 .../scripts/presentation_job/approvals.py          | 279 ++++++++++++++++++---
 .../scripts/tests/test_pd_approvals.py             | 179 +++++++++++++
 3 files changed, 451 insertions(+), 38 deletions(-)
```

Every number above is copied from a command's own output.

## Times

Build finished 2026-11-12, 10:52 PM Eastern.
