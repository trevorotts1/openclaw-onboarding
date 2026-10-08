"""qc_voice_match package: D17 voice-match QC (pitch band + on-screen
speaker + same-gender distinctness). Stdlib only, no spend."""
from .qc_voice_match import (  # noqa: F401
    CHECK,
    CHECK_ID,
    EXIT,
    PITCH_RANGES_HZ,
    SAME_GENDER_MIN_SEPARATION_HZ,
    SCHEMA_VERSION,
    AssemblyBlocked,
    VoiceMatchError,
    check_distinct_same_gender,
    check_line,
    envelope,
    evaluate,
    load_wav_samples,
    measure_pitch_hz,
    pitch_in_range,
    refuse_before_assembly,
    speaker_onscreen_ok,
    to_qc_record,
)

from . import line_voice_fit  # noqa: F401  (H10)

__all__ = [
    "CHECK",
    "CHECK_ID",
    "EXIT",
    "PITCH_RANGES_HZ",
    "SAME_GENDER_MIN_SEPARATION_HZ",
    "SCHEMA_VERSION",
    "AssemblyBlocked",
    "VoiceMatchError",
    "check_distinct_same_gender",
    "check_line",
    "envelope",
    "evaluate",
    "load_wav_samples",
    "measure_pitch_hz",
    "pitch_in_range",
    "refuse_before_assembly",
    "speaker_onscreen_ok",
    "to_qc_record",
]
