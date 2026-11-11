#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fake_command_center.py - a loopback Command Center stand-in for TESTS (stdlib only).

It serves approval rows in the shape the real Command Center GET returns
(GET /api/launch-approvals/<id>, the wire shape approval_record.normalize_record maps), on 127.0.0.1,
so the REAL shared verifier (shared-utils/signature_launch_contract/approval_record.py,
verify(..., test_only=False)) runs end to end, including its refusals. Nothing in the product reads
this module: it adds no bypass flag and no environment override to any tool. A tool is pointed at it
the way it is pointed at the real service, with MISSION_CONTROL_URL, MC_API_TOKEN and COMPANY_SLUG.

    with FakeCommandCenter() as cc:
        approval_id = cc.mint("stub_render", plan_hash_hex, scope=["stub_render"])
        subprocess.run([...], env={**os.environ, **cc.env()})
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

TENANT = "fixture-tenant"


class FakeCommandCenter:
    def __init__(self) -> None:
        self.rows: Dict[str, dict] = {}
        self.requests: List[str] = []
        self._server: Optional[ThreadingHTTPServer] = None

    def start(self) -> "FakeCommandCenter":
        rows, requests = self.rows, self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (http.server API)
                approval_id = self.path.rsplit("/", 1)[-1]
                requests.append(approval_id)
                row = rows.get(approval_id)
                body = json.dumps({"approval": row} if row else {"error": "not found"}).encode()
                self.send_response(200 if row else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # silence the test output
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> "FakeCommandCenter":
        return self.start()

    def __exit__(self, *exc) -> bool:
        self.stop()
        return False

    def env(self) -> Dict[str, str]:
        """The three variables a tool needs to reach this service as it would the real one."""
        return {"MISSION_CONTROL_URL": f"http://127.0.0.1:{self._server.server_port}",
                "MC_API_TOKEN": "fixture-token", "COMPANY_SLUG": TENANT}

    def mint(self, kind: str, plan_hash: str, scope: Optional[List[str]] = None, *,
             revoked: bool = False, expires_in: int = 3600, tenant: str = TENANT) -> str:
        approval_id = "appr_" + uuid.uuid4().hex[:16]
        self.rows[approval_id] = {
            "approval_id": approval_id, "tenant_id": tenant, "client_identity_ref": "fixture-owner",
            "kind": kind, "plan_hash": "sha256:" + plan_hash, "scope": ", ".join(scope or [kind]),
            "cap_minor": None, "currency": None, "revoked": revoked,
            "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat(),
            "source_message_ref": "fixture:client-reply-1"}
        return approval_id
