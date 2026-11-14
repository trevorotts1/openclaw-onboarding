# PD-916 BUILD REPORT

- Unit: PD-916 (lane FL34)
- Branch: `pd/fl34-approvals`
- Worktree: `<scratchpad>/worktrees/onboarding/FL34`
- Head before editing: `61d82494d` was created from `99c98880a` (PD-912). Live head at edit time, `git log --oneline -8`:

```
61d82494d (after) PD-916: style-pick passable test stages the owner message text PD-912 requires
99c98880a PD-912: the three approval consumers require gate-naming owner message text
8928f6b02 PD-907: merge origin/pd/fl34-approvals into the lane
04d93d67e PD-907: approvals require gate-naming message text, not just an id
1e7065d53 PD-907: fixtures stage the owner message text an approval now needs
edda7fa8c PD-004a: qc fix — board row must echo the requested id
190dc0c00 PD-004a: resolve an owner message id to the message the client sent
1a476d2cb Merge pull request #3163 from trevorotts1/batch/openclaw-onboarding/20261112-172032
```

## What was wrong

`tests/test_f5_style_pick_passable.py` (the only copy, under
`23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/`)
carried a FOURTH ids-only test of the same class PD-907 flipped three of:

- helper `_stub_oracle(monkeypatch, ids)` at line 155 stubbed only
  `approvals_mod._cc_board_oracle` — ids, no message text;
- `TestStylePickRecorder::test_it_writes_the_shape_the_engine_gate_accepts`
  at line 349 called `_stub_oracle(monkeypatch, ["owner-msg-42"])` then asserted
  `ok is True` — i.e. that `Engine._style_choice_authentic()` ACCEPTS a resolvable
  id with no owner text.

PD-912 (`99c98880a`) turned that same gate into
`_approvals.verify_with_gate_text(approval, self.run_dir)` (phases.py:3899), which
resolves the message body and refuses AF-FORGED-APPROVAL when no text can be read.
So the assertion was asserting the pre-PD-912 contract.

## Files changed (one file, test-only)

- `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests/test_f5_style_pick_passable.py` (+20 −4)

`approvals.py`, `phases.py`, `run_signature_deck.py` untouched, as ordered.

## Old helper vs new helper

OLD (head 99c98880a, line 155):

```python
def _stub_oracle(monkeypatch, ids):
    """Same stub tests/test_fix29_style_pick_human_stage.py uses: the Fix 32
    Command-Center oracle resolves exactly these owner message ids."""
    monkeypatch.setattr(
        approvals_mod, "_cc_board_oracle",
        lambda run_dir=None: frozenset(ids) if ids is not None else None)
```

NEW (61d82494d, line 155):

```python
def _stub_oracle(monkeypatch, ids, *, text: str | None = None):
    """Same stub tests/test_fix29_style_pick_human_stage.py uses: the Fix 32
    Command-Center oracle resolves exactly these owner message ids.

    PD-912/PD-305: an id alone never proves an owner decision -- the oracle must
    also return the owner message TEXT naming the gate. Pass text=None to keep
    the ids-only shape the contract refuses."""
    monkeypatch.setattr(
        approvals_mod, "_cc_board_oracle",
        lambda run_dir=None: frozenset(ids) if ids is not None else None)
    if ids is not None and text is not None:
        monkeypatch.setattr(
            approvals_mod, "BOARD_TEXT_RESOLVER",
            lambda mid, _run_dir=None: (
                {"msg_id": mid, "chat_id": "owner-chat", "text": text,
                 "received_at": ""}
                if mid in ids else None),
            raising=False)
```

Call sites:

```python
# line 358-359 — the positive case stays positive
_stub_oracle(monkeypatch, ["owner-msg-42"],
             text="approve P-STYLE-PICK variant B")
ok, denial = _engine_accepts_choice(rd, choice, ["A", "B", "C"])
assert ok is True, denial

# line 398-403 — the negative now fails on the ID, not on absent text
_stub_oracle(monkeypatch, ["owner-msg-42"],
             text="approve P-STYLE-PICK variant A")
ok, denial = _engine_accepts_choice(rd, choice, ["A", "B", "C"])
assert ok is False
# Denied for the unresolvable id, NOT for any absence of message text.
assert "not-a-real-id" in denial
assert "does not resolve to a real" in denial
```

