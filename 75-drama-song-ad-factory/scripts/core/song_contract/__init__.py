"""song_contract package: each music style's own definition enforced on the
sheet and the returned song (FU-RNBFLOW-SONG), plus the WWFIX D1 story gates
and the rap sheet floor."""
from .song_contract import (  # noqa: F401
    RAP_AUDIO_UNMEASURED, check_returned_song, check_returned_story,
    check_sheet, parse_sections, rap_floor_for, required_sung_sections,
    sung_target,
)
