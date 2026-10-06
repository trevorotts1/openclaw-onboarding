"""KIE flow for Skill 25 through the Skill 74 transport, against a stubbed Skill 74.

No network, no key, no ffmpeg: `kie74` (the one function that runs Skill 74's CLI) is replaced by Fake74, which
records every call and returns scripted Skill 74 results. A second group runs the real `kie74` against a stub
CLI script to prove the command line, the environment and the missing-adapter error.
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
CREATE = "run"      # a Skill 74 `run` call (validate, createTask or the schema's path, poll, save)
UPLOAD = "upload"
URL = "https://tempfile.example/in.png"


def load_module():
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location(
        f"skill25_ai_providers_{abs(hash(SKILL_ROOT))}", SKILL_ROOT / "scripts" / "ai_providers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ok_run(task="t1"):
    return {"state": "success", "task_id": task, "result_urls": ["https://r/v.mp4"], "data": {}}


def fail_run(code, msg, **kw):
    return {"state": "fail", "task_id": kw.pop("task_id", None), "error": {"code": code, "msg": msg}, **kw}


class Fake74:
    """Stands in for kie74(). `run` and `upload` are single scripted replies (dict, or a callable)."""

    def __init__(self, run=None, upload=None):
        self.run = run or ok_run()
        self.upload = upload or {"state": "success", "data": {"download_url": URL}}
        self.calls = []

    def __call__(self, command, *args, api_key=None, request=None, timeout=300):
        self.calls.append((command, args, request, api_key, timeout))
        if command == "upload":
            return self.upload
        assert command == "run", command
        result = dict(self.run)
        if result.get("state") == "success":  # what Skill 74 does: save the file in --save-dir
            save_dir = Path(args[args.index("--save-dir") + 1])
            saved = save_dir / "t1_0.mp4"
            saved.write_bytes(b"video" * 400)
            result["saved_paths"] = [str(saved)]
        return result

    def of(self, command):
        """Calls of one kind, shaped like the old HTTP log: (method, command, {'json': request, 'args': args})."""
        return [("post", c[0], {"json": c[2], "args": c[1], "key": c[3], "timeout": c[4]})
                for c in self.calls if c[0] == command]


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
    monkeypatch.setattr(module.AIProvider, "_validate_downloaded_video", staticmethod(lambda path: None))
    # These contract tests use short prompts; rule 12 prompt length is covered by tests/unit/kie-prompt-enforcer-and-gates.test.py
    monkeypatch.setattr(module.AIProvider, "_check_prompt_budget", lambda self, prompt, model: None)
    ns = SimpleNamespace(module=module, tmp=tmp_path)

    def install(fake):
        monkeypatch.setattr(module, "kie74", fake)
        return fake

    ns.install = install
    ns.provider = lambda: module.AIProvider("kieai", {"kieai": {"api_key": "test-only-key"}})
    return ns


def test_run_request_has_model_and_nested_input_and_the_file_lands_at_output(env):
    fake = env.install(Fake74())
    out = env.tmp / "o.mp4"
    env.provider().generate_video("a cat", duration=7, resolution="1080p", output=out)

    (_, _, call), = fake.of(CREATE)
    assert call["json"] == {"model": "stub/model-x",
                            "input": {"prompt": "a cat", "duration": 7, "resolution": "1080P"}}
    assert call["key"] == "test-only-key"
    assert call["args"][call["args"].index("--timeout") + 1] == 900
    assert out.read_bytes() == b"video" * 400
    assert not list(env.tmp.glob(".*.part"))


def test_callback_url_is_forwarded_as_callBackUrl(env):
    fake = env.install(Fake74())
    env.provider().generate_video("x", output=env.tmp / "o.mp4", callback_url="https://relay.example/cb")
    assert fake.of(CREATE)[0][2]["json"]["callBackUrl"] == "https://relay.example/cb"


def test_timeout_option_is_the_run_deadline(env):
    fake = env.install(Fake74())
    env.provider().generate_video("x", output=env.tmp / "o.mp4", timeout=1200)
    args = fake.of(CREATE)[0][2]["args"]
    assert args[args.index("--timeout") + 1] == 1200


def test_failed_task_raises_with_fail_message(env):
    env.install(Fake74(run=fail_run("500", "content policy", task_id="t1", data={"state_raw": "fail"})))
    with pytest.raises(RuntimeError, match="failed: 500 content policy"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert not (env.tmp / "o.mp4").exists()


def test_deadline_reached_raises_timed_out(env):
    env.install(Fake74(run={"state": "running", "task_id": "t1", "error": {"code": "timeout", "msg": "deadline"}}))
    with pytest.raises(RuntimeError, match="timed out after 900s"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")


def test_default_deadline_is_at_least_900_seconds(env):
    assert env.module.KIE_POLL_DEADLINE >= 900


@pytest.mark.parametrize("code", [402, 422, 429, 455])
def test_error_body_code_raises_kie_api_error(env, code):
    fake = env.install(Fake74(run=fail_run(code, "nope")))
    with pytest.raises(env.module.KieAPIError, match=f"code {code}: nope") as err:
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert err.value.code == code
    assert len(fake.of(CREATE)) == 1  # one run call; Skill 74 never retries a paid createTask


@pytest.mark.parametrize("code", [401, 403])
def test_auth_failure_stops_after_one_attempt(env, code):
    fake = env.install(Fake74(run=fail_run(code, "bad key")))
    with pytest.raises(env.module.KieAPIError, match="do not retry"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert len(fake.of(CREATE)) == 1


def test_validation_failure_from_skill_74_is_an_error_before_any_file(env):
    env.install(Fake74(run=fail_run("validation_failed", "input.prompt: longer than maxLength 100")))
    with pytest.raises(env.module.KieAPIError, match="maxLength 100"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")


def test_success_without_a_saved_file_is_an_error(env):
    fake = Fake74()
    fake.run = {"state": "success", "task_id": "t1", "saved_paths": [], "data": {"response": {"taskId": "z"}}}
    env.install(lambda *a, **k: fake.run)
    with pytest.raises(RuntimeError, match="returned no result file"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")


def test_tiny_or_undecodable_saved_file_is_rejected_and_output_untouched(env, monkeypatch):
    out = env.tmp / "o.mp4"
    out.write_bytes(b"existing-good-output")

    def tiny(command, *args, **kw):
        d = Path(args[args.index("--save-dir") + 1]) / "t.mp4"
        d.write_bytes(b"x")
        return {"state": "success", "task_id": "t", "saved_paths": [str(d)]}

    env.install(tiny)
    with pytest.raises(RuntimeError, match="too small"):
        env.provider().generate_video("x", output=out)
    assert out.read_bytes() == b"existing-good-output"

    def undecodable(path):
        raise RuntimeError("ffprobe could not decode video: bad")

    monkeypatch.setattr(env.module.AIProvider, "_validate_downloaded_video", staticmethod(undecodable))
    env.install(Fake74())
    with pytest.raises(RuntimeError, match="ffprobe could not decode"):
        env.provider().generate_video("x", output=out)
    assert out.read_bytes() == b"existing-good-output"
    assert not list(env.tmp.glob(".*.part"))


def test_image_to_video_uploads_through_74_then_runs_with_the_download_url(env):
    fake = env.install(Fake74())
    image = env.tmp / "pic.png"
    image.write_bytes(b"png-bytes")
    out = env.tmp / "i.mp4"
    result = env.provider().image_to_video(image, "pan left", 5, output=out, model="wan/3-0-video")

    (_, _, up), = fake.of(UPLOAD)
    assert up["args"] == ("--file", str(image), "--upload-path", "video-creator/inputs")
    assert up["key"] == "test-only-key"
    assert not up["args"][3].startswith("/") and not up["args"][3].endswith("/")
    (_, _, kw), = fake.of(CREATE)
    assert kw["json"]["model"] == "wan/3-0-video"
    assert kw["json"]["input"] == {"prompt": "pan left", "duration": 5, "first_frame_url": URL}
    assert isinstance(kw["json"]["input"]["first_frame_url"], str)
    assert "image_urls" not in kw["json"]["input"]
    assert [c[0] for c in fake.calls] == ["upload", "run"]  # upload first
    assert result == out


def test_upload_error_raises_before_any_task(env):
    fake = env.install(Fake74(upload=fail_run(400, "bad path")))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(env.module.KieAPIError, match="400"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")
    assert not fake.of(CREATE)


def test_upload_without_a_download_url_is_an_error(env):
    env.install(Fake74(upload={"state": "success", "data": {}}))
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="no download URL"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")


def test_missing_local_image_fails_before_any_call(env):
    fake = env.install(Fake74())
    with pytest.raises(FileNotFoundError):
        env.provider().image_to_video(env.tmp / "absent.png", "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")
    assert fake.calls == []


def test_explicit_model_passes_through_unchanged_for_text_and_image(env, monkeypatch):
    monkeypatch.setattr(env.module, "select_kie_video_model",
                        lambda *a, **k: pytest.fail("selector must not run for an explicit model"))
    fake = env.install(Fake74())
    env.provider().generate_video("x", output=env.tmp / "t.mp4", model="Some/Model-9.1", resolution="4k")
    image = env.tmp / "pic.jpg"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="Other/Model-2",
                                  image_field="image_url", image_field_type="string")
    t2v, i2v_ = [c[2]["json"] for c in fake.of(CREATE)]
    assert t2v["model"] == "Some/Model-9.1" and t2v["input"]["resolution"] == "4k"
    assert i2v_["model"] == "Other/Model-2"
    assert i2v_["input"]["image_url"] == URL


def test_unsupported_resolution_for_registry_model_is_a_clear_error(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match="4k.*not supported.*stub/model-x"):
        env.provider().generate_video("x", resolution="4k", output=env.tmp / "o.mp4")
    assert fake.calls == []


def test_missing_skill_67_fails_with_actionable_error_and_no_call(env, monkeypatch):
    monkeypatch.setattr(env.module, "_skills_dirs", lambda: [env.tmp / "empty"])
    fake = env.install(Fake74())
    with pytest.raises(RuntimeError, match="67-kie-video.*not installed.*--model"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4")
    assert fake.calls == []


def test_missing_skill_67_still_allows_explicit_model(env, monkeypatch):
    monkeypatch.setattr(env.module, "_skills_dirs", lambda: [env.tmp / "empty"])
    fake = env.install(Fake74())
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


# ---- one KIE path: the real kie74() against a stub Skill 74 CLI ----

STUB_CLI = """\
import json, os, sys
argv = sys.argv[1:]
open(os.environ["STUB_LOG"], "w").write(json.dumps({"argv": argv, "key": os.environ.get("KIE_API_KEY")}))
req = argv[argv.index("--request") + 1] if "--request" in argv else None
if req:
    open(os.environ["STUB_LOG"] + ".req", "w").write(open(req).read())
