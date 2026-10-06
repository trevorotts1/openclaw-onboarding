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
    result = env.provider().image_to_video(image, "pan left", 5, output=out, model="wan/3-0-video")

    (_, _, up), = fake.of(UPLOAD)
    assert up["headers"] == {"Authorization": "Bearer test-only-key"}
    assert up["data"]["uploadPath"] == "video-creator/inputs"
    assert not up["data"]["uploadPath"].startswith("/") and not up["data"]["uploadPath"].endswith("/")
    assert up["files"]["file"][0] == "pic.png" and up["files"]["file"][2] == "image/png"
    (_, _, kw), = fake.of(CREATE)
    assert kw["json"]["model"] == "wan/3-0-video"
    assert kw["json"]["input"] == {"prompt": "pan left", "duration": 5,
                                   "first_frame_url": "https://tempfile.example/in.png"}
    assert isinstance(kw["json"]["input"]["first_frame_url"], str)
    assert "image_urls" not in kw["json"]["input"]
    assert result == out


def test_upload_error_body_code_raises_before_any_task(env):
    fake = env.install(FakeKie(upload=Resp({"success": False, "code": 400, "msg": "bad path"})))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(env.module.KieAPIError, match="400"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")
    assert not fake.of(CREATE)


def test_missing_local_image_fails_before_any_http(env):
    fake = env.install(FakeKie())
    with pytest.raises(FileNotFoundError):
        env.provider().image_to_video(env.tmp / "absent.png", "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")
    assert fake.calls == []


def test_explicit_model_passes_through_unchanged_for_text_and_image(env, monkeypatch):
    monkeypatch.setattr(env.module, "select_kie_video_model",
                        lambda *a, **k: pytest.fail("selector must not run for an explicit model"))
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/a.mp4"]})] * 2))
    env.provider().generate_video("x", output=env.tmp / "t.mp4", model="Some/Model-9.1", resolution="4k")
    image = env.tmp / "pic.jpg"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="Other/Model-2",
                                  image_field="image_url", image_field_type="string")
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


# Expected mapping, written out independently of the implementation (docs.kie.ai/market/<page>.md).
# models whose docs pin extra required inputs: supplied here so the happy path reaches HTTP
EXTRA_FOR = {"kling-3.0/video": {"sound": False, "mode": "pro", "multi_shots": False, "multi_prompt": [],
                            "aspect_ratio": "16:9"},
             "pixverse-v6/image-to-video": {"quality": "720p"}}


EXPECTED_I2V_FIELDS = [
    ("wan/3-0-video", "first_frame_url", str),
    ("wan/3-0-video-prime", "first_frame_url", str),
    ("wan/2-7-image-to-video", "first_frame_url", str),
    ("bytedance/seedance-2-5", "first_frame_url", str),
    ("bytedance/seedance-2-mini", "first_frame_url", str),
    ("minimax-h3/image-to-video", "first_frame_url", str),
    ("kling/v2-5-turbo-image-to-video-pro", "image_url", str),
    ("kling-3.0-omni/image-to-video", "image_urls", list),
    ("kling-3.0/video", "image_urls", list),
    ("pixverse-v6/image-to-video", "image_urls", list),
    ("happyhorse-1-1/image-to-video", "image_urls", list),
    ("happyhorse/image-to-video", "image_urls", list),
    ("gemini-omni-video", "image_urls", list),
]


@pytest.mark.parametrize("model,field,kind", EXPECTED_I2V_FIELDS)
def test_each_mapped_model_sends_its_documented_image_field_and_type(env, model, field, kind):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    i2v(env, model, input_extra=EXTRA_FOR.get(model))
    inp = fake.of(CREATE)[0][2]["json"]["input"]
    url = "https://tempfile.example/in.png"
    assert inp[field] == (url if kind is str else [url])
    assert type(inp[field]) is kind
    assert {"image_url", "image_urls", "first_frame_url"} & set(inp) == {field}


def test_mapping_table_has_exactly_the_documented_models():
    module = load_module()
    assert set(module.KIE_I2V_IMAGE_FIELD) == {m for m, _, _ in EXPECTED_I2V_FIELDS}


@pytest.mark.parametrize("model", ["runway", "veo3", "veo3_fast", "veo3_lite"])
def test_dedicated_api_models_fail_clearly_before_any_http(env, model):
    fake = env.install(FakeKie())
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match=f"'{model}' uses a dedicated KIE API"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model=model)
    assert fake.calls == []


def test_unknown_model_error_names_model_and_points_to_image_field_flag(env):
    fake = env.install(FakeKie())
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match=r"'brand/new-model'.*not established.*--image-field"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="brand/new-model")
    assert fake.calls == []


