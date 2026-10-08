# Stage runbook

Source: manual 02 B1 step 4; stage ids are `batch_mode/batch.py:112-125` STAGES. One
row per stage: the exact command to run for that stage and what it produces. The
`factory.py next` subcommand returns these rows; the agent loops next -> run -> register -> next.

Run each command from this skill's root (`75-drama-song-ad-factory/`). Substitute
`$RUN` (the run dir), `$RUN_ID` and the `<...>` placeholders before running.

| stage id | command | produces |
|---|---|---|
| research | `python3 scripts/core/research_engine/research.py --brief "$RUN/brief.json" --outdir "$RUN"` | `research/{market,audience,competitors}.md` + `evidence.json` with every claim source-cited. |
| creative-strategy | `python3 scripts/core/story_arc/story_arc.py --story "$RUN/creative/story.json"` | Validated twelve-beat story arc (agent authors `creative/story.json`; missing beats fail). |
| script-lyrics | `python3 scripts/core/lyric_writer/lyric_writer.py --lyrics "$RUN/creative/lyrics.json" --brief "$RUN/brief.json"` | Sung lyric script passing sung-copy rules (first-person, pronunciation, CTA). |
| music | `python3 scripts/core/kie_dispatch/kie_dispatch.py dispatch --model <suno-model-id> --request "$RUN/music/req.json" --save-dir "$RUN/music" --ledger "$RUN/spend.sqlite3" --run-id "$RUN_ID" --logical-key suno --attempt-id a1 --cost 0` | Suno song master and timing map for the approved lyrics, on a reserved ledger attempt. |
| continuity-bible | `python3 scripts/core/qc_gate.py evaluate --run "$RUN_ID" --stage continuity-bible --records "$RUN/continuity/qc-records.json" --makers "$RUN/continuity/makers.json" --required <required-checks>` | Stage gate over the agent-authored Character DNA + product DNA + style bible records (`character_continuity/`, `product_style_bible/` are import-only libraries). |
| storyboard | `python3 scripts/core/shot_planner/speaker_check/speaker_check.py check --env "$RUN/storyboard/shot-list.json"` | Speaker-visible shot list bound to lyric timing; fail-closed before storyboard approval (planner binding via `shot_planner.shot_planner.bind_plan`, import-only). |
| image-keyframes | `python3 scripts/core/kie_dispatch/kie_dispatch.py dispatch --model <image-model-id> --request "$RUN/generation/req.json" --save-dir "$RUN/generation" --ledger "$RUN/spend.sqlite3" --run-id "$RUN_ID" --logical-key keyframes --attempt-id a1 --cost 0` | Keyframe images for every planned shot, delivered only after `final_assembler`-independent QC records exist. |
| video-generation | `python3 scripts/core/kie_dispatch/kie_dispatch.py dispatch --model <video-model-id> --request "$RUN/generation/req.json" --save-dir "$RUN/generation" --ledger "$RUN/spend.sqlite3" --run-id "$RUN_ID" --logical-key video --attempt-id a1 --cost 0` | Per-shot video clips on reserved KIE attempts (model id from `video_router`). |
| qc-retakes | `python3 scripts/core/retake_manager/retake_manager.py --request "$RUN/qc/retake-request.json"` | Targeted retake plan naming only failed units, capped at 2 attempts per unit. |
| assembly | `python3 scripts/core/final_assembler/assembler.py "$RUN/edit/timeline.json" "$RUN/edit/ad.mp4"` | Frame-exact ffmpeg master render of `blackceo.timeline/v1`. |
| final-qc | `python3 scripts/core/qc_gate.py evaluate --run "$RUN_ID" --stage final-qc --records "$RUN/qc/records.json" --makers "$RUN/qc/makers.json" --required <required-checks>` | Approved final-QC verdict records on the rendered master (independent reviewer, UNAVAILABLE never passes). |
| delivery | `python3 scripts/core/qc_gate.py evaluate --run "$RUN_ID" --stage delivery --records "$RUN/qc/records.json" --makers "$RUN/qc/makers.json" --required <required-checks>` | Delivery gate record over the final package (master + `delivery_variants` plan + receipts); board event follows via `cc_sync` (import-only). |

Note: `music`, `image-keyframes` and `video-generation` share one command shape (the
Skill 74 `kie_dispatch` route); only the model id, request file and logical key differ.
Video model ids come from `python3 scripts/core/video_router/video_router.py --request <request.json>`.