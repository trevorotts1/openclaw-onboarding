# KIE Audio QC Checklist (SPEC section 9.5 verbatim + file-level checks)

## 1. TTS QC — after generation

- [ ] Valid playable file
- [ ] Language (matches the requested/declared language)
- [ ] Voice identity (the requested voice, not a different one)
- [ ] Pronunciation (names, acronyms, foreign words rendered correctly)
- [ ] Pace (matches requested pace: Natural / Rapid Fire / The Drift / Staccato)
- [ ] Style/emotion (matches requested style: Vocal Smile / Newscaster / Whisper /
      Empathetic / Promo/Hype / Deadpan)
- [ ] Clipping/distortion (no audible clipping at peaks, no artifacts)
- [ ] Speaker ordering/dialogue correctness (multi-speaker tasks: each turn is
      spoken by the right speaker, in order)

## 2. Music QC — after generation

- [ ] Playable file
- [ ] Requested duration/model behavior (duration only effective for V5_5
      custom; check the returned duration)
- [ ] Musical genre/style (matches prompt/style intent)
- [ ] Vocals/instrumental intent (instrumental request returned instrumental;
      vocal request returned vocals)
- [ ] Lyrics fidelity when supplied (lyrics match the supplied text)
- [ ] No truncation/clipping (track not cut off early; no clipping)
- [ ] Callback completion stage (reached `complete` — `text`/`first` stages are
      not finished output)

## 3. STT QC

- [ ] n/a — STT is `ADVERTISED_NOT_YET_VERIFIED`, `dispatch_enabled: false`.
  Nothing can be generated, so nothing can be QC'd. See `references/stt.md`.
  Do NOT fabricate a check for a route that must not be dispatched.

## 4. File-level checks (before declaring QC pass)

- [ ] File downloads and opens in a player (playable — not a 0-byte file, not an
      HTML error page saved as .mp3).
- [ ] Duration sanity via file header (ffprobe/mediainfo or equivalent): duration
      roughly matches the request; a duration of 0s or an absurd value = failure.
- [ ] Sample rate sanity (e.g. 44.1kHz/48kHz expected; a corrupted header is a
      failure, not a pass).
- [ ] No truncation: file length matches the announced duration (no cut-off tail).

## 5. Retry ladder (SPEC section 15)

1. Same model, corrected prompt/parameters.
2. Same model, alternate valid mode/reference encoding.
3. Another compatible model in the same provider only if model selection was
   automatic or user permits it.
4. Another provider only when generic provider routing is allowed or user approves.
5. Stop after the configured retry cap and report why.

Never silently burn credits across multiple models. API success (a result URL)
is NOT audio QC — the file must be listened to/analyzed per the lists above.

## 6. Persistence

KIE media commonly expires after 14 days. Persist final audio into durable
storage immediately when the workflow requires long-term access.