def test_cli_image_field_flag_is_forwarded_and_unblocks_unknown_model(monkeypatch, tmp_path):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location(
        "skill25_image_to_video_cli", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    seen = {}

    class Recorder:
        def __init__(self, name, config):
            seen["provider"] = name

        def image_to_video(self, **kwargs):
            seen.update(kwargs)
            return kwargs["output"]

    monkeypatch.setattr(cli, "AIProvider", Recorder)
    image = tmp_path / "pic.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["image_to_video.py", str(image), "--provider", "kieai",
                                      "--model", "brand/new-model", "--image-field", "start_image", "--image-field-type", "string",
                                      "--output", str(tmp_path / "o.mp4")])
    assert cli.main() == 0
    assert seen["provider"] == "kieai"
    assert seen["model"] == "brand/new-model" and seen["image_field"] == "start_image"
    assert seen["image_field_type"] == "string"


def test_cli_image_field_reaches_payload_end_to_end(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="brand/new-model",
                                  image_field="start_image", image_field_type="string")
    assert fake.of(CREATE)[0][2]["json"]["input"]["start_image"] == "https://tempfile.example/in.png"


def test_default_selector_model_without_established_field_fails_before_any_http(env):
    fake = env.install(FakeKie())  # stub Skill 67 selects stub/model-x, whose field is unknown
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="stub/model-x.*not established"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4")
    assert fake.calls == []


def test_image_field_override_wins_over_model_mapping(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video",
                                  image_field="reference_image_urls", image_field_type="array")
    inp = fake.of(CREATE)[0][2]["json"]["input"]
    assert inp["reference_image_urls"] == ["https://tempfile.example/in.png"]
    assert "first_frame_url" not in inp


# ---- per-model input types (docs.kie.ai/market/<page>.md input schemas) ----

def i2v(env, model, **kw):
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    return env.provider().image_to_video(image, kw.pop("prompt", "m"),
                                         kw.pop("duration", 4 if model == "gemini-omni-video" else 5),
                                         output=env.tmp / "i.mp4", model=model, **kw)


def sent_input(fake):
    return fake.of(CREATE)[0][2]["json"]["input"]


# (model, duration given, expected sent duration)
DURATION_OK = [
    ("wan/3-0-video", "7", 7), ("wan/3-0-video", -1, -1), ("wan/3-0-video-prime", 30.0, 30),
    ("wan/2-7-image-to-video", 15, 15), ("bytedance/seedance-2-5", 30, 30),
    ("bytedance/seedance-2-mini", -1, -1), ("minimax-h3/image-to-video", 4, 4),
    ("kling/v2-5-turbo-image-to-video-pro", 5, "5"), ("kling/v2-5-turbo-image-to-video-pro", "10", "10"),
    ("kling-3.0-omni/image-to-video", 3, 3), ("kling-3.0/video", 6, "6"),
    ("pixverse-v6/image-to-video", 1, 1),
    ("happyhorse-1-1/image-to-video", 3, 3), ("happyhorse/image-to-video", 15, 15),
    ("gemini-omni-video", 8, "8"),
]
# (model, bad duration, text the error must contain)
DURATION_BAD = [
    ("wan/3-0-video", 31, "2 to 30 or -1"), ("wan/3-0-video-prime", 1, "2 to 30 or -1"),
    ("wan/2-7-image-to-video", 16, "2 to 15"), ("bytedance/seedance-2-5", 3, "4 to 30 or -1"),
    ("bytedance/seedance-2-mini", 16, "4 to 15 or -1"), ("minimax-h3/image-to-video", 3, "4 to 15"),
    ("kling/v2-5-turbo-image-to-video-pro", 7, "one of 5, 10"),
    ("kling-3.0-omni/image-to-video", 16, "3 to 15"), ("kling-3.0/video", 16, "one of 3, 4"),
    ("pixverse-v6/image-to-video", 0, "1 to 15"),
    ("happyhorse-1-1/image-to-video", 2, "3 to 15"), ("happyhorse/image-to-video", 2.5, "3 to 15"),
    ("gemini-omni-video", 5, "one of 4, 6, 8, 10"),
]
# (model, resolution given, expected sent key, expected sent value)
RES_OK = [
    ("wan/3-0-video", "1080p", "resolution", "1080P"), ("wan/3-0-video-prime", "720p", "resolution", "720P"),
    ("wan/2-7-image-to-video", "720P", "resolution", "720p"),
    ("bytedance/seedance-2-5", "1080P", "resolution", "1080p"),
    ("bytedance/seedance-2-mini", "480p", "resolution", "480p"),
    ("minimax-h3/image-to-video", "2k", "resolution", "2K"),
    ("kling-3.0-omni/image-to-video", "4K", "resolution", "4k"),
    ("pixverse-v6/image-to-video", "1080P", "quality", "1080p"),
    ("happyhorse-1-1/image-to-video", "1080P", "resolution", "1080p"),
    ("happyhorse/image-to-video", "720P", "resolution", "720p"),
    ("gemini-omni-video", "4K", "resolution", "4k"),
]


