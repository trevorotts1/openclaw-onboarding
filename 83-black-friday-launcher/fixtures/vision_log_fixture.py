"""Test helper: the SOP-GIP-02 vision log (qc/vision_qc_log.json) a reviewer writes beside the report.

One record per reviewed image: the sha256 of the bytes the multimodal pass looked at and the non-null
vision_api_response it returned. The launcher demands this file in addition to the Review Receipt v2
(issue 21, AF-G-VISION); a fixture that builds a passing report writes it with this helper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def write_vision_log(folder: Path, shas: Iterable[str], model: str = "review-model") -> Path:
    path = Path(folder) / "qc" / "vision_qc_log.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"assets": [
        {"artifact_sha256": sha, "vision_api_response": {"model": model, "observation": "read the image at delivery size"}}
        for sha in shas]}), encoding="utf-8")
    return path
