"""research_engine package: offer research + sub-avatar brief stage runner
(directive 21, 17.9, 24.2/24.4; W2-01 acceptance). stdlib only."""
SCHEMA_VERSION = "blackceo.research/v1"
TOOL_VERSION = "1.0.0"
OUTCOMES = ("ok", "waiting", "parked", "rejected", "error")
EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}
