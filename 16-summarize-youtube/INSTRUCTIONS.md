# INSTRUCTIONS.md

## Daily use
1. Summary command:
```bash
summarize "https://youtu.be/VIDEO_ID" --youtube auto --length short
```
2. Transcript extraction:
```bash
summarize "https://youtu.be/VIDEO_ID" --youtube auto --extract-only
```

## Key policy
1. Load keys from `.env`.
2. Try OpenAI first.
3. If OpenAI fails, retry with Gemini.
4. If both fail, stop and return exact error.
