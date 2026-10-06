"""KIE live createTask/recordInfo flow for Skill 25, against a fake HTTP transport.

No network, no key, no ffmpeg: requests.post/get are replaced by FakeKie and the
final download is stubbed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

try:
    import requests as _requests  # noqa: F401
except ModuleNotFoundError:
    stub = ModuleType("requests")

    class RequestException(Exception):
        pass

    stub.RequestException = RequestException
    sys.modules["requests"] = stub

SKILL_ROOT = Path(os.environ.get("SKILL25_ROOT", Path(__file__).resolve().parents[1]))
CREATE = "https://api.kie.ai/api/v1/jobs/createTask"
RECORD = "https://api.kie.ai/api/v1/jobs/recordInfo"
UPLOAD = "https://kieai.redpandaai.co/api/file-stream-upload"


def load_module():
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location(
        f"skill25_ai_providers_{abs(hash(SKILL_ROOT))}", SKILL_ROOT / "scripts" / "ai_providers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


class FakeKie:
    """Scripted transport. `create` and `upload` are single replies; `records` is a queue."""

    def __init__(self, create=None, records=(), upload=None):
        self.create = create or Resp({"code": 200, "msg": "success", "data": {"taskId": "t1"}})
        self.records = list(records)
        self.upload = upload or Resp({"code": 200, "success": True,
                                      "data": {"downloadUrl": "https://tempfile.example/in.png"}})
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("post", url, kw))
        if url == CREATE:
            return self.create
        if url == UPLOAD:
            return self.upload
        return Resp({"code": 404, "msg": "not found"}, 404)

    def get(self, url, **kw):
        self.calls.append(("get", url, kw))
        assert url == RECORD, url
        return self.records.pop(0)

    def of(self, url):
        return [c for c in self.calls if c[1] == url]


def rec(state, **data):
    return Resp({"code": 200, "data": {"taskId": "t1", "state": state, **data}})


@pytest.fixture
def skills(tmp_path):
    """A fake skills dir holding a stub Skill 67 whose chosen model is NOT hardcoded in Skill 25."""
    root = tmp_path / "skills" / "67-kie-video"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "select_video_model.py").write_text(
        "def select(request):\n"
        "    return {'valid': True, 'selected_model_id': 'stub/model-x', 'reason': request}\n"
    )
    (root / "models.json").write_text(json.dumps({"models": [
        {"canonical_model_id": "stub/model-x", "resolutions": ["480P", "720P", "1080P"]}]}))
    return tmp_path / "skills"


@pytest.fixture
def env(monkeypatch, tmp_path, skills):
    module = load_module()
    monkeypatch.setattr(module, "_skills_dirs", lambda: [skills])
    sleeps = []
    clock = [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=sleep, monotonic=lambda: clock[0]))
    downloads = []

    def download(self, url, output):
        downloads.append(url)
        Path(output).write_bytes(b"video")
        return Path(output)

    monkeypatch.setattr(module.AIProvider, "_download_video", download)
    ns = SimpleNamespace(module=module, sleeps=sleeps, downloads=downloads, tmp=tmp_path)

    def install(fake):
        monkeypatch.setattr(module.requests, "post", fake.post)
        monkeypatch.setattr(module.requests, "get", fake.get)
        return fake

    ns.install = install
    ns.provider = lambda: module.AIProvider("kieai", {"kieai": {"api_key": "test-only-key"}})
    return ns


def test_create_task_payload_has_model_and_nested_input(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/v.mp4"]})]))
    out = env.tmp / "o.mp4"
    env.provider().generate_video("a cat", duration=7, resolution="1080p", output=out)

    (_, url, kw), = fake.of(CREATE)
    assert kw["headers"] == {"Authorization": "Bearer test-only-key"}
    assert kw["json"] == {"model": "stub/model-x",
                          "input": {"prompt": "a cat", "duration": 7, "resolution": "1080P"}}
    assert not [c for c in fake.calls if "video/generate" in c[1]]
    assert env.downloads == ["https://r/v.mp4"]
    assert out.read_bytes() == b"video"


def test_poll_backs_off_through_waiting_queuing_generating_then_success(env):
    fake = env.install(FakeKie(records=[rec("waiting"), rec("queuing"), rec("generating"),
                                        rec("success", response={"resultUrls": ["https://r/v.mp4"]})]))
    env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert env.sleeps[0] == 3.0
    assert env.sleeps == sorted(env.sleeps) and env.sleeps[-1] > 3.0
    assert max(env.sleeps) <= 15.0
    assert [c[2]["params"] for c in fake.calls if c[1] == RECORD] == [{"taskId": "t1"}] * 4


def test_success_result_urls_read_from_result_json_string(env):
    env.install(FakeKie(records=[rec("success", resultJson=json.dumps({"resultUrls": ["https://r/j.mp4"]}))]))
    env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert env.downloads == ["https://r/j.mp4"]


def test_fail_state_raises_with_fail_message(env):
    env.install(FakeKie(records=[rec("generating"), rec("fail", failCode="500", failMsg="content policy")]))
    with pytest.raises(RuntimeError, match="failed: 500 content policy"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert env.downloads == []


def test_poll_times_out_at_deadline(env):
    env.install(FakeKie(records=[rec("generating")] * 200))
    with pytest.raises(RuntimeError, match="timed out after 900s"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert sum(env.sleeps) >= 900


def test_default_deadline_is_at_least_900_seconds(env):
    assert env.module.KIE_POLL_DEADLINE >= 900


@pytest.mark.parametrize("code", [402, 422, 429, 455])
def test_http_200_with_error_body_code_raises(env, code):
    fake = env.install(FakeKie(create=Resp({"code": code, "msg": "nope"}, 200)))
    with pytest.raises(env.module.KieAPIError, match=f"code {code}: nope") as err:
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert err.value.code == code
    assert len(fake.of(CREATE)) == 1 and not fake.of(RECORD)  # no blind retry of a paid call


@pytest.mark.parametrize("status,body", [(401, {"code": 401, "msg": "bad key"}), (200, {"code": 403, "msg": "no"}),
                                         (403, {})])
def test_auth_failure_stops_after_one_attempt(env, status, body):
    fake = env.install(FakeKie(create=Resp(body, status)))
    with pytest.raises(env.module.KieAPIError, match="do not retry"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert len(fake.of(CREATE)) == 1 and env.sleeps == []


def test_record_info_body_error_code_is_not_treated_as_still_running(env):
    env.install(FakeKie(records=[Resp({"code": 500, "msg": "server broke"})]))
    with pytest.raises(env.module.KieAPIError, match="500"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")


def test_record_info_429_is_retried(env):
    env.install(FakeKie(records=[Resp({"code": 429, "msg": "slow"}),
                                 rec("success", response={"resultUrls": ["https://r/v.mp4"]})]))
    env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert env.downloads == ["https://r/v.mp4"]


def test_image_to_video_uploads_then_creates_task_with_download_url(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    image = env.tmp / "pic.png"
    image.write_bytes(b"png-bytes")
    out = env.tmp / "i.mp4"
    result = env.provider().image_to_video(image, "pan left", 5, output=out)

    (_, _, up), = fake.of(UPLOAD)
    assert up["headers"] == {"Authorization": "Bearer test-only-key"}
    assert up["data"]["uploadPath"] == "video-creator/inputs"
    assert not up["data"]["uploadPath"].startswith("/") and not up["data"]["uploadPath"].endswith("/")
    assert up["files"]["file"][0] == "pic.png" and up["files"]["file"][2] == "image/png"
    (_, _, kw), = fake.of(CREATE)
    assert kw["json"]["model"] == "stub/model-x"
    assert kw["json"]["input"] == {"prompt": "pan left", "duration": 5,
                                   "image_urls": ["https://tempfile.example/in.png"]}
    assert result == out


def test_upload_error_body_code_raises_before_any_task(env):
    fake = env.install(FakeKie(upload=Resp({"success": False, "code": 400, "msg": "bad path"})))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(env.module.KieAPIError, match="400"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4")
    assert not fake.of(CREATE)


def test_missing_local_image_fails_before_any_http(env):
    fake = env.install(FakeKie())
    with pytest.raises(FileNotFoundError):
        env.provider().image_to_video(env.tmp / "absent.png", "m", 5, output=env.tmp / "i.mp4")
    assert fake.calls == []


def test_explicit_model_passes_through_unchanged_for_text_and_image(env, monkeypatch):
    monkeypatch.setattr(env.module, "select_kie_video_model",
                        lambda *a, **k: pytest.fail("selector must not run for an explicit model"))
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/a.mp4"]})] * 2))
    env.provider().generate_video("x", output=env.tmp / "t.mp4", model="Some/Model-9.1", resolution="4k")
    image = env.tmp / "pic.jpg"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="Other/Model-2",
                                  image_field="image_url")
    t2v, i2v = [c[2]["json"] for c in fake.of(CREATE)]
    assert t2v["model"] == "Some/Model-9.1" and t2v["input"]["resolution"] == "4k"
    assert i2v["model"] == "Other/Model-2"
    assert i2v["input"]["image_url"] == "https://tempfile.example/in.png"


def test_unsupported_resolution_for_registry_model_is_a_clear_error(env):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match="4k.*not supported.*stub/model-x"):
        env.provider().generate_video("x", resolution="4k", output=env.tmp / "o.mp4")
    assert fake.calls == []


def test_missing_skill_67_fails_with_actionable_error_and_no_http(env, monkeypatch):
    monkeypatch.setattr(env.module, "_skills_dirs", lambda: [env.tmp / "empty"])
    fake = env.install(FakeKie())
    with pytest.raises(RuntimeError, match="67-kie-video.*not installed.*--model"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert fake.calls == []


def test_missing_skill_67_still_allows_explicit_model(env, monkeypatch):
    monkeypatch.setattr(env.module, "_skills_dirs", lambda: [env.tmp / "empty"])
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/v.mp4"]})]))
    env.provider().generate_video("x", output=env.tmp / "o.mp4", model="Some/Model-9.1")
    assert fake.of(CREATE)[0][2]["json"]["model"] == "Some/Model-9.1"


def test_real_skill_67_selector_supplies_default_model():
    module = load_module()
    root = module._find_kie_video_skill()
    if root is None:
        pytest.skip("Skill 67 is not a sibling of this checkout")
    spec = importlib.util.spec_from_file_location("sel67", root / "scripts" / "select_video_model.py")
    sel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sel)
    for task in ("text to video", "image to video"):
        assert module.select_kie_video_model(task, 5) == sel.select(f"{task} 5 seconds")["selected_model_id"]


def test_legacy_dead_endpoint_in_old_config_is_replaced():
    module = load_module()
    ai = module.AIProvider("kieai", {"kieai": {"api_key": "k", "endpoint": "https://api.kie.ai/v1"}})
    assert ai.endpoint == "https://api.kie.ai/api/v1"
    assert module.AIProvider("kieai", {"kieai": {"api_key": "k"}}).endpoint == "https://api.kie.ai/api/v1"


def test_image_to_video_no_longer_raises_not_implemented(env):
    assert callable(getattr(env.module.AIProvider, "_image_to_video_kieai"))


def test_key_falls_back_to_env_when_shared_utils_absent(monkeypatch, tmp_path):
    module = load_module()
    monkeypatch.setattr(module, "_skills_dirs", lambda: [tmp_path])
    monkeypatch.delenv("KIEAI_API_KEY", raising=False)
    monkeypatch.setenv("KIE_API_KEY", "env-key-value")
    assert module.AIProvider("kieai", {}).api_key == "env-key-value"


def test_key_resolved_through_shared_utils_canon(monkeypatch, tmp_path):
    module = load_module()
    shared = tmp_path / "shared-utils"
    shared.mkdir()
    (shared / "key_resolver.py").write_text("def resolve_key(name):\n    return 'canon-' + name\n")
    monkeypatch.setattr(module, "_skills_dirs", lambda: [tmp_path])
    sys.modules.pop("key_resolver", None)
    assert module.AIProvider("kieai", {}).api_key == "canon-kie"
    sys.modules.pop("key_resolver", None)


@pytest.mark.parametrize("provider", ["runway", "pika", "mock"])
def test_other_providers_reject_kie_only_model_option(provider, tmp_path):
    module = load_module()
    ai = module.AIProvider(provider, {provider: {"api_key": "k"}})
    with pytest.raises(ValueError, match="--model"):
        ai.generate_video("x", output=tmp_path / "o.mp4", model="a/b")
