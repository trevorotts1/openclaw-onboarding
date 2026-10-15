# Audio Policy and Mode-Specific Mixing (MG-023)

One audio policy governs every V2 assembly. It lives in
`scripts/audio_policy.py`; the assembler (`scripts/assemble.py`)
resolves it exactly once, when the compiled plan is loaded, and
nothing downstream re-reads the media registry for audio decisions.
That is the structural fix for D-ASSEMBLE-MUSIC-RESET: the old
assembler resolved the score (supplied or synthesized) and then
reassigned the music path from the manifest, silently discarding
the resolution. In the plan path there is no second read to reset
from, and the legacy bridge also resolves exactly once (it did
since MG-022; the regression test pins it).

## Modes

The compiled timeline's `audio_owner` is the single authority on
which mode a job is in:

| audio_owner | mode | Meaning |
| --- | --- | --- |
| `none` | `none` | The insert is silent. No narration, SFX, or music may be placed. |
| `parent` | `inherited` | The parent (deck or long-form video) owns narration and music. The insert contributes picture only. |
| `self` | `own` | This job owns its final mix: narration, music, SFX, ducking, stems, and loudness. |

The four delivery shapes map onto these modes the way Section 4.1
of the directive declares: `powerpoint_graphic` is `none`;
`vsl_desktop` and `vsl_mobile` are `inherited` (silent inserts,
parent owns narration/music); `standalone_video` is `own` when the
brief requires narration or music and `none` when it does not.

## Resolution (once, at plan load)

`resolve_audio_plan` in `scripts/audio_policy.py` takes the
timeline's `audio_owner`, the narration and SFX ids the sidecar
places, and the media registry, and returns the resolved plan
(schema: `references/audio-policy.schema.json`, record
`resolvedAudioPlan`). The assembler stores it on the job and copies
it into the probe record (`audio_plan`).

Rules, in order:

1. An unknown or missing `audio_owner` fails
   (`ASSEMBLE_AUDIO_MODE_VIOLATION`, Section 16.9 `MG_MODE_MISMATCH`).
   A registry `audio.mode` that contradicts the resolved mode fails
   the same way. The registry never overrides the compiled plan.
2. Mode `none`: any placed narration or SFX, or a registry music
   entry, fails by name. Silence is verified, not assumed: the
   deliverable carries no audio stream.
3. Mode `inherited`: placed narration or SFX fails by name (the
   parent owns the narration; a second narrator is a defect, not a
   variation). A registry music entry is EXCLUDED, not mixed: the
   exclusion is recorded in the plan (`exclusions`, code
   `ASSEMBLE_AUDIO_PARENT_OWNED`) and surfaced in the probe record,
   so carrying a bed inside an inherited package is visible rather
   than silently doubled under the parent's bed.
4. Mode `own`: the registry `music` entry declares exactly one
   source, a supplied track (`{"path": ...}`, from the approved
   voice/music providers or a supplied file) or a synthesized score
   (`{"synthesized": {"bpm": ..., "seed": ...}}`). A synthesized
   declaration is executed exactly once during resolution by
   `scripts/synth-score.py`, into `<media>/generated/`, and the
   produced path is written back into the resolved plan; a matching
   prior synthesis (same bpm, seed, and duration) is reused.
   Synthesis is an option, never a requirement and never the
   definition of quality.
5. Declarations are read from the registry `audio` record when
   present, else the older `mix` record. `musicVolume` defaults to
   1.0. `ducking`, when the key is present, is honored as declared
   (explicit `null` means no ducking); when the key is absent and
   narration and music coexist, the policy default applies
   (threshold 0.02, ratio 8, attack 20 ms, release 400 ms, the
   values the legacy bridge shipped, adopted here as policy).
6. Ducking is keyed on the narration stem only (the MG-022 graph
   splits the narration stem for the sidechain). SFX never duck the
   music; this layer only decides whether ducking exists, the graph
   decides what feeds it.
7. A loudness target exists only in mode `own` with at least one
   audio source: the modes that require an independent final mix
   are the only ones a declared target applies to. Declared values
   win; otherwise the policy default is -14 LUFS integrated,
   -1 dBTP true peak.

Before the graph is built, every narration, SFX, and music source
is decoded and measured for clipping (peak at or above 99.9% of
full scale with more than 0.1% of samples at full scale). A clipped
source fails the assembly (`ASSEMBLE_AUDIO_CLIPPING`) instead of
being normalized into invisibility; repair belongs at the provider
or supply step.

## Mixing, stems, and the measured loudness finish

