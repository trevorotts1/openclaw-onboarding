# Install Checklist - Fish Audio API Reference (Skill 31)

Complete every step in order.

---

## Do You Have Your Fish Audio Credentials?

**If YES** - proceed to Step 1.

**If NO** - do Steps 1 through 3, then run this to flag setup as pending:

```bash
cat >> ~/.openclaw/skills/.pending-setup.md << 'EOF'

## fish-audio
- Status: PENDING
- What is needed:
  - Fish Audio API key (sign up free at fish.audio, then go to fish.audio/app/api-keys)
  - Fish Audio Voice ID (set up your voice clone, then copy the model ID from the URL)
- Resume at: Skill 31 INSTALL.md Step 4
EOF
```

Your agent will remind you to complete setup once you have your credentials.

---

## Step 1 - Create the Master Files Folder

```bash
mkdir -p ~/Downloads/openclaw-master-files/service-integrations/fish-audio
```

---

## Step 2 - Copy the API Reference Document

```bash
cp "$(dirname "$0")/references/fish-audio-api-reference.md" \
   ~/Downloads/openclaw-master-files/service-integrations/fish-audio/fish-audio-api-reference.md
```

---

## Step 3 - Index with QMD

```bash
qmd update
qmd embed
```

Wait for both commands to complete before continuing.

---

## Step 4 - Add Your Credentials (Skip If Pending)

Add to `~/.clawdbot/clawdbot.json` under `env.vars`:

```json
"FISH_AUDIO_API_KEY": "your_api_key_here",
"FISH_AUDIO_VOICE_ID": "your_voice_id_here"
```

Also add to `~/clawd/secrets/.env`:

```
FISH_AUDIO_API_KEY=your_api_key_here
FISH_AUDIO_VOICE_ID=your_voice_id_here
```

---

## Step 5 - Test the API

Run this test to confirm your credentials work:

```bash
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2-pro" \
  -d "{
    \"text\": \"Fish Audio is connected and working.\",
    \"reference_id\": \"$FISH_AUDIO_VOICE_ID\",
    \"format\": \"mp3\",
    \"mp3_bitrate\": 64,
    \"normalize\": true,
    \"latency\": \"normal\"
  }" \
  --output /tmp/fish_audio_test.mp3 \
  -w "%{http_code}"
```

You should get `200` and a file at `/tmp/fish_audio_test.mp3`. Play it to confirm your voice.

---

## Done

Skill 31 is complete when:
- [ ] API reference doc is in `~/Downloads/openclaw-master-files/service-integrations/fish-audio/`
- [ ] QMD has indexed and embedded the document
- [ ] Credentials are stored in `clawdbot.json` and `.env`
- [ ] Test curl returned 200 with audio output
