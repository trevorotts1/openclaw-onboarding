#!/usr/bin/env bash
# lib-caption-guard.sh — THE ONE "is this transcript real?" rule for Skill 26.
#
# T0-59: every entry point in this skill validated the transcript by FILE
# EXISTENCE. The transcription tool writes a subtitle file even when it
# recognises no speech, so silent audio, an unsupported language, or a
# transcription that yields nothing all passed the check, reached the burn-in
# filter, and produced a video announced as captioned with no captions in it.
#
# A subtitle file is only a transcript if it carries at least one timing cue AND
# at least one line of caption text under a cue. Both entry points and the
# animated path resolve through this one rule so the branches cannot diverge.
#
# Source it, then call:  assert_srt_has_cues <srt-path> <human-readable-source>
#
# Exit code 3 == AF-CAPTION-EMPTY-TRANSCRIPTION (distinct from the usage exit 1
# and from FFmpeg's own failures), so a caller can branch on the reason.

CAPTION_EMPTY_TRANSCRIPTION_EXIT=3

# Number of SRT timing cues ("HH:MM:SS,mmm --> HH:MM:SS,mmm") in a file.
srt_cue_count() {
  local f="$1" n
  [ -f "$f" ] || { printf '0\n'; return 0; }
  n="$(grep -cE '[0-9]{2}:[0-9]{2}:[0-9]{2}[,.][0-9]{3}[[:space:]]*-->' "$f" 2>/dev/null)" || n=0
  printf '%s\n' "${n:-0}"
}

# Number of non-blank caption text lines that sit directly under a timing cue.
# A cue with no text renders nothing, so it is not a caption.
srt_caption_line_count() {
  local f="$1"
  [ -f "$f" ] || { printf '0\n'; return 0; }
  awk '
    prev ~ /-->/ && $0 ~ /[^[:space:]]/ { c++ }
    { prev = $0 }
    END { print c + 0 }
  ' "$f" 2>/dev/null || printf '0\n'
}

# Hard gate. Fails with a NAMED error identifying an empty transcription rather
# than handing an empty subtitle file to the burn-in filter.
assert_srt_has_cues() {
  local srt="$1" source_label="${2:-the input media}" cues texts

  if [ ! -f "$srt" ]; then
    echo "Error: AF-CAPTION-EMPTY-TRANSCRIPTION — no subtitle file was produced for ${source_label} (expected: ${srt})." >&2
    exit "$CAPTION_EMPTY_TRANSCRIPTION_EXIT"
  fi

  cues="$(srt_cue_count "$srt")"
  texts="$(srt_caption_line_count "$srt")"

  if [ "$cues" -lt 1 ] || [ "$texts" -lt 1 ]; then
    echo "Error: AF-CAPTION-EMPTY-TRANSCRIPTION — the transcription of ${source_label} produced ${cues} timing cue(s) and ${texts} caption line(s)." >&2
    echo "  A subtitle file exists at ${srt}, but it contains no captions, so burning it in would produce a video announced as captioned with nothing in it." >&2
    echo "  Likely causes: silent or near-silent audio, an unsupported spoken language, or a transcription model that recognised no speech." >&2
    echo "  Fix the audio or pass a larger --model, then re-run. Nothing was rendered." >&2
    exit "$CAPTION_EMPTY_TRANSCRIPTION_EXIT"
  fi

  echo "Transcript check: ${cues} timing cue(s), ${texts} caption line(s) — proceeding."
}
