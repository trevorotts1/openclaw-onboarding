"""character_continuity package: Character DNA records (directive 13.1). stdlib only."""
SCHEMA_VERSION = "1.0.0"
TOOL_VERSION = "1.0.0"

from .continuity import (  # noqa: E402
    WARDROBE_BREAK,
    LOCATION_BREAK,
    ACCESSORY_BREAK,
    check_cross_shot_continuity,
    check_accessory_lock,
)

__all__ = ["SCHEMA_VERSION", "TOOL_VERSION", "WARDROBE_BREAK",
           "LOCATION_BREAK", "ACCESSORY_BREAK", "check_cross_shot_continuity",
           "check_accessory_lock"]
