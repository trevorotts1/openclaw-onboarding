"""sung_hook package: the I8 sung hook and its length-based repeat formula."""
from .sung_hook import (  # noqa: F401
    HOOK_MAX, HOOK_MIN, SECONDS_PER_HOOK, build_lyric_sheet, check_hook_text,
    check_sheet_count, hook_count, hook_times, judge, measure, _words as words,
)
