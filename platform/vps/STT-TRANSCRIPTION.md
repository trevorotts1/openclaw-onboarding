# Speech-to-Text (STT) / Voice-Note Transcription — VPS

How OpenClaw transcribes inbound voice messages on **Hostinger Docker VPS** clients.

> Mirror doc for the Mac fleet lives in the Mac onboarding repo. The two fleets use the
> SAME default (local faster-whisper `medium`) so the experience is uniform — only the
> install mechanics differ (Mac: `uv tool install faster-whisper` / pip; VPS: the
> container-correct install below).

---

## Default: LOCAL faster-whisper, model `medium`

VPS clients transcribe inbound voice messages **locally** with **faster-whisper** on the
**`medium`** model. This is:

- **Free** — no API key, no per-minute cost.
- **Private** — audio never leaves the client's box.
- **Uniform** — same default as the Mac clients.

### Why this is fine on a VPS

VPS boxes are capable enough for this. Verified profile: **2–4 cores / 8–15 GB RAM, mostly
idle.** CPU transcription of a single voice note on `medium` is **~10–40s**, which is fine for
**async voice messages** (the owner sends a voice note; a short transcription delay is
acceptable — this is not a real-time streaming use case).

### Why NOT `large-v3` locally

`large-v3` is too heavy for CPU on these boxes. We deliberately keep the LOCAL model at
`medium`. `large-v3` only appears in the **Groq cloud** tier (below), where it runs on Groq's
hardware, not the client's CPU.

---

## The tiered fallback chain

`install.sh` writes this to the client's `openclaw.json` under `tools.media.audio.transcription`:

| Order | Provider | Model | Key | Role |
|---|---|---|---|---|
| 1 | **local-faster-whisper** | `medium` | none | **DEFAULT** — free + private |
| 2 | groq | `whisper-large-v3` | `GROQ_API_KEY` | OPTIONAL fallback (~$0.111/hr) — used only if local fails AND a key is present |
| 3 | openai | `whisper-1` | `OPENAI_API_KEY` | FINAL cloud fallback |

Providers are tried in array order; the first that succeeds wins. **No Groq key is required
for the default path** — the Groq and OpenAI tiers are referenced by env-var NAME only and
are optional. If neither cloud key is set, the client still transcribes locally for free.

The written block (shape):

```json
{
  "tools": {
    "media": {
      "audio": {
        "transcription": {
          "default": "local-faster-whisper",
          "order": ["local-faster-whisper", "groq", "openai"],
          "providers": {
            "local-faster-whisper": {
              "type": "local",
              "command": "faster-whisper",
              "model": "medium",
              "fallbackCommand": "python3 -m faster_whisper",
              "language": "auto",
              "private": true,
              "cost": "free"
            },
            "groq":   { "type": "cloud", "provider": "groq",   "model": "whisper-large-v3", "apiKeyEnv": "GROQ_API_KEY",   "optional": true },
            "openai": { "type": "cloud", "provider": "openai", "model": "whisper-1",        "apiKeyEnv": "OPENAI_API_KEY", "optional": true }
          }
        }
      }
    }
  }
}
```

---

## Install (runs INSIDE the Docker container)

`install.sh` (Step 6.6) installs `faster-whisper` with a container-correct order. **`apt` /
`apt-get` is a brew shim on Hostinger and brew is OFF PATH — it is NOT used here.**

1. `uv tool install faster-whisper` — preferred (clean, isolated).
2. `pip3 install --user faster-whisper --break-system-packages` — fallback.
3. `/data/linuxbrew/.linuxbrew/bin/python3 -m pip install faster-whisper` — last resort (explicit path).

If all three fail, transcription falls back to Groq/OpenAI (cloud) if those keys are present,
and the installer warns with the manual install command.

---

## Verifying

```bash
# Is faster-whisper importable inside the container?
python3 -c "import faster_whisper; print('faster-whisper OK')"

# Is the config block present?
python3 - <<'PY'
import json
cfg = json.load(open('/data/.openclaw/openclaw.json'))
print(json.dumps(cfg['tools']['media']['audio']['transcription'], indent=2))
PY
```

---

## Relationship to Skill 22 (YouTube/video → persona)

Skill 22's long-form transcription pipeline (`yt-dlp` + `whisper-cpp`/`openai-whisper`, Step
6.5) is a **separate** path for batch video transcription. The `tools.media.audio` STT tier
documented here is for **conversational voice notes** sent to the agent. Both coexist.
