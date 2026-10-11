╔══════════════════════════════════════════════════════════════╗
  MANDATORY TYP CHECK - READ THIS BEFORE ANYTHING ELSE
  DO NOT SKIP. DO NOT PROCEED UNTIL THIS CHECK IS COMPLETE.
╚══════════════════════════════════════════════════════════════╝

STEP 1: CHECK IF YOU HAVE BEEN TAUGHT THE TEACH YOURSELF PROTOCOL (TYP)

Before you read, learn, or execute ANY instruction in this document, you must
verify that you have already been taught the Teach Yourself Protocol (TYP).

HOW TO CHECK:
- Look in your AGENTS.md, TOOLS.md, or MEMORY.md for any mention of:
  "Teach Yourself Protocol" or "TYP"
- Look in your session context for prior TYP training
- Look for a tab called "Teach Yourself Protocol" in this same document

IF YOU HAVE BEEN TAUGHT TYP:
Proceed to the examples below.

IF YOU HAVE NOT BEEN TAUGHT TYP:
STOP IMMEDIATELY. Do not read further. Tell the user you must be taught the
Teach Yourself Protocol first.

DO NOT PROCEED PAST THIS POINT WITHOUT TYP CONFIRMED.

══════════════════════════════════════════════════════════════════
KIE AUDIO - REAL EXAMPLES (TTS + SUNO)
══════════════════════════════════════════════════════════════════

Copy-paste curl commands. Replace YOUR_API_KEY with the KIE_API_KEY value (or
use $KIE_API_KEY after sourcing the environment — see INSTALL.md). All bodies
below come from the first-party KIE docs (references/tts.md + references/music.md)
verified 2026-08-26. Run the validator on every body before dispatching:

  python3 scripts/validate_audio_request.py --domain tts --payload req.json
  python3 scripts/validate_audio_request.py --domain music --payload req.json

ALL of these are ASYNC. A 200 response carries data.taskId (accepted), NOT the
audio. The result arrives via callBackUrl callback (or polling recordInfo).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 1: GEMINI TTS - TWO-SPEAKER DIALOGUE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Model: google/gemini-3-1-flash-tts. Required: input.speakers[] +
input.dialogue_turns[]. speaker_id MUST be "Speaker N" format.

curl https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemini-3-1-flash-tts",
    "callBackUrl": "https://your-handler.example.com/kie-callback",
    "input": {
      "scene": "A quiet newsroom at night",
      "sample_context": "Calm, professional news exchange",
      "temperature": 1,
      "speakers": [
        { "speaker_id": "Speaker 1", "voice_name": "Schedar",
          "accent": "American (Gen)", "style": "Newscaster", "pace": "Natural" },
        { "speaker_id": "Speaker 2", "voice_name": "Gacrux",
          "accent": "British (RP)", "style": "Empathetic", "pace": "The Drift" }
      ],
      "dialogue_turns": [
        { "speaker_id": "Speaker 1", "text": "The vote closed at midnight. What happened next is still unclear." },
        { "speaker_id": "Speaker 2", "text": "Sources inside the hall say the count stalled for six hours." }
      ]
    }
  }'

Response (accepted, NOT complete):

{ "code": 200, "msg": "success", "data": { "taskId": "task_1765185282276" } }

Callback when done: POST to callBackUrl, success code:200 / fail code:501,
data.state "success" / "fail", audio in data.resultJson.resultUrls[0] (data.response.resultUrls is the same list already parsed).

Voice options (30): Achernar, Achird, Algenib, Algieba, Alnilam, Aoede, Autonoe,
Callirrhoe, Charon, Despina, Enceladus, Erinome, Fenrir, Gacrux, Iapetus, Kore,
Laomedeia, Leda, Orus, Puck, Pulcherrima, Rasalgethi, Sadachbia, Sadaltager,
Schedar, Sulafat, Umbriel, Vindemiatrix, Zephyr, Zubenelgenubi.

Accents (8): Neutral, American (Gen), American (Valley), American (South),
British (RP), British (Brixton), Transatlantic, Australian.
Styles (6): Vocal Smile, Newscaster, Whisper, Empathetic, Promo/Hype, Deadpan.
Paces (4): Natural, Rapid Fire, The Drift, Staccato.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 2: ELEVENLABS DIALOGUE-V3 (MULTI-TURN)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Same createTask route; model enum picks the engine. Combined text of ALL
dialogue fields must not exceed 5,000 characters (verbatim) — safe ceiling 4,900.