The graph itself is MG-022's (see `references/assembly.md`): exact
sample windows, narration sidechain ducking, SFX placed at compiled
sample positions, no `-shortest` anywhere.

In mode `own` the assembler additionally:

- Emits one stem per contributing role (`stems/narration.wav`,
  `stems/music.wav`, `stems/sfx.wav` beside the deliverable's
  workdir; paths and sizes in the probe record). Stems are tapped
  from the mix ingredients: the narration stem is pre-placement-gain,
  the music stem is post-ducking (what actually sits under the
  narration), the SFX stem is the placed sum. Stems are the mix's
  ingredients, before the loudness finish.
- Writes the mix itself as PCM in the same encode invocation and
  runs a MEASURED two-pass loudnorm: pass one measures the mix
  (integrated loudness, true peak, LRA, threshold, offset); pass
  two applies loudnorm with the measured values and the resolved
  target, encoding the audio to AAC exactly once from the filtered
  PCM with the sample rate set explicitly to 48000 Hz. The legacy
  compatibility path keeps its historical single-pass finish
  untouched (it is a frozen bridge; its 96 kHz resample quirk and
  its AAC padding are recorded there, not silently imported here).

## Verification of the encoded output

The finished file is decoded and measured; requested filter
settings are never taken as evidence. In mode `own`:

- Output clipping: peak above -0.3 dBFS fails
  (`ASSEMBLE_AUDIO_CLIPPING`).
- Loudness: measured integrated loudness must land within 1.0 LU of
  the target and true peak no more than 0.5 dB over the ceiling
  (`ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET`).
- Narration presence: for every placed segment, the source's
  dominant spectral bands (Hann-windowed, third-octave grid) must
  be present in the decoded output across the planned span at a
  energy-weighted band ratio of at least 0.25 (only bands
  carrying at least a tenth of the strongest band's energy vote, so
  codec noise at leakage-floor bands cannot impersonate narration) (`ASSEMBLE_AUDIO_NARRATION_MISSING`).
  Band ratios, not broadband level, so a loud music bed cannot mask
  missing narration.
- Final words: the last placed narration segment's final 0.3 s is
  checked the same way at its planned end position
  (`ASSEMBLE_AUDIO_FINAL_WORDS_MISSING`). Narration shortened by the
  mix (the historical `-shortest` failure shape) fails by name.
- Score audibility: in the longest narration-free window (at least
  0.3 s), the output's level must be consistent with the chosen
  score at its declared volume (within 18 dB, allowing for the
  score's own dynamics), and the window's trailing quarter must
  still carry energy, so a single SFX burst cannot impersonate a
  music bed (`ASSEMBLE_AUDIO_SCORE_NOT_AUDIBLE`).
- Mode `none`: no audio stream in the deliverable. Mode
  `inherited`: no audio stream, and the parent's bed is never
  duplicated because nothing of the package's audio is mixed at all.

All measurements land in the probe record under `audio_qc`.

## Failure vocabulary

Local exit codes are `assemble.py`'s (MG-022); the `mg_category`
column is the Section 16.9 translation the QC layer (MG-034)
consumes.

| Code | Local exit | Section 16.9 category | Raised when |
| --- | --- | --- | --- |
| `ASSEMBLE_AUDIO_MODE_VIOLATION` | 4 | `MG_MODE_MISMATCH` | Mode rules broken (audio in a `none` job, placed audio in an `inherited` job, unknown owner, registry mode contradiction, malformed music declaration) |
| `ASSEMBLE_AUDIO_CLIPPING` | 6 | `MG_QC_FAILED` | A source, or the encoded output, measures clipped |
| `ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET` | 6 | `MG_QC_FAILED` | The encoded output misses the resolved loudness target beyond tolerance |
| `ASSEMBLE_AUDIO_NARRATION_MISSING` | 6 | `MG_QC_FAILED` | A placed narration segment's bands are absent from the output |
| `ASSEMBLE_AUDIO_FINAL_WORDS_MISSING` | 6 | `MG_QC_FAILED` | The last narration segment's tail is absent at its planned end |
| `ASSEMBLE_AUDIO_SCORE_NOT_AUDIBLE` | 6 | `MG_QC_FAILED` | The chosen score is not audible in the planned narration-free sections |

## Scope notes

- Narration enters only from the job package's `narration.json`
  through the compiled timeline and sidecar (MG-025's layer); this
  policy consumes compiled placements and never manifest guesses.
- The TTS and SFX callers needed no changes: they produce sources;
  resolution, mode rules, and verification live here.
- `qc.sh` remains the legacy QC surface; the QC rebuild (MG-034)
  consumes the vocabulary above.
