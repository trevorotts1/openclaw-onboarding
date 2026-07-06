#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE :: FLOW TRIGGER + 409 READ-CHECK-REAPPLY HELPER
# webhook-design.md Section 6 and 7
# -----------------------------------------------------------------------------
# Drives the OpenClaw Webhooks plugin's TaskFlow actions over the loopback
# gateway. This is the PLATFORM'S OWN webhooks action API, not a Model Context
# Protocol server and not a language model: a plain authenticated HTTP POST to
# 127.0.0.1:18789/plugins/webhooks/<routeId> carrying {"action": ...}. The route
# secret is read from the environment and sent as a Bearer token; it is never
# printed, echoed, or logged (verification is SET / behavior, never the value).
#
# LIVE-VERIFIED against the INSTALLED gateway (OpenClaw 2026.6.11,
# extensions/webhooks/index.js). The action schema differs from the design's
# illustrative sketch (documented schema drift), so this client matches the
# installed contract exactly:
#   create_flow : goal(req), status?, notifyPolicy?, currentStep?, stateJson?,
#                 waitJson?, controllerId?      -> platform assigns the flowId
#                 (no client-supplied flow id; dedup is the intake ledger's job,
#                 and the job_key rides in stateJson so get_flow can map it back)
#   run_task    : flowId(req), runtime(subagent|acp), task(req), childSessionKey?,
#                 sourceId?, parentTaskId?, agentId?, runId?, label?, notifyPolicy?
#   get_flow    : flowId(req)                 -> flow carries revision, status,
#                                                stateJson, goal, timestamps
#   resume_flow : flowId, expectedRevision(int>=0), status?(queued|running),
#                 currentStep?, stateJson?
#   finish_flow : flowId, expectedRevision, stateJson?
#   fail_flow   : flowId, expectedRevision, stateJson?, blockedTaskId?, blockedSummary?
#   set_waiting : flowId, expectedRevision, currentStep?, stateJson?, waitJson?
# Error mapping: 404 not_found, 409 not_managed, 409 revision_conflict.
#
# 409 CONTRACT (Section 6): every flow mutation carries expectedRevision. On a
# revision_conflict, re-read the flow, check whether the intended transition
# already happened (someone else did it) and stop success if so, otherwise
# re-apply against the fresh revision. Max 3 attempts with short jittered backoff;
# on exhaustion, park the job and alert the operator. Never blind-retry a mutation
# without re-reading state; that is how double transitions happen.
#
# EXIT: 0 OK / 2 flow error / 3 usage.
# USAGE (self-drive; the podcast agent's own turn owns tool-bearing steps):
#   python3 flow_client.py --self-test
# =============================================================================
"""OpenClaw Webhooks plugin TaskFlow client with a 409 read-check-reapply guard."""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

EXIT_OK = 0
EXIT_FLOW_ERROR = 2
EXIT_USAGE = 3

DEFAULT_GATEWAY = "http://127.0.0.1:18789"
_GATEWAY_ENV = "PODCAST_GATEWAY_URL"
_ROUTE_ENV = "PODCAST_INTAKE_ROUTE_ID"
_SECRET_ENV = "PODCAST_INTAKE_HOOK_SECRET"

CONFLICT_MAX_ATTEMPTS = 3


class FlowError(Exception):
    """Transport or configuration failure. Messages carry labels only, no secrets."""


