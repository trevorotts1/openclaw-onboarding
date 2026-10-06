"""intake_preflight package: shared CLI + intake + preflight (directive 24.2-24.4). stdlib only."""
SCHEMA_VERSION = "blackceo.intake-preflight/envelope/v1"
TOOL_VERSION = "0.1.0"
OUTCOMES = ("ok", "waiting", "parked", "rejected", "error")
EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
