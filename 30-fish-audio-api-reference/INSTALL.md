# Install Checklist - Fish Audio API Reference (Skill 30)

> **N24 — Use the teach-yourself-protocol (Skill 01):** Before any action in this skill, the installing sub-agent MUST read every file under skills/01-teach-yourself-protocol/ and follow its procedural read-order. No shortcuts.


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
- Resume at: Skill 30 (30-fish-audio-api-reference) INSTALL.md Step 4
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

## Step 3 - Index with Gemini Engine

```bash
python3 ~/.openclaw/scripts/gemini-indexer.py
# Handled by gemini-indexer.py
```

Wait for both commands to complete before continuing.

---

## Step 4 - Add Your Credentials (Skip If Pending)

> **Write to the CANONICAL store, never a hardcoded path.** This step used to
> write to `~/.clawdbot/clawdbot.json` and `~/clawd/secrets/.env` — two
> pre-rename paths. `qc-fish-audio-api-reference.sh` reads `$SECRETS_ENV`,
> resolved by `lib-shared.sh` to `~/.openclaw/secrets/.env` (Mac) or
> `/data/.openclaw/secrets/.env` (VPS). The credential was written where nothing
> read it, and the check then reported it absent on a correctly configured box.
> Resolve the path; do not type one.

Run this block. It resolves the canonical store, migrates a value from a legacy
path if one is still there, and writes to the resolved store only.

```bash
# 1. Resolve the canonical secrets path. Same resolution the bundled QC uses.
SKILLS_DIR="$HOME/.openclaw/skills"; [ -d /data/.openclaw/skills ] && SKILLS_DIR=/data/.openclaw/skills
[ -f "$SKILLS_DIR/lib-shared.sh" ] && . "$SKILLS_DIR/lib-shared.sh"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() {
    if [ -d /data/.openclaw ]; then export SECRETS_ENV="/data/.openclaw/secrets/.env"
    else export SECRETS_ENV="$HOME/.openclaw/secrets/.env"; fi
  }
fi
resolve_platform_paths
echo "Canonical secrets store: $SECRETS_ENV"
mkdir -p "$(dirname "$SECRETS_ENV")" && touch "$SECRETS_ENV" && chmod 600 "$SECRETS_ENV"

# 2. One-time MIGRATION READ from the legacy store (read only — never written to
#    again). Skip silently when there is nothing to migrate.
LEGACY_ENV="$HOME/clawd/secrets/.env"
if [ -f "$LEGACY_ENV" ] && [ "$LEGACY_ENV" != "$SECRETS_ENV" ]; then
  for k in FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID; do
    if grep -q "^${k}=" "$LEGACY_ENV" 2>/dev/null && ! grep -q "^${k}=" "$SECRETS_ENV" 2>/dev/null; then
      grep "^${k}=" "$LEGACY_ENV" >> "$SECRETS_ENV"
      echo "migrated $k from the legacy store to the canonical store"
    fi
  done
fi

# 3. Write the values the owner supplied, to the RESOLVED store only.
#    Replace an existing line rather than appending a duplicate.
set_secret() {  # set_secret NAME VALUE — never echoes the value
  local name="$1" value="$2" tmp
  tmp="$(mktemp)"
  grep -v "^${name}=" "$SECRETS_ENV" 2>/dev/null > "$tmp" || true
  printf '%s=%s\n' "$name" "$value" >> "$tmp"
  mv "$tmp" "$SECRETS_ENV" && chmod 600 "$SECRETS_ENV"
  echo "$name: written to $SECRETS_ENV"
}
set_secret FISH_AUDIO_API_KEY  "<the API key the owner supplied>"
set_secret FISH_AUDIO_VOICE_ID "<the voice/model id the owner supplied>"

# 4. Confirm PRESENCE only — never print a credential value.
for k in FISH_AUDIO_API_KEY FISH_AUDIO_VOICE_ID; do
  if grep -q "^${k}=." "$SECRETS_ENV"; then echo "$k: SET"; else echo "$k: NOT-SET"; fi
done
```

Every line above must report `SET`. If either reports `NOT-SET`, stop — the
credential is not where `qc-fish-audio-api-reference.sh` reads it, and the QC
step will fail.

---

## Step 5 - Test the API

Run this test to confirm your credentials work:

```bash
curl -s -X POST "https://api.fish.audio/v1/tts" \
  -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -H "model: s2.1-pro" \
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

Skill 30 is complete when:
- [ ] API reference doc is in `~/Downloads/openclaw-master-files/service-integrations/fish-audio/`
- [ ] Gemini Engine has indexed and embedded the document
- [ ] `FISH_AUDIO_API_KEY` and `FISH_AUDIO_VOICE_ID` both report `SET` in the
      CANONICAL store (`$SECRETS_ENV` — `~/.openclaw/secrets/.env` on Mac,
      `/data/.openclaw/secrets/.env` on VPS), which is the file
      `qc-fish-audio-api-reference.sh` reads
- [ ] Test curl returned 200 with audio output