class FlowClient:
    def __init__(self, base_url=None, route_id=None, secret_env=_SECRET_ENV,
                 transport=None, sleep=time.sleep, timeout=15):
        self.base_url = (base_url or os.environ.get(_GATEWAY_ENV) or DEFAULT_GATEWAY).rstrip("/")
        self.route_id = route_id or os.environ.get(_ROUTE_ENV)
        self.secret_env = secret_env
        self.timeout = timeout
        self._transport = transport or self._http_transport
        self._sleep = sleep

    # -- transport -----------------------------------------------------------
    def _http_transport(self, action):
        if not self.route_id:
            raise FlowError("route id not set (env %s)" % _ROUTE_ENV)
        secret = os.environ.get(self.secret_env)
        if not secret:
            raise FlowError("route secret not set (env %s)" % self.secret_env)
        url = "%s/plugins/webhooks/%s" % (self.base_url, self.route_id)
        data = json.dumps(action).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer %s" % secret)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8") or "{}"
                return resp.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            try:
                parsed = json.loads(body) if body else {}
            except ValueError:
                parsed = {"error": body}
            return exc.code, parsed
        except urllib.error.URLError as exc:
            raise FlowError("gateway unreachable at %s: %s" % (self.base_url, exc.reason))

    def call(self, action_name, **params):
        action = {"action": action_name}
        action.update({k: v for k, v in params.items() if v is not None})
        return self._transport(action)

    @staticmethod
    def _extract_flow(resp):
        result = (resp or {}).get("result") or {}
        if isinstance(result, dict) and "revision" in result:
            return result
        flow = result.get("flow") if isinstance(result, dict) else None
        return flow or {}

    @staticmethod
    def _backoff(attempt):
        return min(0.2 * attempt, 1.0) + random.uniform(0, 0.1)

    # -- thin action wrappers ------------------------------------------------
    def create_flow(self, goal, controller_id=None, status="queued",
                    notify_policy="silent", state_json=None, current_step=None):
        return self.call("create_flow", goal=goal, controllerId=controller_id,
                         status=status, notifyPolicy=notify_policy,
                         stateJson=state_json, currentStep=current_step)

    def run_task(self, flow_id, task, runtime="subagent", child_session_key=None,
                 label=None, notify_policy=None):
        return self.call("run_task", flowId=flow_id, runtime=runtime, task=task,
                         childSessionKey=child_session_key, label=label,
                         notifyPolicy=notify_policy)

    def get_flow(self, flow_id):
        return self.call("get_flow", flowId=flow_id)

    def find_latest_flow(self):
        return self.call("find_latest_flow")

    # -- 409 read-check-reapply guard ---------------------------------------
    def mutate_with_conflict_guard(self, action_name, flow_id, build_params,
                                   already_applied, max_attempts=CONFLICT_MAX_ATTEMPTS):
        """Drive one flow mutation under the Section 6 contract. build_params(flow)
        returns the action params (including expectedRevision from the fresh flow);
        already_applied(flow) returns True when the intended transition is already
        reflected (another worker did it)."""
        last = None
        for attempt in range(1, max_attempts + 1):
            gstatus, gresp = self.get_flow(flow_id)
            if gstatus == 404 or (gresp or {}).get("code") == "not_found":
                return {"ok": False, "status": 404, "code": "not_found",
                        "error": "flow %s not found" % flow_id}
            flow = self._extract_flow(gresp)
            if already_applied(flow):
                return {"ok": True, "applied_by": "other", "flow": flow}
            params = build_params(flow)
            status, resp = self.call(action_name, flowId=flow_id, **params)
            if status == 200 and (resp or {}).get("ok"):
                return {"ok": True, "applied_by": "self", "result": (resp or {}).get("result")}
            last = {"status": status, "code": (resp or {}).get("code"),
                    "error": (resp or {}).get("error")}
            if status == 409 and (resp or {}).get("code") == "revision_conflict":
                self._sleep(self._backoff(attempt))
                continue
            return {"ok": False, **last}
        result = {"ok": False, "status": 409, "code": "revision_conflict",
                  "error": "max attempts exhausted; park job + operator alert"}
        if last:
            result["last"] = last
        return result

    def _merge_state(self, flow, marker, extra_state):
        merged = dict((flow or {}).get("stateJson") or {})
        merged.update(marker or {})
        if extra_state:
            merged.update(extra_state)
        return merged

    def finish_idempotent(self, flow_id, marker, extra_state=None):
        """Finish a flow exactly once. marker is a stateJson signature that proves
        the transition already ran (used by the guard for the already-applied
        short-circuit), e.g. {'podcast_webhook_terminal': 'duplicate'}."""
        def already(flow):
            sj = (flow or {}).get("stateJson") or {}
            return bool(marker) and all(sj.get(k) == v for k, v in marker.items())

        def build(flow):
            return {"expectedRevision": flow.get("revision", 0),
                    "stateJson": self._merge_state(flow, marker, extra_state)}
        return self.mutate_with_conflict_guard("finish_flow", flow_id, build, already)

    def fail_idempotent(self, flow_id, marker, blocked_summary=None, extra_state=None):
        def already(flow):
            sj = (flow or {}).get("stateJson") or {}
            return bool(marker) and all(sj.get(k) == v for k, v in marker.items())

        def build(flow):
            params = {"expectedRevision": flow.get("revision", 0),
                      "stateJson": self._merge_state(flow, marker, extra_state)}
            if blocked_summary:
                params["blockedSummary"] = blocked_summary
            return params
        return self.mutate_with_conflict_guard("fail_flow", flow_id, build, already)

    def set_waiting_idempotent(self, flow_id, marker, current_step=None, extra_state=None):
        def already(flow):
            sj = (flow or {}).get("stateJson") or {}
            return bool(marker) and all(sj.get(k) == v for k, v in marker.items())

        def build(flow):
            params = {"expectedRevision": flow.get("revision", 0),
                      "stateJson": self._merge_state(flow, marker, extra_state)}
            if current_step:
                params["currentStep"] = current_step
            return params
        return self.mutate_with_conflict_guard("set_waiting", flow_id, build, already)


