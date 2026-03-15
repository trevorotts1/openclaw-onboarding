# Fish Audio API Reference

> Complete developer reference for the Fish Audio text-to-speech API. Last updated: March 14, 2026

---

## Table of Contents

1. [Authentication](#authentication)
2. [Base URL](#base-url)
3. [Text-to-Speech (TTS)](#text-to-speech-tts)
4. [Models](#models)
5. [Emotions & Paralanguage](#emotions--paralanguage)
6. [Fine-Grained Control](#fine-grained-control)
7. [WebSocket Streaming](#websocket-streaming)
8. [Speech-to-Text (ASR)](#speech-to-text-asr)
9. [Voice Cloning (Create Model)](#voice-cloning-create-model)
10. [Pricing & Rate Limits](#pricing--rate-limits)
11. [Error Codes](#error-codes)
12. [SDKs](#sdks)

---

## Authentication

Fish Audio uses **Bearer token authentication**. Pass your API key in the `Authorization` header.

### Get Your API Key

1. Go to [fish.audio/app/api-keys](https://fish.audio/app/api-keys)
2. Create a new API key
3. Copy and store it securely

### Header Format

```
Authorization: Bearer YOUR_API_KEY
```

### curl Example

```bash
curl -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/msgpack" \
  -H "model: s2-pro" \
  --data-binary @request.msgpack
```

### Environment Variable (Recommended)

```bash
export FISH_API_KEY="your_api_key_here"
```

---

## Base URL

```
https://api.fish.audio
```

---

## Text-to-Speech (TTS)

### Endpoint

```
POST /v1/tts
```

### Content Types Accepted

- `application/json` - For requests without reference audio
- `application/msgpack` - Required for inline reference audio (zero-shot cloning)

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer YOUR_API_KEY` |
| `Content-Type` | Yes | `application/json` or `application/msgpack` |
| `model` | Yes | `s1` or `s2-pro` (recommended: `s2-pro`) |

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | string | Yes | - | Text to convert to speech |
| `reference_id` | string | No | `null` | Voice model ID from Fish Audio library or your custom models |
| `references` | array | No | `null` | Inline reference audio for zero-shot cloning (requires MessagePack). Array of `{audio: binary, text: string}` |
| `temperature` | number | No | `0.7` | Controls expressiveness. Range: 0-1. Higher = more varied |
| `top_p` | number | No | `0.7` | Controls diversity via nucleus sampling. Range: 0-1 |
| `format` | string | No | `"mp3"` | Output format: `mp3`, `wav`, `pcm`, `opus` |
| `sample_rate` | integer | No | `null` | Sample rate in Hz. Uses format default if null (44.1kHz for most, 48kHz for opus) |
| `mp3_bitrate` | integer | No | `128` | MP3 bitrate: `64`, `128`, or `192` kbps |
| `opus_bitrate` | integer | No | `-1000` | Opus bitrate: `-1000` (auto), `24`, `32`, `48`, `64` kbps |
| `chunk_length` | integer | No | `300` | Characters per chunk. Range: 100-300 |
| `min_chunk_length` | integer | No | `50` | Minimum characters before splitting. Range: 0-100 |
| `normalize` | boolean | No | `true` | Normalizes text for English/Chinese. Improves stability for numbers/dates |
| `latency` | string | No | `"normal"` | Speed vs quality: `normal` (best quality), `balanced` (faster), `low` (lowest latency) |
| `max_new_tokens` | integer | No | `1024` | Maximum audio tokens per text chunk |
| `repetition_penalty` | number | No | `1.2` | Penalty for repeating patterns. Values >1.0 reduce repetition |
| `condition_on_previous_chunks` | boolean | No | `true` | Use previous audio as context for voice consistency |
| `early_stop_threshold` | number | No | `1` | Early stopping threshold. Range: 0-1 |
| `prosody` | object | No | `null` | Speed and volume adjustments: `{speed: 0.5-2.0, volume: -20 to 20}` |

### Output Formats

| Format | Sample Rates | Bitrates | Notes |
|--------|--------------|----------|-------|
| **MP3** | 32kHz, 44.1kHz | 64, 128 (default), 192 kbps | Default format |
| **WAV/PCM** | 8kHz, 16kHz, 24kHz, 32kHz, 44.1kHz | 16-bit, mono | Default: 44.1kHz |
| **Opus** | 48kHz | -1000 (auto), 24, 32 (default), 48, 64 kbps | Best for streaming |

### Full curl Example (JSON)

```bash
curl -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d '{
    "text": "Hello, this is a test of Fish Audio text-to-speech API.",
    "reference_id": "802e3bc2b27e49c2995d23ef70e6ac89",
    "format": "mp3",
    "mp3_bitrate": 128,
    "chunk_length": 200,
    "normalize": true,
    "latency": "normal",
    "temperature": 0.7,
    "top_p": 0.7,
    "repetition_penalty": 1.2,
    "max_new_tokens": 1024,
    "min_chunk_length": 50,
    "condition_on_previous_chunks": true,
    "early_stop_threshold": 1,
    "prosody": {
      "speed": 1.0,
      "volume": 0
    }
  }' \
  --output output.mp3
```

### Full curl Example with MessagePack (Zero-Shot Cloning)

```python
import httpx
import ormsgpack

# Prepare request with reference audio
with open("voice_sample.wav", "rb") as f:
    audio_bytes = f.read()

request_data = {
    "text": "Hello, this is my cloned voice speaking.",
    "references": [
        {
            "audio": audio_bytes,
            "text": "This is the transcript of the reference audio sample."
        }
    ],
    "format": "mp3",
    "chunk_length": 200,
    "normalize": True,
    "latency": "normal"
}

# Pack with MessagePack
packed_data = ormsgpack.packb(request_data)

# Make request
with httpx.Client() as client:
    response = client.post(
        "https://api.fish.audio/v1/tts",
        content=packed_data,
        headers={
            "authorization": "Bearer YOUR_API_KEY",
            "content-type": "application/msgpack",
            "model": "s2-pro"
        }
    )
    
    with open("output.mp3", "wb") as f:
        f.write(response.content)
```

### Response

Returns binary audio data in the specified format.

---

## Models

### Available TTS Models

| Model | Description | Quality | Speed | Use Case |
|-------|-------------|---------|-------|----------|
| `s2-pro` | Latest model with best quality | Excellent | Fastest | Production, content creation |
| `s1` | Stable legacy model | Excellent | Fast | Prototyping, general use |

### Recommended Settings by Use Case

| Use Case | Model | Latency | Bitrate | Normalize | Format |
|----------|-------|---------|---------|-----------|--------|
| **Phone calls** | s2-pro | normal | 64 kbps | true | mp3 |
| **Podcasts / content** | s2-pro | normal | 192 kbps | true | mp3 |
| **Real-time streaming** | s2-pro | balanced | 32 kbps | false | opus |

---

## Emotions & Paralanguage

### S1 Model: Parenthesis Syntax

S1 uses `(parenthesis)` tags with a fixed set of emotions.

### Basic Emotions (24)

| Emotion | Tag | Description |
|---------|-----|-------------|
| Happy | `(happy)` | Cheerful, upbeat tone |
| Sad | `(sad)` | Melancholic, downcast |
| Angry | `(angry)` | Frustrated, aggressive |
| Excited | `(excited)` | Energetic, enthusiastic |
| Calm | `(calm)` | Peaceful, relaxed |
| Nervous | `(nervous)` | Anxious, uncertain |
| Confident | `(confident)` | Assertive, self-assured |
| Surprised | `(surprised)` | Shocked, amazed |
| Satisfied | `(satisfied)` | Content, pleased |
| Delighted | `(delighted)` | Very pleased, joyful |
| Scared | `(scared)` | Frightened, fearful |
| Worried | `(worried)` | Concerned, troubled |
| Upset | `(upset)` | Disturbed, distressed |
| Frustrated | `(frustrated)` | Annoyed, exasperated |
| Depressed | `(depressed)` | Very sad, hopeless |
| Empathetic | `(empathetic)` | Understanding, caring |
| Embarrassed | `(embarrassed)` | Ashamed, awkward |
| Disgusted | `(disgusted)` | Repelled, revolted |
| Moved | `(moved)` | Emotionally touched |
| Proud | `(proud)` | Accomplished, satisfied |
| Relaxed | `(relaxed)` | At ease, casual |
| Grateful | `(grateful)` | Thankful, appreciative |
| Curious | `(curious)` | Inquisitive, interested |
| Sarcastic | `(sarcastic)` | Ironic, mocking |

### Advanced Emotions (25)

| Emotion | Tag | Description |
|---------|-----|-------------|
| Disdainful | `(disdainful)` | Contemptuous, scornful |
| Unhappy | `(unhappy)` | Discontent, dissatisfied |
| Anxious | `(anxious)` | Very worried, uneasy |
| Hysterical | `(hysterical)` | Uncontrollably emotional |
| Indifferent | `(indifferent)` | Uncaring, neutral |
| Uncertain | `(uncertain)` | Doubtful, unsure |
| Doubtful | `(doubtful)` | Skeptical, questioning |
| Confused | `(confused)` | Puzzled, perplexed |
| Disappointed | `(disappointed)` | Let down, dissatisfied |
| Regretful | `(regretful)` | Sorry, remorseful |
| Guilty | `(guilty)` | Culpable, responsible |
| Ashamed | `(ashamed)` | Deeply embarrassed |
| Jealous | `(jealous)` | Envious, resentful |
| Envious | `(envious)` | Wanting what others have |
| Hopeful | `(hopeful)` | Optimistic about future |
| Optimistic | `(optimistic)` | Positive outlook |
| Pessimistic | `(pessimistic)` | Negative outlook |
| Nostalgic | `(nostalgic)` | Longing for the past |
| Lonely | `(lonely)` | Isolated, alone |
| Bored | `(bored)` | Uninterested, weary |
| Contemptuous | `(contemptuous)` | Showing contempt |
| Sympathetic | `(sympathetic)` | Showing sympathy |
| Compassionate | `(compassionate)` | Showing deep care |
| Determined | `(determined)` | Resolved, decided |
| Resigned | `(resigned)` | Accepting defeat |

### Tone Markers (5)

| Tone | Tag | Description |
|------|-----|-------------|
| Hurried | `(in a hurry tone)` | Rushed, urgent |
| Shouting | `(shouting)` | Loud, calling out |
| Screaming | `(screaming)` | Very loud, panicked |
| Whispering | `(whispering)` | Very soft, secretive |
| Soft | `(soft tone)` | Gentle, quiet |

### Audio Effects (10)

| Effect | Tag | Suggested Text |
|--------|-----|----------------|
| Laughing | `(laughing)` | Ha, ha, ha |
| Chuckling | `(chuckling)` | Heh, heh |
| Sobbing | `(sobbing)` | (optional) |
| Crying Loudly | `(crying loudly)` | (optional) |
| Sighing | `(sighing)` | sigh |
| Groaning | `(groaning)` | ugh |
| Panting | `(panting)` | huff, puff |
| Gasping | `(gasping)` | gasp |
| Yawning | `(yawning)` | yawn |
| Snoring | `(snoring)` | zzz |

### Special Effects

| Effect | Tag | Description |
|--------|-----|-------------|
| Short pause | `(break)` | Brief pause |
| Long pause | `(long-break)` | Extended pause |
| Audience laughter | `(audience laughing)` | Crowd laughing |
| Background laughter | `(background laughter)` | Ambient laughter |
| Crowd laughter | `(crowd laughing)` | Large group laughing |

### Usage Examples (S1)

```
(happy) What a beautiful day!
(sad) I'm sorry for your loss.
(excited) We won the championship!
(sad)(whispering) I'll miss you so much.
(angry)(shouting) Get out of here now!
```

### S2 Model: Natural Language Syntax

S2 uses `[bracket]` syntax with free-form natural language descriptions:

```
[speaking excitedly and with joy] I just won the lottery!
[speaking softly with a hint of sadness] I'm sorry for your loss.
[sounding confident and professional] Welcome to our company.
```

---

## Fine-Grained Control

### Phoneme Control

Specify exact pronunciations using phoneme tags.

#### English (CMU Arpabet)

```
I am an <|phoneme_start|>EH N JH AH N IH R<|phoneme_end|>.
```

#### Chinese (Pinyin)

```
我是一个<|phoneme_start|>gong1<|phoneme_end|><|phoneme_start|>cheng2<|phoneme_end|><|phoneme_start|>shi1<|phoneme_end|>。
```

### Paralanguage Effects (S1/S2)

| Effect | Tag | Description | Stage |
|--------|-----|-------------|-------|
| `(break)` | Short pause | 0.5-1 second pause | Experimental |
| `(long-break)` | Extended pause | 2-3 second pause | Experimental |
| `(breath)` | Breathing sound | Natural breath | Experimental |
| `(laugh)` | Laughter sound | Single laugh | Experimental |
| `(cough)` | Coughing sound | Single cough | Experimental |
| `(lip-smacking)` | Lip smacking sound | Mouth sound | Experimental |
| `(sigh)` | Sighing sound | Exhale | Experimental |

**Note:** Effects `(laugh)`, `(cough)`, `(lip-smacking)`, and `(sigh)` are still developing. You may need to repeat them for better results.

### Pause Words

Use natural pause words to control rhythm:
- English: "um", "uh"
- Chinese: "嗯", "啊"

### Normalization

For fine-grained control to work best, set `normalize: false` in your request. This prevents the API from altering intonation of control tags.

**Trade-off:** Disabling normalization may reduce stability for numbers, dates, and URLs.

---

## WebSocket Streaming

### Endpoint

```
wss://api.fish.audio/v1/tts/live
```

### Connection Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Authorization` | Yes | `Bearer YOUR_API_KEY` |
| `model` | Yes | `s1` (WebSocket currently supports s1) |

### Message Flow

1. **Client** sends `StartEvent` with configuration
2. **Client** sends one or more `TextEvent` messages with text chunks
3. **Client** optionally sends `FlushEvent` to force immediate synthesis
4. **Client** sends `CloseEvent` (with `event: "stop"`) when done
5. **Server** sends multiple `AudioEvent` messages with audio chunks
6. **Server** sends `FinishEvent` when complete

### Client-to-Server Events

#### StartEvent

```json
{
  "event": "start",
  "request": {
    "text": "",
    "reference_id": "802e3bc2b27e49c2995d23ef70e6ac89",
    "format": "mp3",
    "chunk_length": 200,
    "latency": "balanced",
    "temperature": 0.7,
    "top_p": 0.7,
    "normalize": true,
    "prosody": {
      "speed": 1.0,
      "volume": 0
    }
  }
}
```

#### TextEvent

```json
{
  "event": "text",
  "text": "Hello, this is streaming text. "
}
```

#### FlushEvent

```json
{
  "event": "flush"
}
```

#### CloseEvent

```json
{
  "event": "stop"
}
```

### Server-to-Client Events

#### AudioEvent

```json
{
  "event": "audio",
  "audio": "<binary audio data>"
}
```

#### FinishEvent

```json
{
  "event": "finish",
  "reason": "stop"
}
```

Reasons:
- `stop`: Normal completion
- `error`: An error occurred

### Python WebSocket Example

```python
from fishaudio import FishAudio

client = FishAudio(api_key="YOUR_API_KEY")

# Stream audio chunks
audio_stream = client.tts.stream(
    text="Streaming this text in real-time",
    reference_id="model_id"
)

with open("stream_output.mp3", "wb") as f:
    for chunk in audio_stream:
        f.write(chunk)
```

### JavaScript WebSocket Example

```javascript
import { FishAudioClient, RealtimeEvents } from "fish-audio";
import { writeFile } from "fs/promises";
import path from "path";

async function* makeTextStream() {
    const chunks = [
        "Hello from Fish Audio! ",
        "This is a realtime text-to-speech test. ",
        "We are streaming multiple chunks over WebSocket.",
    ];
    for (const chunk of chunks) {
        yield chunk;
    }
}

const fishAudio = new FishAudioClient({ apiKey: process.env.FISH_API_KEY });

const request = { text: "" };
const connection = await fishAudio.textToSpeech.convertRealtime(request, makeTextStream());

const chunks = [];
connection.on(RealtimeEvents.OPEN, () => console.log("WebSocket opened"));
connection.on(RealtimeEvents.AUDIO_CHUNK, (audio) => {
    if (audio instanceof Uint8Array || Buffer.isBuffer(audio)) {
        chunks.push(Buffer.from(audio));
    }
});
connection.on(RealtimeEvents.ERROR, (err) => console.error("Error:", err));
connection.on(RealtimeEvents.CLOSE, async () => {
    const outPath = path.resolve(process.cwd(), "out.mp3");
    await writeFile(outPath, Buffer.concat(chunks));
    console.log("Saved to", outPath);
});
```

---

## Speech-to-Text (ASR)

### Endpoint

```
POST /v1/asr
```

**Status:** BETA

### Content Types Accepted

- `multipart/form-data`
- `application/msgpack`

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `audio` | binary | Yes | - | Audio file to transcribe |
| `language` | string | No | `null` | Language code for the speech |
| `ignore_timestamps` | boolean | No | `true` | Return precise timestamps (slower for audio < 30s) |

### curl Example

```bash
curl -X POST "https://api.fish.audio/v1/asr" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "audio=@recording.wav" \
  -F "language=en" \
  -F "ignore_timestamps=true"
```

### Response

```json
{
  "text": "This is the transcribed text from the audio.",
  "duration": 12.5,
  "segments": [
    {
      "text": "This is the transcribed",
      "start": 0.0,
      "end": 5.2
    },
    {
      "text": "text from the audio.",
      "start": 5.3,
      "end": 12.5
    }
  ]
}
```

---

## Voice Cloning (Create Model)

### Endpoint

```
POST /model
```

### Content Types Accepted

- `multipart/form-data`
- `application/msgpack`

### Request Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `type` | string | Yes | - | Model type: `tts` |
| `title` | string | Yes | - | Model name/title |
| `train_mode` | string | Yes | - | Training mode: `fast` (instantly available) |
| `voices` | binary/array | Yes | - | Audio file(s) for voice training |
| `visibility` | string | No | `public` | `public`, `unlist`, or `private` |
| `description` | string | No | `null` | Model description |
| `cover_image` | binary | No | `null` | Cover image (required if public) |
| `texts` | string/array | No | `null` | Transcripts corresponding to voices (ASR used if not provided) |
| `tags` | string/array | No | `null` | Model tags |
| `enhance_audio_quality` | boolean | No | `false` | Enhance audio quality during training |

### curl Example

```bash
curl -X POST "https://api.fish.audio/model" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -F "type=tts" \
  -F "title=My Custom Voice" \
  -F "train_mode=fast" \
  -F "visibility=private" \
  -F "voices=@sample1.wav" \
  -F "voices=@sample2.wav" \
  -F "texts=This is the first sample transcript." \
  -F "texts=This is the second sample transcript." \
  -F "enhance_audio_quality=false"
```

### Response

```json
{
  "_id": "abc123def456",
  "type": "tts",
  "title": "My Custom Voice",
  "description": "",
  "cover_image": "",
  "train_mode": "fast",
  "state": "trained",
  "tags": [],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z",
  "languages": ["en"],
  "visibility": "private",
  "like_count": 0,
  "mark_count": 0,
  "shared_count": 0,
  "task_count": 0,
  "author": {
    "_id": "user123",
    "nickname": "UserName",
    "avatar": "https://..."
  }
}
```

### Model States

| State | Description |
|-------|-------------|
| `created` | Model created, waiting to start training |
| `training` | Currently training |
| `trained` | Training complete, model ready |
| `failed` | Training failed |

---

## Pricing & Rate Limits

### Pricing

**Pay-as-you-go** - No subscription fees or monthly minimums.

#### Text-to-Speech

| Model | Price |
|-------|-------|
| `s2-pro` | $15.00 / million UTF-8 bytes |
| `s1` | $15.00 / million UTF-8 bytes |

> 1M UTF-8 bytes ≈ 180,000 English words ≈ 12 hours of speech

#### Speech-to-Text

| Model | Price |
|-------|-------|
| `transcribe-1` | $0.36 / audio hour |

- Duration rounded up to nearest second

### Rate Limits

#### Concurrent Request Limits

| Tier | Spending Threshold | Concurrent Requests |
|------|-------------------|---------------------|
| Starter | < $100 paid | 5 requests |
| Elevated | >= $100 paid | 15 requests |
| Enterprise | Custom | Custom limits |

Contact [support@fish.audio](mailto:support@fish.audio) for enterprise pricing.

---

## Error Codes

### HTTP Status Codes

| Status | Description | Common Causes |
|--------|-------------|---------------|
| `200` | Success | Request fulfilled |
| `201` | Created | Model created successfully |
| `401` | Unauthorized | Invalid or missing API key |
| `402` | Payment Required | Insufficient credits |
| `422` | Validation Error | Invalid request parameters |

### 422 Validation Error Format

```json
[
  {
    "loc": ["field_name"],
    "type": "error_type",
    "msg": "Error message",
    "ctx": "Error context",
    "in": "body"
  }
]
```

### Common Error Messages

| Error | Solution |
|-------|----------|
| `No permission -- see authorization schemes` | Check your API key is valid and in the correct format |
| `No payment -- see charging schemes` | Add credits to your account |
| Invalid model ID | Verify the `reference_id` exists and is accessible |
| Invalid audio format | Ensure audio is WAV, MP3, or FLAC |
| Request too large | Reduce chunk size or split into smaller requests |

---

## SDKs

### Python SDK

```bash
pip install fish-audio-sdk
```

```python
from fishaudio import FishAudio
from fishaudio.utils import save

client = FishAudio()

# Generate speech
audio = client.tts.convert(
    text="Hello, world!",
    reference_id="your_voice_model_id"
)
save(audio, "output.mp3")
```

### JavaScript SDK

```bash
npm install fish-audio
```

```javascript
import { FishAudioClient } from "fish-audio";
import { writeFile } from "fs/promises";

const fishAudio = new FishAudioClient({ apiKey: process.env.FISH_API_KEY });

const audio = await fishAudio.textToSpeech.convert({
    text: "Hello, world!",
    reference_id: "your_voice_model_id",
});

const buffer = Buffer.from(await new Response(audio).arrayBuffer());
await writeFile("output.mp3", buffer);
```

---

## Resources

- **Documentation:** [docs.fish.audio](https://docs.fish.audio)
- **API Keys:** [fish.audio/app/api-keys](https://fish.audio/app/api-keys)
- **Voice Discovery:** [fish.audio/discovery](https://fish.audio/discovery)
- **Discord Community:** [discord.gg/fish-audio](https://discord.gg/fish-audio)
- **Email Support:** [support@fish.audio](mailto:support@fish.audio)
- **OpenAPI Spec:** [docs.fish.audio/api-reference/openapi.json](https://docs.fish.audio/api-reference/openapi.json)

---

## Quick Reference Card

### Essential Headers
```
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json (or application/msgpack)
model: s2-pro
```

### Quick TTS Request
```bash
curl -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d '{"text":"Hello world","reference_id":"VOICE_ID","format":"mp3"}' \
  --output output.mp3
```

### Common Voice IDs (from Discovery)
- Find voice IDs in URLs: `fish.audio/voice/VOICE_ID`
- Or use the [Discovery page](https://fish.audio/discovery)

### Model Selection Flow
1. Default to `s2-pro` for best quality
2. Use `normalize: true` for numbers/dates
3. Use `normalize: false` for fine-grained control
4. Use `latency: balanced` for real-time applications
5. Use `format: opus` with `opus_bitrate: 32` for streaming

---

*Document compiled from Fish Audio documentation. For the latest updates, visit [docs.fish.audio](https://docs.fish.audio)*
