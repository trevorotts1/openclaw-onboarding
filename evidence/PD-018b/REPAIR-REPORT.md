# PD-018b — REPAIR REPORT

- **Unit:** PD-018b (lane FL05), repair of the FAIL at `414c715ab0a761911570c6274a1acf477a43b41b`
- **Branch:** `pd/fl05-engine-reporting`
- **Repair commit:** `aa506ba7e3748d05ba29f45d7015d3d08eafce41`
- **Base:** `c40b6744da`
- **Report commit:** the commit that adds this file (branch head after it; remote proof in the build-room return message)
- **Files touched by this repair (4):**
  - `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/presentation_job/phases.py`
  - `…/scripts/tests/test_engine_client_report.py`
  - `…/scripts/tests/test_pd_engine_client_copy.py`
  - `…/scripts/tests/test_pd_report_sanitize.py`

No file outside PD-018b's named set was touched. `report.py` was **not** modified by this repair: every defect was either test-side or in `phases.py`'s count helper.

## Dependency: PD-018a's manifest is not on this branch (stated, not fixed here)

`universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json` at this branch's base and at `origin/main` is the OLD manifest: 56 phases, **0** carrying `client_label`, **0** carrying `client_visible`. PD-018a's retokened manifest exists only on `pd/fl04-manifest` (`b78085f9e`: 56 phases, **56** with `client_label`, **56** with `client_visible`, 18 of them `client_visible: true`). That is an unmerged-accepted ancestor, not a defect in this unit, and it was **not** added to this branch.

All behavioural proof below was run in an integration tree that carries this branch plus only PD-018a's three manifest artifacts (manifest, `MANIFEST-SOURCE.txt`, `_content-manifest.json`), never PD-018a's test file:

```
INTEGRATION TREE: /Volumes/mac mini m4/swarm-contract/pd-fix/scratchpads/PD-018b/integration
(created with: git worktree add --detach <path> HEAD
               git checkout b78085f9e -- universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json \
                 universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt universal-sops/_content-manifest.json)
```

Because the manifest is absent, this branch run in isolation renders `""` for every phase (empty labels) and `test_all_112_templates_render_with_the_manifest_label` fails there. That is the known ancestor gap, not a code defect.

## Defects A–F

### A. `test_counted_phase_substitutes_real_k_n_name` pinned the old leak — FIXED
Was `'Step 1 of 46 — Deep Research — starting'` (`Phase.name`). Now exact:

```
assert msg  == "Step 1 of 16 — Researching your topic — starting"
assert done == "Step 1 of 16 — Researching your topic — complete"
assert ph.name not in msg and ph.name not in done      # "Deep Research" is internal
```

The number is 16 because defect E changed N to the rendered count; `P-0.5-RESEARCH` is rendered step 1 (`order` −0.5).

### B. `test_name_field_used_not_bare_phase_id` asserted `ph.name in msg` — REWRITTEN
That is the exact internal-name leak this unit removes. It now asserts the plain label and the absence of the internal name:

```
label, client_visible = eng._phase_client_meta(ph)      # P4-RENDER
assert client_visible and label == "Creating your slide images"
assert ph.name and ph.name != ph.id and ph.name != label
msg = eng._render_client_report_msg(ph, "start")
assert label in msg
assert ph.name not in msg                               # "Deterministic Render (build_deck.py — this script)"
assert ph.id not in msg
```

### C. False fixture in `test_the_rendered_step_line_reads_as_a_step` — FIXED
The test built a **no-intake** engine (fail-safe renders `Step 27 of 56`) while pinning `Step 19 of 46`. The fixture now produces the situation the assertion describes — a real deck — and the number is the honest rendered pair from E:

```
eng, manifest = _engine(tmp_path, intake={"deck_type": "webinar", "creation_mode": "from_scratch"})
assert msg == "Step 10 of 16 — Creating your slide images — starting"
```

### D. Unquoted notify path made the transport never start (A4 vacuous) — FIXED
`PRESENTATION_NOTIFY_CMD` is an argument vector (`shlex.split`, `shell=False`). The mandated TMPDIR is `/Volumes/mac mini m4/...`, so an unquoted path splits into three tokens, the transport never starts, and `assert not sent.exists()` passed vacuously. Both harnesses now quote:

```
monkeypatch.setenv("PRESENTATION_NOTIFY_CMD", shlex.quote(str(notify)))
```

and A4 now proves reachability before it can claim silence:

```
eng.report.to_requester("blocked", "transport control")
assert sent.exists() and sent.read_text().strip(), (
    "notify transport never started -- 'received nothing' above was vacuous")
```

**Discrimination proof:** with the quoting reverted inside a scratch copy of the same test, A4 fails exactly at that control line:

```
tests/_probe_broken_transport.py:136: AssertionError
report.undeliverable: blocked message to requester FAILED delivery (outcome=undetermined)
```

So A4 can no longer pass on a dead pipe.

### E. N was 46 client-visible while only 16 messages were sent, leaving k gapped — FIXED (item-4 ruling)
Confirmed on the real manifest, `deck_type=webinar`, `creation_mode=from_scratch`:

```
rendered messages: 16
k values:  [1, 2, 4, 7, 8, 9, 12, 17, 18, 19, 22, 23, 26, 29, 31, 39] of 46
```

New helper `Engine._client_rendered_phases()` = deck-visible ∧ manifest `client_visible: true` ∧ non-empty `client_label`; `_client_phase_index()` now numbers over that list. `_client_visible_phases()` is unchanged (still 46/50/47/56 — the deck filter is a separate concern and its tests still pin those numbers).

