#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_kie_legacy.py -- QUARANTINED fallback client for providers/kie.py.

Used ONLY when Skill 74 (74-kie-live-adapter) is not installed on the box.
Every normal run goes through Skill 74 (submit, wait, save, upload, price,
validate, prompt-budget); providers/kie.py logs ``path=legacy`` loudly when it
has to fall back here. Do not extend this file: new behaviour belongs in
Skill 74. It is the pre-consolidation createTask/recordInfo/upload plumbing
moved out of providers/kie.py (result parsing trimmed to the documented resultJson.resultUrls route), and it goes away once
Skill 74 is a hard prerequisite of Skill 62.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .base import ProviderTaskError

_API = "https://api.kie.ai"
CREATE_TASK_URL = f"{_API}/api/v1/jobs/createTask"
RECORD_INFO_URL = f"{_API}/api/v1/jobs/recordInfo"
UPLOAD_URL = "https://kieai.redpandaai.co/api/file-base64-upload"
_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def decode_result_json(raw: Any) -> Dict[str, Any]:
    """``resultJson`` is a JSON-ENCODED STRING on recordInfo: str -> json.loads
    ({} on failure); dict -> as-is; anything else -> {}."""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return raw if isinstance(raw, dict) else {}


def upload_asset(transport: Any, api_key: str, path: Path, purpose: str) -> str:
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    body = {
        "base64Data": f"data:{mime};base64,{b64}",
        "uploadPath": f"images/cinematic-web-funnel-engine/{purpose}",
        "fileName": path.name,
    }
    resp = transport.post_json(UPLOAD_URL, headers={"Authorization": f"Bearer {api_key}"}, body=body, timeout=60)
    data = resp.json_body.get("data") or {}
    url = data.get("downloadUrl") or resp.json_body.get("downloadUrl") or data.get("url")
    if not url or not str(url).startswith("http"):
        raise ProviderTaskError(f"kie provider: upload_asset returned no usable URL: {resp.json_body}")
    return str(url)


def submit(transport: Any, api_key: str, body: Dict[str, Any], model_id: str) -> str:
    resp = transport.post_json(
        CREATE_TASK_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise ProviderTaskError(f"kie provider: createTask HTTP {resp.status_code} for {model_id}: {resp.json_body}")
    task_id = (resp.json_body.get("data") or {}).get("taskId") or resp.json_body.get("taskId")
    if not task_id:
        raise ProviderTaskError(f"kie provider: createTask for {model_id} returned no taskId: {resp.json_body}")
    return str(task_id)


def task_state(transport: Any, api_key: str, task_id: str):
    """-> (status, detail) with status in success|failed|processing|queued."""
    resp = transport.get_json(
        RECORD_INFO_URL, headers={"Authorization": f"Bearer {api_key}"}, params={"taskId": task_id}, timeout=15
    )
    data = resp.json_body.get("data") or {}
    state = data.get("state", "")
    status = {"success": "success", "fail": "failed", "failed": "failed", "error": "failed"}.get(
        state, "processing" if state else "queued"
    )
    detail = (data.get("failMsg") or resp.json_body.get("msg")) if status == "failed" else None
    return status, detail


def poll_result_url(
    transport: Any, api_key: str, task_id: str, *, interval: float = 5, timeout: float = 600
) -> str:
    elapsed = 0.0
    while elapsed < timeout:
        resp = transport.get_json(
            RECORD_INFO_URL, headers={"Authorization": f"Bearer {api_key}"}, params={"taskId": task_id}, timeout=15
        )
        data = resp.json_body.get("data") or {}
        state = data.get("state", "")
        if state == "success":
            result_json = decode_result_json(data.get("resultJson"))
            urls = result_json.get("resultUrls")
            if isinstance(urls, list) and urls:
                return str(urls[0])
            raise ProviderTaskError(f"kie provider: task {task_id} succeeded but no result URL found: {result_json}")
        if state in ("fail", "failed", "error"):
            fail_msg = data.get("failMsg") or resp.json_body.get("msg") or "unknown"
            raise ProviderTaskError(f"kie provider: task {task_id} failed: {fail_msg}")
        time.sleep(interval)
        elapsed += interval
    raise ProviderTaskError(f"kie provider: task {task_id} timed out after {timeout}s")


def download(transport: Any, url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(transport.download(url, timeout=180))
