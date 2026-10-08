"""final_assembler package: timeline.json -> frame-exact ffmpeg render."""
from .assembler import (
    EXIT,
    NICE_LEVEL,
    SCHEMA_VERSION,
    TIMELINE_SCHEMA,
    TOOL_NAME,
    TOOL_VERSION,
    assemble,
    build_argv,
    load_timeline,
    plan_timeline,
    size_ffmpeg,
)
from .lipsync_coverage import (
    CHECK,
    COVERAGE_SHORT as LIPSYNC_COVERAGE_SHORT,
    LINES_TOO_FEW as LIPSYNC_LINES_TOO_FEW,
    TOOL_VERSION as LIPSYNC_TOOL_VERSION,
    check_lipsync_coverage,
    to_qc_record,
)

__all__ = [
    "EXIT",
    "NICE_LEVEL",
    "SCHEMA_VERSION",
    "TIMELINE_SCHEMA",
    "TOOL_NAME",
    "TOOL_VERSION",
    "assemble",
    "build_argv",
    "check_lipsync_coverage",
    "load_timeline",
    "LIPSYNC_COVERAGE_SHORT",
    "LIPSYNC_LINES_TOO_FEW",
    "LIPSYNC_TOOL_VERSION",
    "plan_timeline",
    "size_ffmpeg",
    "to_qc_record",
]
