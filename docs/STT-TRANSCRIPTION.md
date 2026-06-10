# Speech-to-Text (Audio Transcription) — Tiered, Mac-Local

> This repo is the **unified** onboarding package for Mac (Apple Silicon) and VPS. Audio transcription on Mac is configured to run **locally** by default, with a cloud fallback. The VPS platform overlay (`platform/vps/`) uses a different config — see the bottom of this note.

---

## The tier order

| Tier | Where it runs | Engine / model | Cost | Privacy |
|---|---|---|---|---|
| **1 (primary)** | **Local — on the client's Mac** | `faster-whisper` (CTranslate2 engine), model **`medium`** | **Free** | **Private — audio never leaves the box** |
| **2 (final fallback)** | OpenAI cloud | `gpt-4o-mini-transcribe` | Per-call | Audio sent to OpenAI |

`medium` is the **balanced** choice on Apple Silicon: it runs fast on the Neural Engine, is meaningfully more accurate than `base`/`small`, and stays free + private. The cloud entry exists only so transcription never hard-fails if the local model is missing or errors.

---

## What `install.sh` does (Step 8b)

On a fresh Mac install, `install.sh` Step 8b runs automatically:

1. **Installs a local faster-whisper CLI** — `uv tool install whisper-ctranslate2` (the CTranslate2 / faster-whisper engine exposed through a `whisper`-compatible CLI that supports `--model medium`), with `pipx install whisper-ctranslate2` and `pip3 install --user whisper-ctranslate2` as fallbacks. If a faster-whisper CLI is already present, it is left as-is.
2. **Writes a deterministic wrapper** at `~/.openclaw/bin/oc-faster-whisper`. The wrapper forces model `medium`, drives whichever faster-whisper CLI is present, and prints the transcript as **plain text to stdout** — the exact form OpenClaw's CLI transcriber expects. It exits non-zero on failure so OpenClaw advances to the cloud fallback.
3. **Bakes `tools.media.audio` into `~/.openclaw/openclaw.json`** with the local wrapper as the **first** (primary) model entry and OpenAI cloud as the **last** (fallback) entry.

The resulting config (verified against docs.openclaw.ai/gateway/config-tools):

```json
{
  "tools": {
    "media": {
      "audio": {
        "enabled": true,
        "maxBytes": 26214400,
        "models": [
          {
            "type": "cli",
            "command": "/Users/<you>/.openclaw/bin/oc-faster-whisper",
            "args": ["{{MediaPath}}"],
            "timeoutSeconds": 300
          },
          {
            "provider": "openai",
            "model": "gpt-4o-mini-transcribe"
          }
        ]
      }
    }
  }
}
```

- The **first** entry in `models[]` is primary; later entries are fallbacks.
- `{{MediaPath}}` is substituted with the local audio file path at run time.
- `maxBytes` is 25MB (comfortably above OpenClaw's 20MB default).

---

## Changing the model

The wrapper reads `OC_WHISPER_MODEL` (default `medium`). To trade accuracy for speed (or vice-versa), set it in the wrapper's environment or override per call:

```bash
OC_WHISPER_MODEL=small  oc-faster-whisper /path/to/audio.m4a   # faster, lighter
OC_WHISPER_MODEL=large-v3 oc-faster-whisper /path/to/audio.m4a # most accurate, slower
```

`medium` remains the shipped default because it is the best balance on Apple Silicon.

---

## Verify it works

```bash
# 1. The local CLI is installed
command -v whisper-ctranslate2 || command -v faster-whisper

# 2. The wrapper exists and is executable
ls -l ~/.openclaw/bin/oc-faster-whisper

# 3. The config is in place (local primary, openai fallback)
python3 -c "import json,os; a=json.load(open(os.path.expanduser('~/.openclaw/openclaw.json')))['tools']['media']['audio']; print('enabled:', a['enabled']); [print(' -', m.get('command') or m.get('provider'), m.get('model','')) for m in a['models']]"
```

---

## Mac vs VPS (do not co-mingle the configs)

- **Mac (this repo):** LOCAL faster-whisper `medium` primary + OpenAI cloud fallback. Apple Silicon makes the local model fast and free, and keeps audio private on-box.
- **VPS (platform/vps/ in this repo):** cloud transcription only (Groq) — **no local model**. VPS containers do not have a Neural Engine and we do not want to bloat the image with a local Whisper model. Do **not** copy this Mac local-model block into VPS config.

The two platforms have intentionally different transcription tiers, exactly as their LLM and version sequences are kept independent.
