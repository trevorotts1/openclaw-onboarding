# `core/lip_sync/narrator_rule/` — Decision 26 + plan 6.6

The canonical narrator lip-sync rule for stage V2-08L. `core/voice_velvet_echo`
mirrors the same eight narrator tokens for its own path; this package is what
the lip-sync stage screens and QC's against.

## The rule (owner Decision 26, 2026-10-07; plan section 6.6)

1. A narrator / off-screen voice may play as **voice-over over any shot**.
2. A lip-synced mouth **only ever moves to that on-screen person's own
   isolated line** — never a narrator's voice, never another character's,
   never a mixed stem (the 2026-10-07 HIDE test lip-synced a CTA stem
   carrying another voice onto a face).
3. A **device speaking with no person on screen** (phone voicemail shot) is a
   legal scene: it passes QC as voice-over and is never dispatched for mouth
   animation.
4. **QC refuses every violation** — a mouth moving to a narrator/foreign
   voice, a face whose voice is not the one playing, a missing, mixed,
   sung, music-bed, foreign or non-isolated stem.

## Interfaces

| Entry | Role |
|---|---|
| `screen_line(record, stems_required=False)` | Screen one scene. `outcome ok` = the shot is legal to show; `lipsync True` = a mouth may move here; `voice_over True` = plays with the mouth shut. |
| `screen_selection(base_selection, scenes)` | **Extend** the base `select_lines` envelope: adds the `narrator_rule` block (`lipsync_line_ids`, `voice_over_line_ids`, `violations`, `per_line`). The base envelope is passed through byte-identical under `base_selection` — the V2-W1-U5 suite's input shape never changes. |
| `lipsync_selection(base_selection, screened)` | Base-shaped `{"selected": [...]}` subset for dispatch. Empty is legal (voice-over-only ad = directive 11.4's default). |
| `check_lipsync_attempt(record, scene, flagged=True)` | Dispatch/QC verdict `PASS`/`FAIL`, fail-closed: stems mandatory here. |
| `refuse_lipsync(qc_result)` | Assembly hook; raises `NarratorRuleBlocked` on anything but PASS. |
| `narrator_qc_rules(base_rules, scenes, flagged_ids)` | Extends the base QC rule map: flagged own lines keep plan 6.3's `mouth_match_required`; flagged narrator/device/no-person lines flip to `voice_over_no_mouth_movement` (source Decision 26); unflagged lines untouched (directive 17.4 keeps ruling). |
| `build_screened_plan(timing, flags, scenes, base=None)` | Real pipeline: base `select_lines` → screen → dispatch subset + QC rules. Missing base stage fails closed with `BASE_LIPSYNC_UNAVAILABLE`. |
| CLI `narrator_rule.py --selection … --scenes …` | Plan only; never dispatches. |

`scenes` maps `line_id -> {"speaker", "onscreen", "stems"?}`.
`qc_voice_match` (D17) owns the pitch bands, `speaker_onscreen_ok` and the
device token set — imported, never re-implemented. The base `lip_sync` stage
supplies `RULE_FLAGGED` / `RULE_UNFLAGGED` when present; the mirrored v1
strings are used only while the base stage is not yet merged, and the base
envelope itself is always passed through untouched.

## Tests

```sh
sh run_all.sh        # 51 checks, mocked: no network, no provider, $0
```

Evidence (lane `V2B-C-R-U2-lane/`):

- `test_narrator_rule.py.log` — 51 passed, 0 failed.
- `base-suite-with-narrator.log` — the V2-W1-U5 suite (198 checks across
  6 files) run **with this package present in the same directory**: still
  `ALL_LIP_SYNC_TESTS_PASS`.
- `integration-real-base.log` — real base `select_lines` → screen → plan,
  narrator attempt refused, device scene passed:
  `REAL_BASE_INTEGRATION_PASS`.
