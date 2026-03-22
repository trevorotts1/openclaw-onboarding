# Migration Guide: Google Embedding 2 to Google Gemini Embedding 2

**For:** Existing users who installed the onboarding package before March 18, 2026
**When:** After updating to the latest onboarding package
**What:** Replace the old Google Embedding 2 local search engine with Google Gemini Embedding 2

---

## What Changed

| Before (old) | After (new) |
|--------------|-------------|
| Google Embedding 2 local SQLite search (`Google Embedding 2 retrieval query`, `check Google Embedding 2 retrieval status`) | Google Gemini Embedding 2 API |
| `refresh the Google Embedding 2 retrieval layer` to index | `python3 ~/clawd/scripts/gemini-indexer.py` |
| `Google Embedding 2 retrieval query coaching-personas "query"` | `python3 ~/clawd/scripts/gemini-search.py "query"` |
| `check Google Embedding 2 retrieval status` to check index | `python3 ~/clawd/scripts/gemini-indexer.py --status` |
| Local SQLite database at `~/.cache/google embedding 2/index.sqlite` | Gemini API (no local database needed) |

---

## Do I Need to Migrate?

**New user installing fresh?** No. The install scripts handle everything automatically.

**Existing user with Google Embedding 2 already set up?** Yes. Follow the steps below.

---

## Migration Steps

### Step 1: Get a Google API Key

1. Go to https://aistudio.google.com/app/apikey
2. Click "Create API key"
3. Copy the key (starts with `AIza...`)

### Step 2: Set the Environment Variable

Add this line to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export GOOGLE_API_KEY="AIza..."
```

Then reload your shell:

```bash
source ~/.zshrc
```

### Step 3: Install the Python SDK

```bash
pip3 install google-genai numpy
```

### Step 4: Update the Onboarding Package

**VPS/Docker users:**
```bash
cd ~/Downloads/openclaw-master-files/OpenClaw Onboarding
curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash
```

**Or manually pull the latest:**
```bash
cd /path/to/your/onboarding-folder
git pull origin main
```

### Step 5: Re-index Your Personas

```bash
python3 ~/clawd/scripts/gemini-indexer.py
```

This reads all persona blueprint files and indexes them with Gemini Embedding 2.

### Step 6: Verify

```bash
# Check index status
python3 ~/clawd/scripts/gemini-indexer.py --status

# Test a search
python3 ~/clawd/scripts/gemini-search.py "leadership habits"
```

If you get results back, the migration is complete.

### Step 7: Update OpenClaw Config (if applicable)

If your `openclaw.json` has a `memory.backend` setting, change it:

```json
"memory": {
  "backend": "gemini"
}
```

And under `agents.defaults.memorySearch`:

```json
"memorySearch": {
  "provider": "gemini",
  "model": "models/gemini-embedding-2-preview"
}
```

---

## Clean Up Old Google Embedding 2 (Optional)

Your old Google Embedding 2 data is not deleted automatically. To reclaim disk space:

```bash
# Remove old Google Embedding 2 cache
rm -rf ~/.cache/google embedding 2/

# Uninstall Google Embedding 2 if you installed it globally
npm uninstall -g google embedding 2
```

To keep as backup for 30 days (recommended):

```bash
mv ~/.cache/google embedding 2/ ~/.cache/google embedding 2-backup/
```

---

## Troubleshooting

**"GOOGLE_API_KEY not found"**
```bash
echo $GOOGLE_API_KEY
# If empty, set it and reload shell
```

**"google-genai module not found"**
```bash
pip3 install google-genai
```

**"404 NOT_FOUND" on embedding model**
Make sure you are using `models/gemini-embedding-2-preview`, not `text-embedding-004` (which was removed from the API).

**"google embedding 2: command not found" errors in scripts**
You are running an outdated version of the onboarding package. Pull the latest from GitHub.

**build-workforce.py fails**
Make sure `GOOGLE_API_KEY` is set and `google-genai` is installed. The script now uses Gemini API instead of Google Embedding 2.

---

## FAQ

**Q: Why did we replace Google Embedding 2?**
A: Google Embedding 2 is a local SQLite tool that breaks on Linux VPS containers, only supports text, and requires manual maintenance. Gemini Embedding 2 is a managed API with multimodal support (text, images, audio, video), better search quality, and zero local maintenance.

**Q: Will this cost money?**
A: Google AI Studio has a generous free tier. Indexing 40 personas and running occasional searches is well within free limits. Check https://ai.google.dev/pricing for current rates.

**Q: Do I need to rebuild my personas?**
A: No. The persona blueprint files are unchanged. Only the search/retrieval engine changed. Your content is preserved.

**Q: What environment variable should I use?**
A: `GOOGLE_API_KEY`. If you also have `GEMINI_API_KEY` set, the SDK will use `GOOGLE_API_KEY` first.

---

## Summary Checklist

- [ ] Google API key obtained from AI Studio
- [ ] `GOOGLE_API_KEY` set in shell profile
- [ ] `pip3 install google-genai numpy` completed
- [ ] Onboarding package updated to latest
- [ ] `python3 ~/clawd/scripts/gemini-indexer.py` ran successfully
- [ ] `python3 ~/clawd/scripts/gemini-search.py "test query"` returns results
- [ ] OpenClaw config updated (`memory.backend: "gemini"`)
- [ ] Old Google Embedding 2 cache cleaned up (optional)

**Migration is complete when:** `python3 ~/clawd/scripts/gemini-search.py "leadership"` returns persona results and `build-workforce.py` runs without errors.
