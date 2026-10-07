"""Scripted offline harness for the V2-13 lip-sync model-quality canary.

No network client is imported anywhere in this module: every response is popped
from fixtures/. Live dispatch is refused fail-closed until an operator approves
a separate budget for the live canary.
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

#: Closed roster, in dispatch order: primary first, backup second.
ROSTER = ("kling/ai-avatar-standard", "infinitalk/from-audio")

SHOTS_MIN = 1
SHOTS_MAX = 2

#: Scripted outcomes the harness understands.
PRIMARY_OK = "primary_ok"
FALLBACK = "fallback"
BOTH_FAIL = "both_fail"

PATHS = (PRIMARY_OK, FALLBACK, BOTH_FAIL)


class SpecError(ValueError):
    """The canary spec or an attempt list violates the contract."""


class LiveCallRefused(RuntimeError):
    """A live (paid) call was attempted in a window that spends nothing."""


def load_spec(path: pathlib.Path | None = None) -> dict:
    target = path or (HERE / "canary_spec.json")
    with open(target, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_fixture(name: str) -> dict:
    with open(FIXTURES / name, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_spec(spec: dict) -> dict:
    """Fail-closed contract check. Returns the spec when it is usable."""
    if spec.get("mode") != "mock":
        raise SpecError(f"mode must be 'mock' in this window, got {spec.get('mode')!r}")

    spend = spec.get("spend") or {}
    if spend.get("allowed") is not False:
        raise SpecError("spend.allowed must be false: this window spends nothing")
    if float(spend.get("ceiling_usd", 1)) != 0.0:
        raise SpecError("spend.ceiling_usd must be 0.0 in this window")
    if int(spend.get("paid_calls", 1)) != 0:
        raise SpecError("spend.paid_calls must be 0 in this window")

    providers = spec.get("providers") or []
    models = tuple(p.get("model") for p in providers)
    if models != ROSTER:
        raise SpecError(
            "provider roster must be exactly the ordered two-entry roster, "
            f"got {models!r}"
        )
    if tuple(p.get("rank") for p in providers) != (1, 2):
        raise SpecError("provider ranks must be 1 then 2")
    if tuple(p.get("role") for p in providers) != ("primary", "backup"):
        raise SpecError("provider roles must be primary then backup")

    shots = spec.get("shots") or {}
    count = shots.get("count")
    low = shots.get("min")
    high = shots.get("max")
    if low != SHOTS_MIN or high != SHOTS_MAX:
        raise SpecError(f"shot range must be {SHOTS_MIN}..{SHOTS_MAX}, got {low!r}..{high!r}")
    if not isinstance(count, int) or not (low <= count <= high):
        raise SpecError(f"shots.count must be within {low}..{high}, got {count!r}")
    if shots.get("same_keyframe") is not True:
        raise SpecError("shots.same_keyframe must be true: one keyframe per canary")

    if not spec.get("attempt_order_rule"):
        raise SpecError("attempt_order_rule is required")
    return spec


def verify_attempt_order(models: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """An attempt list must be a strict prefix of ROSTER (primary never skipped)."""
    seen = tuple(models)
    if not seen:
        raise SpecError("attempt list is empty")
    roster_prefix = ROSTER[: len(seen)]
    if len(seen) > len(ROSTER) or seen != roster_prefix:
        raise SpecError(
            f"attempt order {seen!r} is not a prefix of the roster {ROSTER!r}"
        )
    return seen


class Ledger:
    """Counts dispatches. A nonzero price is refused outright."""

    def __init__(self) -> None:
        self.mock_dispatches: list[dict] = []
        self.paid_calls = 0
        self.spend_usd = 0.0

    def record_mock(self, model: str, shot_id: str, price_usd: float = 0.0) -> None:
        if price_usd:
            raise LiveCallRefused(
                f"refusing to record a price of {price_usd}: this window spends nothing"
            )
        if model not in ROSTER:
            raise SpecError(f"provider outside the closed roster: {model!r}")
        self.mock_dispatches.append({"model": model, "shot_id": shot_id, "paid": False})
        self.paid_calls += 0
        self.spend_usd += 0.0


class ScriptedKIE:
    """Answers dispatches from a scripted fixture list. Offline by construction."""

    def __init__(self, script: dict[str, list[dict]]) -> None:
        self._script = {model: list(responses) for model, responses in script.items()}
        self.calls: list[dict] = []

    def dispatch(self, model: str, payload: dict) -> dict:
        if model not in ROSTER:
            raise SpecError(f"provider outside the closed roster: {model!r}")
        if model not in self._script:
            raise SpecError(f"no scripted response for {model!r}")
        if not self._script[model]:
            raise SpecError(f"script exhausted for {model!r}")
        response = self._script[model].pop(0)
        self.calls.append(
            {
                "model": model,
                "shot_id": payload.get("shot_id"),
                "status": response.get("status"),
            }
        )
        return response


def _succeeded(response: dict) -> bool:
    return response.get("status") == "succeeded" and bool(response.get("saved_file"))


def run_path(spec: dict, shot: dict, path: str) -> dict:
    """Run one scripted canary path and return its recorded result.

    Paths: PRIMARY_OK (primary succeeds), FALLBACK (primary fails, backup runs),
    BOTH_FAIL (neither produces a saved file).
    """
    validate_spec(spec)
    if path not in PATHS:
        raise SpecError(f"unknown path {path!r}; expected one of {PATHS!r}")
    if shot.get("style") != spec["shots"]["style"]:
        raise SpecError(
            f"shot style {shot.get('style')!r} does not match the canary style "
            f"{spec['shots']['style']!r}"
        )

    scripts = {
        PRIMARY_OK: {ROSTER[0]: [load_fixture("kling_primary_success.json")]},
        FALLBACK: {
            ROSTER[0]: [load_fixture("kling_primary_failure.json")],
            ROSTER[1]: [load_fixture("infinitalk_backup_success.json")],
        },
        BOTH_FAIL: {
            ROSTER[0]: [load_fixture("kling_primary_failure.json")],
            ROSTER[1]: [load_fixture("infinitalk_backup_failure.json")],
        },
    }
    client = ScriptedKIE(scripts[path])
    ledger = Ledger()

    payload = {
        "shot_id": shot.get("shot_id"),
        "keyframe": shot.get("keyframe"),
        "isolated_line": shot.get("isolated_line"),
        "style": shot.get("style"),
        "character": shot.get("character"),
    }

    attempts: list[str] = []
    attempts.append(ROSTER[0])
    verify_attempt_order(attempts)
    ledger.record_mock(attempts[-1], payload["shot_id"])
    first = client.dispatch(attempts[-1], payload)
    winner = attempts[-1] if _succeeded(first) else None
    outcome = first

    if winner is None:
        attempts.append(ROSTER[1])
        verify_attempt_order(attempts)
        ledger.record_mock(attempts[-1], payload["shot_id"])
        second = client.dispatch(attempts[-1], payload)
        winner = attempts[-1] if _succeeded(second) else None
        outcome = second

    return {
        "path": path,
        "shot_id": shot.get("shot_id"),
        "attempts": attempts,
        "dispatch_order": [c["model"] for c in ledger.mock_dispatches],
        "models_dispatched": [c["model"] for c in ledger.mock_dispatches],
        "winner": winner,
        "final_status": outcome.get("status"),
        "saved_file": outcome.get("saved_file"),
        "paid_calls": ledger.paid_calls,
        "spend_usd": ledger.spend_usd,
        "mode": spec["mode"],
        "mock": True,
    }


def run_live(*_args, **_kwargs):  # pragma: no cover - exercised by test_zero_spend
    """Live canary entrypoint. Always refused in this window."""
    raise LiveCallRefused(
        "live lip-sync canary refused: this window spends nothing; "
        "an operator budget approval is required before any paid call"
    )