@pytest.mark.parametrize("model,given,expected", DURATION_OK)
def test_duration_is_coerced_to_documented_type(env, model, given, expected):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, model, duration=given, input_extra=EXTRA_FOR.get(model))
    sent = sent_input(fake)["duration"]
    assert sent == expected and type(sent) is type(expected)


@pytest.mark.parametrize("model,given,allowed", DURATION_BAD)
def test_invalid_duration_fails_before_any_http_naming_allowed_values(env, model, given, allowed):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match=f"{model}.*duration.*{allowed}"):
        i2v(env, model, duration=given, input_extra=EXTRA_FOR.get(model))
    assert fake.calls == []


@pytest.mark.parametrize("model,given,key,expected", RES_OK)
def test_resolution_is_mapped_to_the_documented_enum_and_key(env, model, given, key, expected):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, model, resolution=given)
    inp = sent_input(fake)
    assert inp[key] == expected
    assert key == "quality" or "quality" not in inp


@pytest.mark.parametrize("model,given,allowed", [
    ("wan/3-0-video", "4k", "480P, 720P, 1080P"), ("wan/2-7-image-to-video", "4k", "720p, 1080p"),
    ("bytedance/seedance-2-mini", "1080p", "480p, 720p"), ("minimax-h3/image-to-video", "1080p", "768P, 2K"),
    ("kling-3.0-omni/image-to-video", "480p", "720p, 1080p, 4k"),
    ("pixverse-v6/image-to-video", "4k", "360p, 540p, 720p, 1080p"),
    ("happyhorse-1-1/image-to-video", "4k", "720p, 1080p"), ("happyhorse/image-to-video", "480p", "720p, 1080p"),
    ("gemini-omni-video", "480p", "720p, 1080p, 4k"), ("bytedance/seedance-2-5", "4k", "480p, 720p, 1080p")])
def test_invalid_resolution_fails_before_any_http_naming_allowed_values(env, model, given, allowed):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match=f"{model}.*{allowed}"):
        i2v(env, model, resolution=given)
    assert fake.calls == []


@pytest.mark.parametrize("model,given,expected,bad", [
    ("wan/3-0-video", "ADAPTIVE", "adaptive", "5:4"), ("bytedance/seedance-2-5", "21:9", "21:9", "2:1"),
    ("kling-3.0-omni/image-to-video", "AUTO", "auto", "4:3"), ("gemini-omni-video", "9:16", "9:16", "1:1")])
def test_aspect_ratio_enum(env, model, given, expected, bad):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, model, aspect_ratio=given)
    assert sent_input(fake)["aspect_ratio"] == expected
    with pytest.raises(ValueError, match=f"aspect_ratio.*{bad}"):
        i2v(env, model, aspect_ratio=bad)


def test_seed_must_be_an_in_range_integer_and_string_digits_are_coerced(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, "wan/3-0-video", seed="42")
    assert sent_input(fake)["seed"] == 42
    for bad in (-1, 2147483648, "abc", True):
        with pytest.raises(ValueError, match="seed"):
            i2v(env, "wan/3-0-video", seed=bad)


def test_kling_30_requires_documented_inputs_before_http_and_accepts_them_via_input_extra(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    with pytest.raises(ValueError, match=r"kling-3.0/video requires .*mode.*input_extra.*--input-extra"):
        i2v(env, "kling-3.0/video")
    assert fake.calls == []
    i2v(env, "kling-3.0/video", duration=6,
        input_extra={"sound": True, "mode": "std", "multi_shots": False, "multi_prompt": [],
                     "aspect_ratio": "16:9"})
    inp = sent_input(fake)
    assert inp["duration"] == "6" and inp["mode"] == "std" and inp["image_urls"] == ["https://tempfile.example/in.png"]


def test_kling_30_mode_enum_checked_in_input_extra(env):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match="mode.*std, pro, 4K"):
        i2v(env, "kling-3.0/video",
            input_extra={"sound": True, "mode": "ultra", "multi_shots": False, "multi_prompt": [],
                         "aspect_ratio": "16:9"})
    assert fake.calls == []