## Proof — exact commands and output

All commands run from
`.../presentations/scripts`, with the temporary directory redirected under `<scratchpad>/tmp`.

1. BEFORE the edit (head 99c98880a) — the fourth ids-only test already failed
   against PD-912's contract:

```
$ python3 -m pytest tests/test_f5_style_pick_passable.py -q -p no:cacheprovider
>       assert ok is True, denial
E       AssertionError: style choice owner_msg_id 'owner-msg-42' failed authenticity verification:
        AF-FORGED-APPROVAL: approval for gate 'P-STYLE-PICK' references owner_msg_id
        'owner-msg-42', which resolves to a real message but whose TEXT could not be read
        (ids-only oracle / no inbound message log). An id proves a message exists, never what
        the owner approved — DENIED.
E       assert False is True
tests/test_f5_style_pick_passable.py:351: AssertionError
1 failed, 30 passed in 8.59s
```

2. AFTER the edit — the file at new head, all green:

```
$ python3 -m pytest tests/test_f5_style_pick_passable.py -q -p no:cacheprovider
...............................                                          [100%]
31 passed in 8.27s
```

3. The file plus its sibling, to show no collateral:

```
$ python3 -m pytest tests/test_f5_style_pick_passable.py tests/test_fix29_style_pick_human_stage.py -q -p no:cacheprovider
...................................................                      [100%]
51 passed in 68.19s (0:01:08)
```

4. STASHED — the fix removed, line 351 fails again, so the flip follows the rule:

```
$ git stash push -m "PD-916 stash" -- .../tests/test_f5_style_pick_passable.py
Saved working directory and index state On pd/fl34-approvals: PD-916 stash
$ python3 -m pytest tests/test_f5_style_pick_passable.py::TestStylePickRecorder::test_it_writes_the_shape_the_engine_gate_accepts -q -p no:cacheprovider
[approvals] resolve.board_has_no_text
[approvals] resolve.no_text_source
FAILED tests/test_f5_style_pick_passable.py::TestStylePickRecorder::test_it_writes_the_shape_the_engine_gate_accepts
1 failed in 0.35s
$ git stash pop      # restored; git status --porcelain showed the one modified file
```

## Commit, push, remote sha

```
$ git commit ...
61d82494d PD-916: style-pick passable test stages the owner message text PD-912 requires
   1 file changed, 20 insertions(+), 4 deletions(-)

$ git push origin pd/fl34-approvals
To https://github.com/trevorotts1/openclaw-onboarding.git
   8928f6b02..61d82494d  pd/fl34-approvals -> pd/fl34-approvals

$ git ls-remote origin refs/heads/pd/fl34-approvals
61d82494d34b7a57a02bf20f3228014264abb396	refs/heads/pd/fl34-approvals
```

Remote sha `61d82494d34b7a57a02bf20f3228014264abb396` == local commit sha
`61d82494d`: the push landed. (The same push also carried `99c98880a` PD-912,
which the remote did not have yet; the remote moved from `8928f6b02` to
`61d82494d`.) This report is committed on top of that.

## Lane hunk attribution on this branch

| Unit | Commit | What it put here |
|---|---|---|
| PD-004a | `190dc0c00` | `presentation_job/approvals.py` + `tests/test_pd_approvals.py`: resolve an owner message id to the message the client sent (`resolve_owner_message`, `_file_row`, `_message_row`) |
| PD-004a | `edda7fa8c` | `presentation_job/approvals.py`: qc fix — the board row must echo the requested id |
| PD-907 | `1e7065d53` | `tests/negative_fixtures.py`: fixtures stage the owner message text an approval now needs |
| PD-907 | `04d93d67e` | `tests/test_negative_fixtures.py`: approvals require gate-naming message text, not just an id |
| PD-907 | `8928f6b02` | merge of `origin/pd/fl34-approvals` into the lane |
| PD-912 | `99c98880a` | `presentation_job/approvals.py` (`text_names_gate`, `verify_with_gate_text`), `presentation_job/phases.py` (`_style_choice_authentic` calls `verify_with_gate_text`), `run_signature_deck.py` |
| PD-916 | `61d82494d` | this unit: `tests/test_f5_style_pick_passable.py` only |