# =============================================================================
# SELF-TEST (in-memory FakeGateway; no live gateway is ever contacted)
# =============================================================================
class _FakeGateway:
    def __init__(self):
        self.flows = {}
        self.counter = 0
        self._concurrent = []  # one-shot mutations run just before a revision compare

    def schedule_concurrent(self, fn):
        self._concurrent.append(fn)

    def transport(self, action):
        a = action["action"]
        if a == "create_flow":
            self.counter += 1
            fid = "flow_%d" % self.counter
            self.flows[fid] = {"flowId": fid, "revision": 0,
                               "status": action.get("status", "queued"),
                               "goal": action["goal"], "stateJson": action.get("stateJson")}
            return 200, {"ok": True, "routeId": "r", "result": {"flow": dict(self.flows[fid])}}
        if a == "run_task":
            if action["flowId"] not in self.flows:
                return 404, {"ok": False, "code": "not_found", "result": {}}
            return 200, {"ok": True, "result": {"taskId": "task_1"}}
        if a == "get_flow":
            f = self.flows.get(action["flowId"])
            if not f:
                return 404, {"ok": False, "code": "not_found", "result": {}}
            return 200, {"ok": True, "result": {"flow": dict(f)}}
        if a in ("finish_flow", "resume_flow", "fail_flow", "set_waiting"):
            f = self.flows.get(action["flowId"])
            if not f:
                return 404, {"ok": False, "code": "not_found", "result": {}}
            if self._concurrent:
                self._concurrent.pop(0)(f)  # a concurrent worker moves the flow
            if action["expectedRevision"] != f["revision"]:
                return 409, {"ok": False, "code": "revision_conflict",
                             "error": "stale revision", "result": {}}
            f["revision"] += 1
            f["status"] = {"finish_flow": "done", "fail_flow": "failed",
                           "set_waiting": "waiting"}.get(a, action.get("status", "running"))
            if action.get("stateJson") is not None:
                f["stateJson"] = action["stateJson"]
            return 200, {"ok": True, "result": {"flow": dict(f)}}
        return 400, {"ok": False, "code": "bad_action", "result": {}}


def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "MISS", name))

    fake = _FakeGateway()
    client = FlowClient(route_id="podcast-intake-canary", transport=fake.transport,
                        sleep=lambda _s: None)

    # create_flow assigns a flow id and carries our job_key in stateJson
    job = "pd-CNT1-0123456789abcdef"
    st, resp = client.create_flow("Podcast intake %s" % job,
                                  controller_id="webhooks/podcast-intake-canary",
                                  state_json={"engine": "podcast", "job_key": job})
    flow = client._extract_flow(resp)
    fid = flow.get("flowId")
    check("create_flow ok", st == 200 and resp["ok"] and fid)
    check("job_key carried in stateJson", flow["stateJson"]["job_key"] == job)

    st2, resp2 = client.run_task(fid, "read the intake ledger and execute Step 1", runtime="subagent")
    check("run_task ok", st2 == 200 and resp2["ok"])

    # happy-path finish (no conflict)
    r = client.finish_idempotent(fid, marker={"podcast_webhook_terminal": "test"})
    check("finish happy path applied by self", r["ok"] and r["applied_by"] == "self")

    # conflict-then-reapply: a concurrent worker bumps the revision once
    st3, resp3 = client.create_flow("second", state_json={"job_key": "j2"})
    fid2 = client._extract_flow(resp3)["flowId"]

    def bump_only(f):
        f["revision"] += 1  # e.g. another worker set_waiting; status still not terminal

    fake.schedule_concurrent(bump_only)
    r2 = client.finish_idempotent(fid2, marker={"podcast_webhook_terminal": "duplicate"})
    check("conflict then re-apply succeeds", r2["ok"] and r2["applied_by"] == "self")

    # already-applied-by-other: a concurrent worker performs OUR finish first
    st4, resp4 = client.create_flow("third", state_json={"job_key": "j3"})
    fid3 = client._extract_flow(resp4)["flowId"]
    marker3 = {"podcast_webhook_terminal": "needs_input"}

    def other_finished(f):
        f["revision"] += 1
        f["status"] = "done"
        f["stateJson"] = dict(f.get("stateJson") or {}, **marker3)

    fake.schedule_concurrent(other_finished)
    r3 = client.finish_idempotent(fid3, marker=marker3)
    check("already-applied-by-other short-circuits", r3["ok"] and r3["applied_by"] == "other")

    # unknown flow -> not_found, no crash
    r4 = client.finish_idempotent("flow_does_not_exist", marker={"x": "y"})
    check("missing flow -> not_found", r4["ok"] is False and r4["code"] == "not_found")

    # exhaustion: a conflict injected on every attempt -> park + operator alert
    st5, resp5 = client.create_flow("fourth", state_json={"job_key": "j4"})
    fid4 = client._extract_flow(resp5)["flowId"]
    for _ in range(CONFLICT_MAX_ATTEMPTS + 2):
        fake.schedule_concurrent(bump_only)
    r5 = client.finish_idempotent(fid4, marker={"podcast_webhook_terminal": "x"})
    check("conflict every attempt -> exhausted park", r5["ok"] is False
          and r5["code"] == "revision_conflict" and "park job" in r5["error"])

    # secret discipline: http transport with the secret env unset raises a labeled
    # error that names the ENV VAR only (there is no value to leak)
    os.environ.pop(_SECRET_ENV, None)
    live = FlowClient(route_id="podcast-intake-canary")
    raised_label = ""
    try:
        live.call("list_flows")
    except FlowError as exc:
        raised_label = str(exc)
    check("unset secret raises labeled FlowError", _SECRET_ENV in raised_label)

    print("== flow_client self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Podcast Engine TaskFlow client.")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    ap.error("this module is a library; run --self-test to verify the 409 guard")


if __name__ == "__main__":
    sys.exit(main())
