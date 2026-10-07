"""style_bible_integration package: Style Bible consumption gate (13.3).

Wires bible.assert_compiled as the intake gate for every visual prompt:
image prompts here, shot prompts in shot_planner, video prompts in
storyboard_director. Default style = animated Resilia-like record.
stdlib only. No schema changes.
"""
from __future__ import annotations

from .style_gate import (
    DEFAULT_STYLE,
    SCHEMA_VERSION,
    TOOL_VERSION,
    StyleGateError,
    assert_compiled,
    compile_visual,
    default_style,
    intake_image_prompt,
    require_compiled,
    validate_default_style,
)

__all__ = [
    "DEFAULT_STYLE",
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "StyleGateError",
    "assert_compiled",
    "compile_visual",
    "default_style",
    "intake_image_prompt",
    "require_compiled",
    "validate_default_style",
]
