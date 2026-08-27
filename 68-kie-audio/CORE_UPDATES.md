# KIE Audio (68) - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

**These updates are PERFORMED by `wire.sh`, not pasted.** `wire.sh` writes each block
behind its `<!-- BEGIN/END skill:68-kie-audio:<target> -->` marker REPLACE-IN-PLACE,
with `[MASTER_FILES_FOLDER]` resolved to this box's absolute master-files path, and
stamps `<!-- skill:68-kie-audio:core-update-applied -->`. Earlier versions had no
installer, so the generic merger copied this section VERBATIM and every box ended up
with the literal word `Add:`, a markdown code fence, and an unresolved relative
pointer in its AGENTS.md. Never paste the instruction — run `bash wire.sh`.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Media Generation Routing
- generic image -> provider router -> Agnes Image (63) or KIE Image (66)
- generic video -> provider router -> Agnes Video (64) or KIE Video (67)
- KIE audio/music/TTS -> KIE Audio (68)
- explicit model/provider wins; department manifest wins; chosen provider remembered for the task
- validators run before API dispatch
- detailed model tables live in skill references/, not here

## KIE Audio (68)
- TTS via generic Market createTask (POST /api/v1/jobs/createTask): google/gemini-3-1-flash-tts, google/gemini-2-5-pro-tts, elevenlabs/text-to-dialogue-v3, elevenlabs/text-to-speech-multilingual-v2, elevenlabs/text-to-speech-turbo-2-5. Key: KIE_API_KEY (referenced, never printed).
- Suno music is DEDICATED (/api/v1/generate + /extend + /sounds + 14 operations) — NEVER through createTask. Models: V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5.
- STT is NOT dispatchable: ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false — never route transcription here.
- Validator: python3 scripts/validate_audio_request.py --domain tts|music|stt --payload <file.json> (exit 2 = do not dispatch).
- Full reference: [MASTER_FILES_FOLDER]/68-kie-audio/references/tts.md (+ music.md, stt.md, qc.md)
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## KIE Audio API (TTS + Suno)
- Auth: Bearer <KIE_API_KEY> (referenced, never printed)
- TTS: POST https://api.kie.ai/api/v1/jobs/createTask; query GET /api/v1/jobs/recordInfo?taskId=<id>
  - google/gemini-3-1-flash-tts, google/gemini-2-5-pro-tts (input.speakers[] + input.dialogue_turns[]; per-turn text max 10000)
  - elevenlabs/text-to-dialogue-v3 (dialogue[] combined max 5000), /text-to-speech-multilingual-v2, /text-to-speech-turbo-2-5 (text max 5000)
- Music (Suno DEDICATED — never createTask): POST /api/v1/generate, /generate/extend, /generate/sounds, plus 14 operations (mashup = exactly 2 URLs; persona vocal window 10-30s; replace-section min 10s max 50%)
- All audio tasks ASYNC: 200 = taskId only; result via callBackUrl callback (or polling); Suno stages text -> first -> complete
- STT: no endpoint — ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false
- Validator: python3 scripts/validate_audio_request.py --domain tts|music|stt --payload <file.json>
- Full reference: [MASTER_FILES_FOLDER]/68-kie-audio/references/tts.md (+ music.md, stt.md, qc.md)
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## KIE Audio (68) - installed
- KIE_API_KEY (same as Skill 07; referenced, never printed)
- TTS via generic createTask (Gemini speakers/dialogue_turns; ElevenLabs dialogue-v3/multilingual-v2/turbo-2-5); query recordInfo
- Suno is DEDICATED /api/v1/generate family — never createTask
- STT is ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false — never route transcription here
- Full reference: [MASTER_FILES_FOLDER]/68-kie-audio/references/tts.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
