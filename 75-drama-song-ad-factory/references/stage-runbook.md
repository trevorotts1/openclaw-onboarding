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

Story arc rule (FU-U13): every ad's story runs struggle -> what changed -> the
product is why -> get the product. The product is named and connected inside
the lyrics AND on screen (cover, title, link), never only on an end card. The
script-lyrics stage plans the spoken-word parts and the struggle motion shots
from the source material; the plan carries `product_connection` (seconds and
percent of runtime). The aim is 10-15% of runtime connecting story to product
-- a TARGET, not a hard cap: the planner computes it, the final-qc delivery
checklist measures it (row `PRODUCT_CONNECTION` in `delivery_checklist`), and
outside the band is a FLAG with the measured seconds and percent, never a
blocker by itself. The choice card shows the planned seconds and percent.

Song files (H14): before the delivery gate, build the audio-only deliverables with `delivery_variants.build_song_files(mix, $DELIVERY, <ad name>, instrumental)` then `write_song_docs($DELIVERY, rows)` (MP3 320 kbps + WAV named after the ad, plus the instrumental pair if one exists; both listed in `delivery-receipt.json` and `README.md`). Gate it with a `song_files` QC record (`python3 scripts/core/delivery_variants/song_files.py check $DELIVERY <ad name>`, exit 5 = a song file is missing); include `song_files` in the delivery `--required` list.

Parallel minute-lanes (W-G-008): a song under 120 s runs the table above unchanged (one lane). At 120 s and up, `scripts/core/lane_planner.py` cuts the shot list into N = ceil(L / 60) lanes of about 60 s, every cut on a shot boundary (`plan_lanes(shots, song_length_s)`); shared steps (song + song checker, plan/shot list, character, close-up picture gate) run once before the split, the per-lane stages above (`image-keyframes`, `video-generation`, lip-sync) then run in every lane at the same time, and the fan-in (one edit, one independent checker, one repair) runs once after. ONE `SharedGovernor` paces all lanes: at most 20 new generation requests per 10 s in total, per-lane share floor(18 / N), 429s resubmitted through `load_governor.kie_request`; heavy ffmpeg stays at most 2 at once across all lanes (`heavy_slot`). `classify_tag(db, run_id, tag)` polls a ledger-known tag and reuses a finished file, so a re-run never pays twice; all lanes plan against the ONE run's ledger.
Song mp3 part of the deliverable (FU-U14): every delivered ad folder must ALSO hold the final song named `<Author> - <Title> - Song.mp3` (320 kbps, the exact song used, full length; plus the wav when one exists) beside the captioned and clean-master mp4s. Gate it before delivery: `python3 -c "from delivery_checklist import delivery_checklist as dc; print(dc.check_song_mp3('<AD_DIR>', '<AD_AUDIO>', '<Title>', '<Author>'))"` — rows `SONG_MP3_FILE` / `SONG_MP3_DURATION` / `SONG_MP3_CORRELATION`, fail closed (missing file, duration off by more than 0.1 s, or correlation under 0.95 is a FAIL). When a book/batch campaign finishes, build one zip per client: `python3 scripts/core/batch_zip/batch_zip.py <manifest.json>` (`build_batch_zip(client, ads, out_path)`) — one folder per author with the three files per ad plus a README listing every file, duration, resolution and banner link.

Note: `music`, `image-keyframes` and `video-generation` share one command shape (the
Skill 74 `kie_dispatch` route); only the model id, request file and logical key differ.
Video model ids come from `python3 scripts/core/video_router/video_router.py --request <request.json>`.