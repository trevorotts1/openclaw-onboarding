"""song_contract package: each music style's own definition enforced on the
sheet and the returned song (FU-RNBFLOW-SONG)."""
from .song_contract import (  # noqa: F401
    RAP_AUDIO_UNMEASURED, check_returned_song, check_sheet, parse_sections,
    required_sung_sections, sung_target,
)
