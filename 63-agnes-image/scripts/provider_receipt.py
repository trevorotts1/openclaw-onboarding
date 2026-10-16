"""provider_receipt.py -- provider-neutral asset receipt (packet doc 02 s10).

Every generated asset records requested/actual provider and model, mode,
provider receipt identifiers IF actually returned, result hash/dimensions,
prompt hash, and the prompt policy used.

Agnes image results are synchronous and the API returns no task ID:
task_id stays null. Attaching a KIE task ID to an Agnes receipt is refused
outright - validators that assume every image has a KIE task ID are the
bug this module exists to fix (acceptance A23). KIE receipts, conversely,
require the task ID the KIE API actually returned.
"""
from __future__ import annotations

import hashlib
import unicodedata


class ReceiptError(ValueError):
    pass


def _count(prompt: str) -> int:
    return len(unicodedata.normalize("NFC", prompt).strip())


def build_agnes_receipt(*, model_id: str, prompt: str, output_bytes: bytes,
                        dimensions: str, output_path: str,
                        request_id: str | None = None,
                        prompt_policy_id: str = "signature_launch_completeness") -> dict:
    return {
        "provider": "agnes",
        "model_requested": model_id,
        "model_actual": model_id,
        "mode": "sync",
        "task_id": None,
        "request_id": request_id,
        "prompt_hash": hashlib.sha256(
            unicodedata.normalize("NFC", prompt).strip().encode("utf-8")
        ).hexdigest(),
        "prompt_chars": _count(prompt),
        "prompt_policy_id": prompt_policy_id,
        "result_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "result_bytes": len(output_bytes),
        "dimensions": dimensions,
        "output_path": output_path,
    }


def validate_receipt(receipt: dict) -> None:
    if receipt.get("provider") == "agnes":
        if receipt.get("task_id") is not None:
            raise ReceiptError("Agnes synchronous results have no task ID; do not attach one")
        for key in receipt:
            if "kie" in key.lower() and receipt[key] is not None:
                raise ReceiptError(f"Agnes receipt must not carry a KIE identifier field '{key}'")
    if receipt.get("provider") == "kie" and not receipt.get("task_id"):
        raise ReceiptError("KIE receipts require the task ID the KIE API actually returned")
