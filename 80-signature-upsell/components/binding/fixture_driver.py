"""TEST ONLY - deterministic fixture NativeDriver for S80-06 binding tests.

This driver scripts native outcomes so the binding core can be proven
at L1 without any real native system. It performs no network calls, no
charges, and proves nothing about a real location (interface section 8
proof boundary). It is NEVER imported by production paths: the
production driver is S06's installed native binding, pending open
questions S06-Q1..Q6.

Scenarios:
  paid_with_readback       invoke -> paid;    read_back -> paid
  paid_without_readback    invoke -> paid;    read_back -> pending_confirmation
  failed                   invoke -> failed (card_declined)
  pending_then_paid        invoke -> pending_confirmation; read_back -> paid
  requires_customer_action invoke -> requires_customer_action (authentication_required)
  expired_cancelled        invoke -> cancelled (session_expired)
  invoke_raises_unknown    invoke raises;     read_back -> paid (reconcile resolves)
"""

from __future__ import annotations

from typing import Callable, List, Optional

from extra_offer_binding import BindingContext, NativeResult

SCENARIOS = (
    "paid_with_readback",
    "paid_without_readback",
    "failed",
    "pending_then_paid",
    "requires_customer_action",
    "expired_cancelled",
    "invoke_raises_unknown",
)


class FixtureDriver:
    """A scripted NativeDriver. Deterministic: same scenario, same results."""

    def __init__(self, scenario: str, *,
                 on_invoke: Optional[Callable[[], None]] = None) -> None:
        if scenario not in SCENARIOS:
            raise ValueError("Unknown fixture scenario %r." % (scenario,))
        self.scenario = scenario
        self.on_invoke = on_invoke
        self.invoke_calls: List[str] = []  # idempotency keys, in order
        self.read_back_calls: List[Optional[str]] = []  # txn refs, in order

    @property
    def total_calls(self) -> int:
        return len(self.invoke_calls) + len(self.read_back_calls)

    def _txn(self) -> str:
        return "TEST-TXN-%s" % self.scenario

    def invoke(self, context: BindingContext, idempotency_key: str) -> NativeResult:
        self.invoke_calls.append(idempotency_key)
        if self.on_invoke is not None:
            self.on_invoke()
        if self.scenario == "invoke_raises_unknown":
            raise RuntimeError("TEST ONLY: simulated transport loss; outcome unknown")
        if self.scenario in ("paid_with_readback", "paid_without_readback"):
            return NativeResult("paid", self._txn(), None)
        if self.scenario == "failed":
            return NativeResult("failed", self._txn(), "card_declined")
        if self.scenario == "pending_then_paid":
            return NativeResult("pending_confirmation", self._txn(), None)
        if self.scenario == "requires_customer_action":
            return NativeResult(
                "requires_customer_action", self._txn(), "authentication_required"
            )
        # expired_cancelled
        return NativeResult("cancelled", None, "session_expired")

    def read_back(self, context: BindingContext,
                  native_txn_ref: Optional[str]) -> NativeResult:
        self.read_back_calls.append(native_txn_ref)
        if self.scenario in ("paid_with_readback", "pending_then_paid",
                             "invoke_raises_unknown"):
            return NativeResult("paid", self._txn(), None)
        if self.scenario == "paid_without_readback":
            return NativeResult("pending_confirmation", self._txn(), None)
        if self.scenario == "failed":
            return NativeResult("failed", self._txn(), "card_declined")
        if self.scenario == "requires_customer_action":
            return NativeResult(
                "requires_customer_action", self._txn(), "authentication_required"
            )
        return NativeResult("cancelled", None, "session_expired")