curl https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "elevenlabs/text-to-dialogue-v3",
    "callBackUrl": "https://your-handler.example.com/kie-callback",
    "input": {
      "stability": 0.5,
      "language_code": "en",
      "dialogue": [
        { "text": "You kept the ticket?", "voice": "EkK5I93UQWFDigLMpZcX" },
        { "text": "I kept the ticket.", "voice": "EkK5I93UQWFDigLMpZcX" }
      ]
    }
  }'

Response: { "code": 200, "data": { "taskId": "task_elevenlabs_1765185448724",
"recordId": "elevenlabs_1765185448724" } }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 3: ELEVENLABS TURBO V2.5 (SINGLE TEXT; LANGUAGE ENFORCEMENT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "elevenlabs/text-to-speech-turbo-2-5",
    "callBackUrl": "https://your-handler.example.com/kie-callback",
    "input": {
      "text": "Security is a process, not a product.",
      "voice": "EkK5I93UQWFDigLMpZcX",
      "stability": 0.5,
      "similarity_boost": 0.75,
      "style": 0,
      "speed": 1,
      "language_code": "en"
    }
  }'

Turbo v2.5 / Flash v2.5 ("only Turbo v2.5 and Flash v2.5 support language
enforcement") — enforce language_code on those two models. Callback failure
carries failCode "GENERATION_FAILED".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 4: SUNO GENERATE - CUSTOM SONG (V6)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CURRENT (and ONLY) route: POST /api/v1/jobs/createTask with top-level
"model": "ai-music-api/generate" and every direction nested under input
(snake_case). Version at input.model (default V6). Required input: custom_mode,
instrumental, model. Custom caps: lyrics/prompt 5,000, style 1,000, title 80.
input.style is a rule-12 DESCRIPTIVE field (validator target 95-100% of the
1,000 cap, hard floor 80%) -- the value below is sized to the band (917 chars). duration applies when custom_mode true and input.model
is V5_5 or the V6 family (V6/V6_MINI/V6_WILD): 10-360, default 20. The legacy
POST /api/v1/generate music-generation route is RETIRED (WW-30): refused, no
fallback, no silent switch-back. The other /api/v1/generate/<op> routes
(extend, sounds, cover, ...) are different routes and untouched.

curl https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai-music-api/generate",
    "callBackUrl": "https://your-handler.example.com/kie-callback",
    "input": {
      "custom_mode": true,
      "instrumental": false,
      "model": "V6",
      "title": "The Last Light",
      "style": "Slow-burning synthwave ballad, 88 BPM, minor key: warm analog pad swells, a pulsing Juno bass, glassy electric piano and a dry gated snare, with tape saturation and gentle wow-and-flutter hiss for a worn cassette feel. The verse stays sparse and intimate - soft rimshot, one arpeggio, a close-mic breathy female lead; the pre-chorus lifts a rising filter sweep and stacked oohs; the chorus opens wide with a soaring lead, doubled harmonies a third above, a sawtooth hook line and a four-on-the-floor kick. A short instrumental bridge trades the voice for a nostalgic chorus-soaked guitar solo and a plate reverb tail, then a stripped final chorus ends on a lone sustained pad and a tape-stop. Mood: wistful, cinematic, nocturnal, hopeful, lonely - a lighthouse keeper watching the last light over a black sea. Avoid edm drops, autotune and choir stacks; keep the low end round and the top end soft, 88 BPM throughout.",
      "lyrics": "<the verbatim lyrics sheet; sections in [brackets]>",
      "negative_tags": "choir, reverb, echo",
      "duration": 120
    }
  }'

Response: { "data": { "taskId": "..." } }. Callback stages: text → first →
complete; ONLY complete is finished output. items carry audio_url,
stream_audio_url, image_url, prompt, model_name, title, tags, duration.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 5: SUNO NON-CUSTOM MODE (PROMPT-ONLY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://api.kie.ai/api/v1/jobs/createTask \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ai-music-api/generate",
    "callBackUrl": "https://your-handler.example.com/kie-callback",
    "input": {
      "custom_mode": false,
      "instrumental": true,
      "model": "V6",
      "prompt": "Lo-fi hip hop, rain on a window, vinyl crackle, mellow Rhodes",
      "title": "Rainy Window",
      "style": "lo-fi hip hop, mellow, instrumental",
      "negative_tags": "choir, reverb, echo",
      "duration": 60
    }
  }'