Rendered N per deck: webinar/from_scratch **16**, signature/from_scratch **16**, webinar/content_personal **17**, unknown intake **18**.

The test that encoded the false pair is defect C's test (same commit). The consistency test now asserts both numbers explicitly:

```
("webinar", "from_scratch", 46, 16),
("signature_presentation", "from_scratch", 50, 16),
("webinar", "content_personal", 47, 17),
...
assert len(visible) == deck_visible_n
assert len(eng._client_rendered_phases(eng.manifest.phases)) == expected_n
```

`test_hidden_phase_is_silent_whatever_its_step_number` was renamed to `test_hidden_phase_is_silent_and_unnumbered`: a hidden phase now has `k is None` by construction, and the test pins that plus silence (`== ""`) instead of the old `k is not None`.

**Item-4 consequence on the recorded defect pair:** the label-fill property is unchanged; the numbers are now honest.

```
BEFORE (base c40b6744da code + PD-018a manifest):  'Step 19 of 46 —  — starting'
AFTER  (repair + PD-018a manifest):                'Step 10 of 16 — Creating your slide images — starting'
```

### F. Two partial relaxation holes in the fallback tests — FIXED
`startswith("Step ")` + `endswith("— starting")` also accepts `'Step 19 of 46 —  — starting'`, so the old assertions no longer proved a label was filled. Both tests now go through one predicate:

```
def _labelled_step_line(msg, suffix):
    if not (msg.startswith("Step ") and msg.endswith(suffix)):
        return False
    _head, sep, rest = msg.partition(" — ")
    label, sep2, _tail = rest.partition(" — ")
    return bool(sep and sep2 and label.strip())
```

and each test proves the predicate rejects the empty-label form:

```
assert _labelled_step_line(msg, "— starting")
assert not _labelled_step_line("Step 19 of 46 —  — starting", "— starting")
# (the done-side test also rejects "Step 19 of 46 —  — complete")
```

## Commands run, with results

| # | Command | Result |
|---|---|---|
| 1 | `git branch --show-current` / `git rev-parse HEAD` (FL05 worktree) | `pd/fl05-engine-reporting` / `414c715ab0a761911570c6274a1acf477a43b41b` — matched the ledger row; tree clean |
| 2 | `git log --all --oneline --grep=PD-018a` | `b64fb8cd5`, `b78085f9e` present; `git branch -a --contains b78085f9e` → only `pd/fl04-manifest` |
| 3 | `git merge-base --is-ancestor b78085f9e HEAD` / `… origin/main` | `NO` / `NO` — manifest absent from this branch and origin/main (dependency stated above) |
| 4 | `git worktree add --detach …/scratchpads/PD-018b/integration HEAD` + `git checkout b78085f9e -- <3 manifest artifacts>` | integration tree built (path above) |
| 5 | probe: `_client_visible_phases` / `_client_phase_index` / `_render_client_report_msg` on integration tree | deck-visible 46; rendered 16; k gapped `[1,2,4,7,8,9,12,17,18,19,22,23,26,29,31,39]` of 46 (pre-repair) |
| 6 | `python3 -m pytest tests/test_engine_client_report.py tests/test_pd_engine_client_copy.py tests/test_pd_report_sanitize.py -q` (integration tree, `TMPDIR` mandated) | **38 passed** (1.27 s) |
| 7 | same three files on base code `c40b6744da` + PD-018a manifest + the repaired tests (`scratchpads/PD-018b/base`) | **20 failed, 18 passed** — the repaired assertions still discriminate |
| 8 | subset `test_pd010_signature_only_phase_gating.py test_pd_report_throttle.py test_report.py test_client_step_count.py test_presentation_job.py` on integration tree | 13 failed, 82 passed |
| 9 | same subset on pre-repair tree `414c715ab` + PD-018a manifest (`scratchpads/PD-018b/pre`) | 13 failed, 82 passed |
| 10 | `diff` of the two `FAILED` lists | **identical** — no failure attributable to this repair (the 13 are pre-existing: TMPDIR-with-spaces transport tests and manifest-dependent counts) |
| 11 | before/after probe on `P4-RENDER`, webinar/from_scratch | before `'Step 19 of 46 —  — starting'`, after `'Step 10 of 16 — Creating your slide images — starting'` |
| 12 | broken-transport control: scratch copy with `str(notify)` instead of `shlex.quote(...)`, `pytest tests/_probe_broken_transport.py` | `AssertionError` at the control line (136) + `outcome=undetermined` — A4 fails when the pipe is dead |
| 13 | `python3 -m py_compile` on the four changed files | OK |
| 14 | full suite `pytest tests -q` (integration tree) | stopped at 77% after ~12 min on a hanging environment-dependent test; superseded by row 10, which covers the blast radius (`_render_client_report_msg` / `_client_phase_index` / `_client_rendered_phases` are referenced by only three test files, all run green in row 6) |
| 15 | `git commit` (4 files) | `aa506ba7e3748d05ba29f45d7015d3d08eafce41` |
| 16 | `git push origin pd/fl05-engine-reporting` + `git rev-parse HEAD` vs `git ls-remote origin refs/heads/pd/fl05-engine-reporting` | remote sha equals local head (exact line in the build-room return message) |

## Statement

All six defects A–F were fixed inside PD-018b's named file set. None required touching a file outside it. The only standing dependency is PD-018a's unmerged manifest, which is required to render labels at all and is documented above with the integration-tree path used for every behavioural proof.
