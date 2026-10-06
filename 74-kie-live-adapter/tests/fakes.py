"""Shared test doubles: fake transport routes, fake clock, fixture loader. No network."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import kie_live_adapter as K  # noqa: E402

KEY = "fake-key-SENTINEL-0123456789"


def fx(name):
    with open(os.path.join(HERE, "fixtures", name)) as f:
        return json.load(f)


class Clock:
    def __init__(self):
        self.t = 1_000_000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


class FakeTransport:
    """routes: list of [method, url-substring, [(status, obj_or_bytes), ...]]; last response repeats."""

    def __init__(self, routes=()):
        self.routes = [list(r) for r in routes]
        self.calls = []

    def add(self, method, sub, responses):
        self.routes.insert(0, [method, sub, list(responses)])

    def request(self, method, url, headers=None, body=None, timeout=60, guard=None):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "body": body, "guard": guard})
        for r in self.routes:
            if r[0] == method and r[1] in url:
                st, obj = r[2].pop(0) if len(r[2]) > 1 else r[2][0]
                if isinstance(obj, (bytes, bytearray)):
                    return st, bytes(obj)
                return st, json.dumps(obj).encode()
        return 404, b'{"code":404,"msg":"no route"}'

    def n(self, method, sub):
        return sum(1 for c in self.calls if c["method"] == method and sub in c["url"])


def make(tmp, routes=(), mode="active", extra_env=None, clock=None):
    clock = clock or Clock()
    env = {"KIE_API_KEY": KEY, "KIE_LIVE_ADAPTER_MODE": mode, "HOME": tmp,
           "KIE_LIVE_CACHE_DIR": os.path.join(tmp, "cache"), "KIE_LIVE_POLL_INITIAL": "3"}
    env.update(extra_env or {})
    tr = FakeTransport(routes)
    return K.Adapter(env=env, transport=tr, sleep=clock.sleep, now=clock.now), tr, clock


def std_routes():
    return [
        ["GET", "/api/v1/models/gpt-image-2-5-sunburst-text-to-image/schema", [(200, fx("schema_image.json"))]],
        ["GET", "/api/v1/models", [(200, fx("catalog.json"))]],
        ["GET", "/api/v1/chat/credit", [(200, {"code": 200, "msg": "success", "data": 2450})]],
        ["POST", "/api/v1/jobs/createTask", [(200, {"code": 200, "msg": "success", "data": {"taskId": "T1", "recordId": "R1"}})]],
    ]


MODEL = "gpt-image-2-5-sunburst-text-to-image"


def slurp(path, mode="r"):
    with open(path, mode) as f:
        return f.read()
