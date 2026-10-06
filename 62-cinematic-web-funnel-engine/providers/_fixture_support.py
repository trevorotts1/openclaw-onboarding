"""_fixture_support.py -- TEST SUPPORT ONLY. Never imported by production code.

Skill 74 reads the KIE catalog and the per-model schema before it submits, so a
fully offline fake transport has to answer those GETs too. ``kie_discovery_response``
answers the three read-only discovery routes (catalog, schema, credit balance)
with a permissive, deterministic body; the caller's own fixture still answers
createTask, recordInfo and upload.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from .kie import HttpResponse

_JOB = "/api/v1/jobs/createTask"


def kie_discovery_response(url: str) -> Optional[HttpResponse]:
    path = urlparse(url).path
    if path == "/api/v1/models":
        return HttpResponse(status_code=200, json_body={"code": 200, "msg": "success", "data": {"total": 0, "models": []}})
    if path.startswith("/api/v1/models/") and path.endswith("/schema"):
        schema = {
            "type": "object",
            "required": ["model", "input"],
            "properties": {
                "model": {"type": "string"},
                "callBackUrl": {"type": "string"},
                "input": {"type": "object", "properties": {"prompt": {"type": "string"}}},
            },
        }
        openapi = {
            "openapi": "3.1.0",
            "paths": {_JOB: {"post": {"requestBody": {"content": {"application/json": {"schema": schema}}}}}},
        }
        return HttpResponse(status_code=200, json_body={"code": 200, "msg": "success", "data": {"openapi": openapi}})
    if path == "/api/v1/chat/credit":
        return HttpResponse(status_code=200, json_body={"code": 200, "msg": "success", "data": 100000})
    return None