print(json.dumps({"state": "success", "data": {"download_url": "https://x/y.png"}}))
"""


def stub_74(tmp_path):
    root = tmp_path / "skills" / "74-kie-live-adapter" / "scripts"
    root.mkdir(parents=True)
    (root / "kie_live_adapter.py").write_text(STUB_CLI)
    return tmp_path / "skills"


def test_kie74_runs_the_cli_active_json_with_key_in_env_not_argv(monkeypatch, tmp_path):
    module = load_module()
    monkeypatch.setattr(module, "_skills_dirs", lambda: [stub_74(tmp_path)])
    log = tmp_path / "log.json"
    monkeypatch.setenv("STUB_LOG", str(log))
    res = module.kie74("run", "--save-dir", "/tmp/d", request={"model": "m", "input": {"prompt": "p"}},
                       api_key="secret-key-value")
    assert res["state"] == "success"
    seen = json.loads(log.read_text())
    assert seen["argv"][:4] == ["run", "--mode", "active", "--json"]
    assert "--save-dir" in seen["argv"] and "secret-key-value" not in " ".join(seen["argv"])
    assert seen["key"] == "secret-key-value"
    assert json.loads(Path(str(log) + ".req").read_text()) == {"model": "m", "input": {"prompt": "p"}}


def test_missing_skill_74_fails_clearly_with_no_fallback_client(env, monkeypatch):
    monkeypatch.setattr(env.module, "_skills_dirs", lambda: [env.tmp / "empty"])
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match=r"74-kie-live-adapter.*not installed.*no KIE client of its own"):
        env.provider().generate_video("x", output=env.tmp / "o.mp4", model="Some/Model-9.1")
    with pytest.raises(RuntimeError, match="74-kie-live-adapter.*not installed"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="wan/3-0-video")


def test_kie74_without_json_output_is_a_clear_error(monkeypatch, tmp_path):
    module = load_module()
    root = tmp_path / "skills" / "74-kie-live-adapter" / "scripts"
    root.mkdir(parents=True)
    (root / "kie_live_adapter.py").write_text("import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n")
    monkeypatch.setattr(module, "_skills_dirs", lambda: [tmp_path / "skills"])
    with pytest.raises(RuntimeError, match=r"returned no JSON \(exit 3\): boom"):
        module.kie74("credits")


def test_skill_25_kie_path_has_no_http_client_of_its_own():
    source = (SKILL_ROOT / "scripts" / "ai_providers.py").read_text(encoding="utf-8")
    for forbidden in ("api.kie.ai", "kieai.redpandaai", "recordInfo", "/jobs/createTask", "file-stream-upload"):
        assert forbidden not in source, forbidden
    module = load_module()
    assert not hasattr(module, "KIE_API_BASE") and not hasattr(module, "KIE_UPLOAD_URL")
    assert not hasattr(module.AIProvider, "_kie_call")


def test_old_kieai_endpoint_config_is_ignored_not_used():
    module = load_module()
    ai = module.AIProvider("kieai", {"kieai": {"api_key": "k"}})
    assert ai.endpoint is None


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
             "pixverse-v6/image-to-video": {"quality": "720p"},
             "runway": {"quality": "720p"}}


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
    ("runway", "image_url", str),
    ("veo-3-1", "image_urls", list),
    ("veo3", "image_urls", list),
    ("veo3_fast", "image_urls", list),
    ("veo3_lite", "image_urls", list),
]


@pytest.mark.parametrize("model,field,kind", EXPECTED_I2V_FIELDS)
def test_each_mapped_model_sends_its_documented_image_field_and_type(env, model, field, kind):
    fake = env.install(Fake74())
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


@pytest.mark.parametrize("model", ["runway", "veo3", "veo3_fast", "veo3_lite", "veo-3-1"])
def test_runway_and_veo_models_are_routed_through_skill_74_not_refused(env, model):
    fake = env.install(Fake74())
    out = i2v(env, model, input_extra=EXTRA_FOR.get(model))
    assert out == env.tmp / "i.mp4"
    assert [c[0] for c in fake.calls] == ["upload", "run"]
    assert fake.of(CREATE)[0][2]["json"]["model"] == model  # Skill 74 picks the path the schema declares


@pytest.mark.parametrize("model", ["runway", "veo3_fast"])
def test_runway_and_veo_text_to_video_goes_through_skill_74(env, model):
    fake = env.install(Fake74())
    env.provider().generate_video("x", duration=6 if model != "runway" else 5, resolution="720p",
                                  output=env.tmp / "t.mp4", model=model, input_extra=EXTRA_FOR.get(model))
    assert fake.of(CREATE)[0][2]["json"]["model"] == model


def test_unknown_model_error_names_model_and_points_to_image_field_flag(env):
    fake = env.install(Fake74())
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
    fake = env.install(Fake74())
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4", model="brand/new-model",
                                  image_field="start_image", image_field_type="string")
    assert fake.of(CREATE)[0][2]["json"]["input"]["start_image"] == "https://tempfile.example/in.png"


def test_default_selector_model_without_established_field_fails_before_any_http(env):
    fake = env.install(Fake74())  # stub Skill 67 selects stub/model-x, whose field is unknown
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="stub/model-x.*not established"):
        env.provider().image_to_video(image, "m", 5, output=env.tmp / "i.mp4")
    assert fake.calls == []


def test_image_field_override_wins_over_model_mapping(env):
    fake = env.install(Fake74())
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
                                         kw.pop("duration", 4 if model.startswith(("gemini", "veo")) else 5),
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
    ("runway", 5, 5), ("runway", "10", 10), ("veo-3-1", 8, 8), ("veo3", "6", 6), ("veo3_lite", 4.0, 4),
]
# (model, bad duration, text the error must contain)
DURATION_BAD = [
    ("wan/3-0-video", 31, "2 to 30 or -1"), ("wan/3-0-video-prime", 1, "2 to 30 or -1"),
    ("wan/2-7-image-to-video", 16, "2 to 15"), ("bytedance/seedance-2-5", 3, "4 to 30 or -1"),
    ("bytedance/seedance-2-mini", 16, "4 to 15 or -1"), ("minimax-h3/image-to-video", 3, "4 to 15"),
    ("kling/v2-5-turbo-image-to-video-pro", 7, "one of 5, 10"),
    ("kling-3.0-omni/image-to-video", 16, "3 to 15"), ("kling-3.0/video", 16, "one of 3, 4"),
    ("pixverse-v6/image-to-video", 0, "1 to 15"),
    ("happyhorse-1-1/image-to-video", 2, "3 to 15"), ("happyhorse-1-1/image-to-video", 5.5, "integer 3 to 15"),
    ("happyhorse/image-to-video", 2.5, "3 to 15"),
    ("gemini-omni-video", 5, "one of 4, 6, 8, 10"),
    ("runway", 11, "5 to 10"), ("veo-3-1", 5, "one of 4, 6, 8"), ("veo3_fast", 10, "one of 4, 6, 8"),
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
    ("runway", "1080P", "quality", "1080p"), ("veo3", "4K", "resolution", "4k"),
]


@pytest.mark.parametrize("model,given,expected", DURATION_OK)
def test_duration_is_coerced_to_documented_type(env, model, given, expected):
    fake = env.install(Fake74())
    i2v(env, model, duration=given, input_extra=EXTRA_FOR.get(model))
    sent = sent_input(fake)["duration"]
    assert sent == expected and type(sent) is type(expected)


@pytest.mark.parametrize("model,given,allowed", DURATION_BAD)
def test_invalid_duration_fails_before_any_http_naming_allowed_values(env, model, given, allowed):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match=f"{model}.*duration.*{allowed}"):
        i2v(env, model, duration=given, input_extra=EXTRA_FOR.get(model))
    assert fake.calls == []


@pytest.mark.parametrize("model,given,key,expected", RES_OK)
def test_resolution_is_mapped_to_the_documented_enum_and_key(env, model, given, key, expected):
    fake = env.install(Fake74())
    i2v(env, model, resolution=given)
    inp = sent_input(fake)
    assert inp[key] == expected
    assert key == "quality" or "quality" not in inp
    assert key == "resolution" or "resolution" not in inp  # pixverse never receives a "resolution" key


@pytest.mark.parametrize("model,given,allowed", [
    ("wan/3-0-video", "4k", "480P, 720P, 1080P"), ("wan/2-7-image-to-video", "4k", "720p, 1080p"),
    ("bytedance/seedance-2-mini", "1080p", "480p, 720p"), ("minimax-h3/image-to-video", "1080p", "768P, 2K"),
    ("kling-3.0-omni/image-to-video", "480p", "720p, 1080p, 4k"),
    ("pixverse-v6/image-to-video", "4k", "360p, 540p, 720p, 1080p"),
    ("happyhorse-1-1/image-to-video", "4k", "720p, 1080p"), ("happyhorse/image-to-video", "480p", "720p, 1080p"),
    ("gemini-omni-video", "480p", "720p, 1080p, 4k"), ("bytedance/seedance-2-5", "4k", "480p, 720p, 1080p"),
    ("runway", "4k", "720p, 1080p"), ("veo3_fast", "480p", "720p, 1080p, 4k")])
def test_invalid_resolution_fails_before_any_http_naming_allowed_values(env, model, given, allowed):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match=f"{model}.*{allowed}"):
        i2v(env, model, resolution=given)
    assert fake.calls == []


@pytest.mark.parametrize("model,given,expected,bad", [
    ("wan/3-0-video", "ADAPTIVE", "adaptive", "5:4"), ("bytedance/seedance-2-5", "21:9", "21:9", "2:1"),
    ("kling-3.0-omni/image-to-video", "AUTO", "auto", "4:3"), ("gemini-omni-video", "9:16", "9:16", "1:1")])
def test_aspect_ratio_enum(env, model, given, expected, bad):
    fake = env.install(Fake74())
    i2v(env, model, aspect_ratio=given)
    assert sent_input(fake)["aspect_ratio"] == expected
    with pytest.raises(ValueError, match=f"aspect_ratio.*{bad}"):
        i2v(env, model, aspect_ratio=bad)


def test_seed_must_be_an_in_range_integer_and_string_digits_are_coerced(env):
    fake = env.install(Fake74())
    i2v(env, "wan/3-0-video", seed="42")
    assert sent_input(fake)["seed"] == 42
    for bad in (-1, 2147483648, "abc", True):
        with pytest.raises(ValueError, match="seed"):
            i2v(env, "wan/3-0-video", seed=bad)


def test_kling_30_requires_documented_inputs_before_http_and_accepts_them_via_input_extra(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match=r"kling-3.0/video requires .*mode.*input_extra.*--input-extra"):
        i2v(env, "kling-3.0/video")
    assert fake.calls == []
    i2v(env, "kling-3.0/video", duration=6,
        input_extra={"sound": True, "mode": "std", "multi_shots": False, "multi_prompt": [],
                     "aspect_ratio": "16:9"})
    inp = sent_input(fake)
    assert inp["duration"] == "6" and inp["mode"] == "std" and inp["image_urls"] == ["https://tempfile.example/in.png"]


def test_kling_30_mode_enum_checked_in_input_extra(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match="mode.*std, pro, 4K"):
        i2v(env, "kling-3.0/video",
            input_extra={"sound": True, "mode": "ultra", "multi_shots": False, "multi_prompt": [],
                         "aspect_ratio": "16:9"})
    assert fake.calls == []


def test_pixverse_requires_quality_and_resolution_option_fills_it(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match="pixverse-v6/image-to-video requires quality"):
        i2v(env, "pixverse-v6/image-to-video")
    assert fake.calls == []
    i2v(env, "pixverse-v6/image-to-video", input_extra={"quality": "540P"})
    assert sent_input(fake)["quality"] == "540p"


def test_unmapped_explicit_model_input_passes_through_unchanged(env):
    fake = env.install(Fake74())
    env.provider().generate_video("x", duration=7, output=env.tmp / "o.mp4", model="Some/Model-9.1",
                                  resolution="4k", input_extra={"weird": [1]})
    assert sent_input(fake) == {"prompt": "x", "duration": 7, "resolution": "4k", "weird": [1]}


def test_text_to_video_path_validates_mapped_model_before_http(env):
    fake = env.install(Fake74())
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
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match=r"--image-field-type string\|array.*never guessed"):
        i2v(env, "brand/new-model", image_field="start_images")  # trailing s is NOT used to guess
    assert fake.calls == []


@pytest.mark.parametrize("kind,expected", [("string", "https://tempfile.example/in.png"),
                                           ("array", ["https://tempfile.example/in.png"])])
def test_image_field_type_is_honoured_regardless_of_the_name(env, kind, expected):
    fake = env.install(Fake74())
    i2v(env, "brand/new-model", image_field="start_images", image_field_type=kind)
    assert sent_input(fake)["start_images"] == expected


def test_image_field_matching_the_mapped_key_needs_no_type(env):
    fake = env.install(Fake74())
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


# ---- QC nits: gemini seed, happyhorse integer duration, pixverse key, CLI resolution, raw duration ----

@pytest.mark.parametrize("seed,ok", [(0, True), (2147483647, True), (-1, False), (2147483648, False)])
def test_gemini_seed_range_is_enforced(env, seed, ok):
    fake = env.install(Fake74())
    if ok:
        i2v(env, "gemini-omni-video", seed=seed)
        assert sent_input(fake)["seed"] == seed
    else:
        with pytest.raises(ValueError, match="gemini-omni-video.*seed.*0 to 2147483647"):
            i2v(env, "gemini-omni-video", seed=seed)
        assert fake.calls == []


def test_happyhorse_11_duration_is_integer_valued(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match="happyhorse-1-1/image-to-video.*duration=5.5"):
        i2v(env, "happyhorse-1-1/image-to-video", duration=5.5)
    assert fake.calls == []
    i2v(env, "happyhorse-1-1/image-to-video", duration=5.0)
    assert sent_input(fake)["duration"] == 5 and type(sent_input(fake)["duration"]) is int


def test_pixverse_conflicting_resolution_and_quality_is_rejected_before_http(env):
    fake = env.install(Fake74())
    with pytest.raises(ValueError, match="uses 'quality' instead of 'resolution'"):
        i2v(env, "pixverse-v6/image-to-video", resolution="1080p", input_extra={"quality": "540p"})
    assert fake.calls == []


def test_pixverse_same_resolution_and_quality_sends_only_quality(env):
    fake = env.install(Fake74())
    i2v(env, "pixverse-v6/image-to-video", resolution="720P", input_extra={"quality": "720p"})
    inp = sent_input(fake)
    assert inp["quality"] == "720p" and "resolution" not in inp


def test_pixverse_text_to_video_path_also_renames_resolution(env):
    fake = env.install(Fake74())
    env.provider().generate_video("x", duration=5, resolution="1080p", output=env.tmp / "o.mp4",
                                  model="pixverse-v6/image-to-video")
    inp = sent_input(fake)
    assert inp["quality"] == "1080p" and "resolution" not in inp


def test_image_to_video_does_not_int_cast_duration_before_per_model_validation(env, monkeypatch):
    module = load_module()
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_i2v_cli6", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    fake = env.install(Fake74())
    monkeypatch.setattr(cli, "AIProvider", lambda name, cfg: env.provider())
    image = env.tmp / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(ValueError, match="happyhorse-1-1/image-to-video.*duration=5.5"):
        cli.image_to_video(image, output=env.tmp / "o.mp4", duration=5.5, provider="kieai",
                           model="happyhorse-1-1/image-to-video")  # int(5.5) would have silently become 5
    assert fake.calls == []


@pytest.mark.parametrize("script,extra", [("image_to_video", ["x.png"]), ("text_to_video", ["a prompt"])])
@pytest.mark.parametrize("resolution", ["480p", "540p", "720p", "1080p", "2K", "4k", "768P"])
def test_cli_resolution_accepts_every_documented_value_and_forwards_it(monkeypatch, tmp_path, script, extra,
                                                                      resolution):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location(f"skill25_{script}_cli7", SKILL_ROOT / "scripts" / f"{script}.py")
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
    argv = [str(image)] if script == "image_to_video" else extra
    monkeypatch.setattr(sys, "argv", [f"{script}.py", *argv, "--provider", "kieai", "--resolution", resolution,
                                      "--output", str(tmp_path / "o.mp4")])
    assert cli.main() == 0
    assert seen["resolution"] == resolution


def test_cli_image_duration_is_forwarded_raw(monkeypatch, tmp_path):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_i2v_cli8", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    seen = {}

    class Recorder:
        def __init__(self, name, config):
            pass

        def image_to_video(self, **kwargs):
            seen.update(kwargs)
            return kwargs["output"]

    monkeypatch.setattr(cli, "AIProvider", Recorder)
    image = tmp_path / "pic.png"
    image.write_bytes(b"x")
    monkeypatch.setattr(sys, "argv", ["image_to_video.py", str(image), "--provider", "kieai", "--duration", "5.5",
                                      "--output", str(tmp_path / "o.mp4")])
    assert cli.main() == 0
    assert seen["duration"] == 5.5


@pytest.mark.parametrize("provider", ["runway", "pika", "mock"])
def test_non_kie_providers_reject_resolutions_they_do_not_support(provider, tmp_path):
    module = load_module()
    ai = module.AIProvider(provider, {provider: {"api_key": "k"}})
    with pytest.raises(ValueError, match="does not support resolution '2K'"):
        ai.generate_video("x", resolution="2K", output=tmp_path / "o.mp4")


def test_local_image_mode_rejects_unknown_resolution_instead_of_ignoring_it(monkeypatch, tmp_path):
    sys.modules.pop("ai_providers", None)
    spec = importlib.util.spec_from_file_location("skill25_i2v_cli9", SKILL_ROOT / "scripts" / "image_to_video.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    class FakeClip:
        def resize(self, **kw):
            return self

    fake_editor = ModuleType("moviepy.editor")
    fake_editor.ImageClip = lambda path: FakeClip()
    fake_editor.AudioFileClip = object
    audio_fx = ModuleType("moviepy.audio.fx.all")
    for name in ("audio_fadein", "audio_fadeout", "volumex"):
        setattr(audio_fx, name, lambda *a, **k: None)
    for name, mod in {"moviepy": ModuleType("moviepy"), "moviepy.editor": fake_editor,
                      "moviepy.audio": ModuleType("moviepy.audio"), "moviepy.audio.fx": ModuleType("moviepy.audio.fx"),
                      "moviepy.audio.fx.all": audio_fx}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    image = tmp_path / "pic.png"
    image.write_bytes(b"x")
    with pytest.raises(ValueError, match="Unsupported resolution '2K' for local mode"):
        cli.image_to_video(image, output=tmp_path / "o.mp4", provider="local", resolution="2K")


# Specs for the three models re-verified against fresh docs fetches (kling-3.0-omni image-to-video,
# happyhorse/image-to-video, wan/3-0-video-prime): literal expectations from each page's input schema.
def test_specs_for_reverified_models_match_their_docs_pages():
    f = load_module().KIE_INPUT_SPECS
    omni = f["kling-3.0-omni/image-to-video"]["fields"]
    assert omni["duration"] == {"kind": "int", "min": 3, "max": 15}
    assert omni["resolution"]["values"] == ["720p", "1080p", "4k"]
    assert omni["aspect_ratio"]["values"] == ["16:9", "9:16", "1:1", "auto"]
    hh = f["happyhorse/image-to-video"]["fields"]
    assert hh["duration"] == {"kind": "int", "min": 3, "max": 15}
    assert hh["resolution"]["values"] == ["720p", "1080p"]
    assert hh["seed"] == {"kind": "int", "min": 0, "max": 2147483647}
    prime = f["wan/3-0-video-prime"]["fields"]
    assert prime["duration"] == {"kind": "int", "min": 2, "max": 30, "also": (-1,)}
    assert prime["resolution"]["values"] == ["480P", "720P", "1080P"]
    assert prime["aspect_ratio"]["values"] == ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16"]
    assert prime["seed"] == {"kind": "int", "min": 0, "max": 2147483647}