Non-custom prompt limit: the generate-music page says 3,000 characters, the
mashup page says 500 (the two pages disagree; UNDETERMINED, the validator enforces
the smallest documented ceiling of 500 with no floor and treats the conflict as
advisory). With custom_mode false the prompt is the ONE lyrics source -- never send
input.lyrics beside it. duration is advisory here; it takes effect only for custom
V5_5/V6-family. Skill 75's drama-song build emits only the CUSTOM form (input.lyrics
present, input.prompt refused); this non-custom form is the general KIE envelope
documented in references/music.md -- same createTask route, same field names.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 6: SUNO EXTEND
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://api.kie.ai/api/v1/generate/extend \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "defaultParamFlag": true,
    "audioId": "<audioId from a completed generate task>",
    "model": "V5",
    "continueAt": 32,
    "prompt": "Continue the bridge into a quiet outro, same instruments",
    "style": "synthwave, dreamy",
    "title": "The Last Light (Part 2)",
    "instrumental": false,
    "callBackUrl": "https://your-handler.example.com/kie-callback"
  }'

instrumental=true PROHIBITS prompt + vocalGender. continueAt = seconds to start
extending from. Per-model title: V4/V4_5ALL 80, V4_5/V4_5PLUS/V5/V5_5 100.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 7: SUNO SOUNDS (SOUND EFFECT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://api.kie.ai/api/v1/generate/sounds \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "sint",
    "model": "V5",
    "soundLoop": true,
    "soundTempo": 166,
    "soundKey": "D#m",
    "grabLyrics": true,
    "callBackUrl": "https://your-handler.example.com/kie-callback"
  }'

That example body is the docs' own example. Prompt limit: 500 characters.
soundTempo 1-300 BPM. soundKey default "Any". Poll via get music details every
30 seconds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 8: SUNO MASHUP (EXACTLY 2 URLS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

curl https://api.kie.ai/api/v1/generate/mashup \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "uploadUrlList": [
      "https://res.example.com/track-a.mp3",
      "https://res.example.com/track-b.mp3"
    ],
    "model": "V5",
    "customMode": false,
    "callBackUrl": "https://your-handler.example.com/kie-callback"
  }'

uploadUrlList must contain EXACTLY 2 audio file URLs (min 2, max 2 — verbatim
"must contain exactly 2 audio file URLs"). The validator rejects 1 or 3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXAMPLE 9: TTS POLLING FALLBACK (RECORD INFO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Prefer callBackUrl. If no handler is available, poll the unified Market query
endpoint. Initial delay 2-3s, stepped backoff, respect 429:

  curl "https://api.kie.ai/api/v1/jobs/recordInfo?taskId=task_1765185282276" \
    -H "Authorization: Bearer YOUR_API_KEY"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STT: NO EXAMPLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

There is deliberately NO speech-to-text example in this skill. KIE advertises
ElevenLabs STT on its market overview, but no first-party callable endpoint was
located on 2026-08-26 (sitemap ~460 URLs zero hits; elevenlabs docs dir = 4
models, all TTS/isolation). The registry entry is dispatch_enabled: false and
validate_audio_request.py --domain stt exits 2 on ANY dispatch attempt. If you
are asked for transcription, report the status and re-proof path from
references/stt.md — do NOT invent a /transcribe route.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON MISTAKES TO AVOID
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MISTAKE 1: Routing the wrong Suno model through createTask.
  WRONG:  POST /api/v1/jobs/createTask with model "V5" or "suno/...".
  RIGHT:  createTask carries ONLY ai-music-api/* (e.g. "ai-music-api/generate"
          with input.model V6). The legacy POST /api/v1/generate
          music-generation route is RETIRED (refused, exit 2); the other
          /api/v1/generate/<op> routes (extend, sounds, cover, ...) are
          different routes and untouched. The validator rejects the wrong
          family (exit 2).

MISTAKE 2: Treating the 200 as the finished audio.
  WRONG:  Listening for audio in the createTask response.
  RIGHT:  The 200 carries data.taskId. Audio comes via callback (or polling).

MISTAKE 3: Exceeding combined-text caps.
  dialogue-v3 combined > 5,000 (reject); Gemini per-turn text > 10,000 (reject).

MISTAKE 4: Using a parameter where it does not apply.
  duration on non-V5_5/V6-family or non-custom — provider IGNORES it (advisory
  warning in validator, not a reject); instrumental=true with prompt/vocalGender
  on extend (hard reject).

MISTAKE 5: Dispatching an STT request anywhere.
  Exit 2 from the validator. No endpoint exists. Report status, never fabricate.

MISTAKE 6: Skipping audio QC.
  API success is not QC. Run references/qc.md after completion (playable file,
  language, voice identity, pronunciation, pace, style, no clipping, speaker
  ordering; music: duration, genre/style, vocals intent, lyrics fidelity,
  callback complete stage).