def test_pixverse_requires_quality_and_resolution_option_fills_it(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    with pytest.raises(ValueError, match="pixverse-v6/image-to-video requires quality"):
        i2v(env, "pixverse-v6/image-to-video")
    assert fake.calls == []
    i2v(env, "pixverse-v6/image-to-video", input_extra={"quality": "540P"})
    assert sent_input(fake)["quality"] == "540p"


def test_unmapped_explicit_model_input_passes_through_unchanged(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/v.mp4"]})]))
    env.provider().generate_video("x", duration=7, output=env.tmp / "o.mp4", model="Some/Model-9.1",
                                  resolution="4k", input_extra={"weird": [1]})
    assert sent_input(fake) == {"prompt": "x", "duration": 7, "resolution": "4k", "weird": [1]}


def test_text_to_video_path_validates_mapped_model_before_http(env):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match="wan/3-0-video.*duration.*2 to 30 or -1"):
        env.provider().generate_video("x", duration=99, output=env.tmp / "o.mp4", model="wan/3-0-video")
    with pytest.raises(ValueError, match="resolution.*480P, 720P, 1080P"):
        env.provider().generate_video("x", resolution="4k", output=env.tmp / "o.mp4", model="wan/3-0-video")
    assert fake.calls == []


def test_every_mapped_image_model_has_an_input_spec_with_a_duration_rule():
    module = load_module()
    assert set(module.KIE_INPUT_SPECS) == set(module.KIE_I2V_IMAGE_FIELD)
    assert all("duration" in v["fields"] for v in module.KIE_INPUT_SPECS.values())


# ---- explicit image field type ----

def test_image_field_without_type_is_rejected_for_unmapped_model_before_http(env):
    fake = env.install(FakeKie())
    with pytest.raises(ValueError, match=r"--image-field-type string\|array.*never guessed"):
        i2v(env, "brand/new-model", image_field="start_images")  # trailing s is NOT used to guess
    assert fake.calls == []


@pytest.mark.parametrize("kind,expected", [("string", "https://tempfile.example/in.png"),
                                           ("array", ["https://tempfile.example/in.png"])])
def test_image_field_type_is_honoured_regardless_of_the_name(env, kind, expected):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, "brand/new-model", image_field="start_images", image_field_type=kind)
    assert sent_input(fake)["start_images"] == expected


def test_image_field_matching_the_mapped_key_needs_no_type(env):
    fake = env.install(FakeKie(records=[rec("success", response={"resultUrls": ["https://r/i.mp4"]})]))
    i2v(env, "wan/3-0-video", image_field="first_frame_url")
    assert sent_input(fake)["first_frame_url"] == "https://tempfile.example/in.png"


def test_invalid_image_field_type_value_is_rejected_by_the_cli(monkeypatch, tmp_path, capsys):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_i2v_cli2", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(sys, "argv", ["image_to_video.py", "x.png", "--image-field-type", "list"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "string,array" in capsys.readouterr().err.replace("'", "").replace(" ", "")


def test_cli_help_documents_image_field_type_and_input_extra(monkeypatch, capsys):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_i2v_cli3", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(sys, "argv", ["image_to_video.py", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    text = " ".join(capsys.readouterr().out.split())
    assert "--image-field-type {string,array}" in text and "never guessed from the name" in text
    assert "--input-extra JSON" in text


@pytest.mark.parametrize("script,argv_extra", [("image_to_video", ["x.png"]), ("text_to_video", ["a prompt"])])
def test_cli_input_extra_json_is_parsed_and_forwarded(monkeypatch, tmp_path, script, argv_extra):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location(f"skill25_{script}_cli4", SKILL_ROOT / "scripts" / f"{script}.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    seen = {}

    class Recorder:
        def __init__(self, name, config):
            pass

        def image_to_video(self, **kwargs):
            seen.update(kwargs)
            return kwargs["output"]

        def generate_video(self, **kwargs):
            seen.update(kwargs)
            return kwargs["output"]

    monkeypatch.setattr(cli, "AIProvider", Recorder)
    image = tmp_path / "pic.png"
    image.write_bytes(b"x")
    argv = [str(image)] if script == "image_to_video" else argv_extra
    monkeypatch.setattr(sys, "argv", [f"{script}.py", *argv, "--provider", "kieai", "--output",
                                      str(tmp_path / "o.mp4"), "--input-extra", '{"quality": "720p", "n": 2}'])
    assert cli.main() == 0
    assert seen["input_extra"] == {"quality": "720p", "n": 2}


@pytest.mark.parametrize("bad", ["not json", "[1, 2]"])
def test_cli_input_extra_rejects_non_object_json(monkeypatch, bad):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_t2v_cli5", SKILL_ROOT / "scripts" / "text_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(sys, "argv", ["text_to_video.py", "p", "--input-extra", bad])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2


def test_other_providers_reject_input_extra(tmp_path):
    module = load_module()
    ai = module.AIProvider("mock", {"mock": {"api_key": "k"}})
    with pytest.raises(ValueError, match="--input-extra"):
        ai.generate_video("x", output=tmp_path / "o.mp4", input_extra={"a": 1})
