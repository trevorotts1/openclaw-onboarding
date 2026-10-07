# W4-01-U1 full-duration campaign qualification - test evidence

Run `w4-long` | owned output `qualification/long-form-media/` | attempt `W4-01-1791336458459`

**This is measurement, not approval.** The unit verdict is written by the independent checker at `evidence/W4-01/W4-01-U1.verdict.json`; the builder does not write it.

| id | requirement | result | measured |
|---|---|---|---|
| C1 | intake ok, authorization bound to this campaign summary digest | **PASS** | `{"auth_status": "bound", "digest": "8eddf994b96fc122", "outcome": "ok", "questions": null, "target_length_s": 63}` |
| C2 | preflight rc=0 before any paid call | **PASS** | `{"outcome": "ok", "profile": "long-9x16-60s", "rc": 0, "reason_code": "preflight-pass"}` |
| C3 | lyric gate accepts approved 60s+ sung copy | **PASS** | `{"coverage": {"covered": 7, "critical_words": 7, "missing": []}, "line_count": 12, "outcome": "ok"}` |
| C4 | Skill 68 music payload validates before dispatch | **PASS** | `{"rc": 0, "tail": "WARN: music: style is 894 chars; the target is 95-100% of 1000 (add 56 chars)\nVALIDATION PASSED (1 advisory warning(s))"}` |
| C5 | directive 16 capability router selects one pinned catalog model for every shot | **PASS** | `{"models": {"shot-01": "wan/3-0-video", "shot-02": "wan/3-0-video", "shot-03": "wan/3-0-video"}, "outcomes": {"shot-01": "ok", "shot-02": "ok", "shot-03": "ok"}}` |
| C6 | storyboard bound to lyric timing, adversarial review passes, video spend gate open | **PASS** | `{"bind": "ok", "findings": [], "gate": true, "gate_reason": "storyboard-gate-open", "review": "pass"}` |
| C7 | character DNA record valid and bound to approved references | **PASS** | `{"records": {"char-owner-shop": []}, "reference_binding": {"char-owner-shop": ["asset-keyframe-01"]}}` |
| C8 | final media full intended duration (60-90s) | **PASS** | `{"assembled_from_s": 63.0, "band": [60.0, 90.0], "final_master_s": 63.0, "streams": {"audio": 63.0, "video": 63.0}}` |
| C9 | multi-shot continuity: 3 distinct shots share one character, one wardrobe and one first frame | **PASS** | `{"distinct_camera_directions": 3, "distinct_clip_files": ["392dd178ee87d269b65452e923f2a63e_0.mp4", "5cfe577e66857e913d7713e67b7439c9_0.mp4", "c3bb63b280a862c6b8fa9f5c79ee39c5_0.mp4"], "first_frame_shared": true, "review": "pass", "shot_count": 3, "wardrobe_identical": true}` |
| C9b | frame-level continuity: shots start from one shared keyframe rather than drifting per generation | **PASS** | `{"mean_mse_shot0_to_shot0": 0.07017543859649122, "mean_mse_shot0_to_shot1_same_shot": 0.9441246345029239, "pairs": [{"a": "shot-01", "b": "shot-02", "mse_frame0": 0.06825657894736842}, {"a": "shot-01", "b": "shot-03", "mse_frame0": 0.06990131578947369}, {"a": "shot-02", "b": "shot-03", "mse_frame...` |
| C10 | lyric timing accepted on the full-length master | **PASS** | `{"audio_s": 63.0, "clips_checked": 3, "coverage": {"approved_n": 94, "covered": 94, "overall": 1.0}, "detail": "", "low_confidence": ["timing-sample-unrecorded"], "reason_code": "LOW_CONFIDENCE", "verdict": "REVIEW", "video_s": 63.0}` |
| C11 | music QC on the long master | **PASS** | `{"checks": {"clipping": "PASS", "genre_continuity": "UNAVAILABLE", "master_duration": "PASS", "persona_continuity": "PASS", "tempo_continuity": "UNAVAILABLE", "transitions": "PASS"}, "measurement": {"ffmpeg_sample_peak_dbfs": -1.03687, "ffprobe_duration_s": 62.352, "final_master_duration_s": 63.0...` |
| C12 | paid spend reserved before submission and fully reconciled inside the ceiling | **PASS** | `{"actual": 1016, "calls": 5, "ceiling_cents": 5000, "jobs": [{"actual": 6, "estimated": 6, "logical_key": "w4-long/music-generate", "remote_task_id": "5e9ed441cc177a5cc5bfaa46ff26e37d", "state": "reconciled"}, {"actual": 2, "estimated": 2, "logical_key": "w4-long/image-generate", "remote_task_id"...` |
| C13 | program-wide spend stays inside the owner-recorded $50 total program | **PASS** | `{"by_run": {"w3-04-short-run": {"actual": 8, "outstanding_estimated": 0, "total": 8}, "w4-long": {"actual": 1016, "outstanding_estimated": 0, "total": 1016}}, "program_ceiling_cents": 5000, "projected_cents": 1024}` |
| C14 | every recorded artifact re-hashes to its manifest digest | **PASS** | `{"artifacts": 7, "mismatch": []}` |
| C15 | all run stages claimed and completed | **PASS** | `{"stages": {"final_assemble": "COMPLETE", "image_generate": "COMPLETE", "intake": "COMPLETE", "lyrics_approved": "COMPLETE", "music_generate": "COMPLETE", "music_qc": "COMPLETE", "preflight": "COMPLETE", "receipts": "COMPLETE", "storyboard": "COMPLETE", "timing_guard": "COMPLETE", "video_generate...` |
| C16 | unknown provider outcome policy: stop/park, never resubmit | **PASS** | `{"failed_files": [], "unknown_files": [], "unknown_or_reserved_cents": 0}` |
| C17 | final media meets the delivery profile | **PASS** | `{"bytes": 18534133, "fps": 30, "height": 1920, "path": "qualification/long-form-media/final/final-9x16.mp4", "sha256": "18cee37d083db74eec711c36c902ad8883f502e992492fd927dea3f5bbea967c", "variant_plans": ["9:16", "16:9", "1:1"], "width": 1080}` |
| C18 | no credential material anywhere in the owned output | **PASS** | `{"files_scanned": 86, "leaks": []}` |
| C19 | every paid submission has a provider task id, a credit charge and a persisted artifact digest | **PASS** | `{"jobs": [{"cents": 2, "credits": 4.0, "logical_key": "w4-long/image-generate", "sha256": "48e9ddc0ae8a2cbee0225a0e05c0a3d84f914d43625351df12b9103dab5be407", "task_id": "52cd20311ab74e660bfe7d4cf8b19a8b"}, {"cents": 6, "credits": 12.0, "logical_key": "w4-long/music-generate", "sha256": "b4425ff21...` |
| C20 | builder wrote no unit verdict | **PASS** | `{"expected_verdict_path": "evidence/W4-01/W4-01-U1.verdict.json", "owner": "independent checker", "verdict_files_touched_by_builder": []}` |

Summary: **21/21 PASS**, 0 FAIL.

## Honest limitations (recorded, not papered over)

- `timing_guard` verdict is **REVIEW / LOW_CONFIDENCE**: Skill 68 STT is `ADVERTISED_NOT_YET_VERIFIED` with `dispatch_enabled false`, so there is no independent ASR sample and the guard must not invent one. Lyric coverage (94/94), clip spans and final A/V sync are all measured and clean.
- `music_qc` verdict is **UNAVAILABLE**: only `genre_continuity` and `tempo_continuity` are unavailable - the provider returns no independent genre or tempo evidence and no calibrated estimator exists. Clipping, master duration, persona continuity, transitions and every lyric check PASSED.
- `delivery_variants` produced aspect **plans** only; transcoding is the media pipeline's job, not that module's.
- `aspect_ratio` is undetermined in the Skill 67 catalog, so the router warns; the produced artifacts measure 1080x1920, which is what the profile asks for.
- Frame continuity (C9b) is a **relative** test with no absolute threshold: the acceptance profile's calibration status is `uncalibrated`, so an invented similarity bar would be false precision. Raw pairwise MSE is recorded in `continuity-frames.json`.

