"""Regression tests for provider failure and downloaded-artifact contracts."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


try:
    import requests as _requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = ModuleType("requests")

    class RequestException(Exception):
        pass

    requests_stub.RequestException = RequestException
    requests_stub.get = lambda *args, **kwargs: pytest.fail("unexpected HTTP GET")
    requests_stub.post = lambda *args, **kwargs: pytest.fail("unexpected HTTP POST")
    sys.modules["requests"] = requests_stub


SKILL_ROOT = Path(
    os.environ.get("SKILL25_ROOT", Path(__file__).resolve().parents[1])
)
SCRIPTS_ROOT = SKILL_ROOT / "scripts"


def load_script(name: str):
    """Load one script from the selected worktree without package side effects."""
    sys.modules.pop("ai_providers", None)
    module_name = f"skill25_{name}_{abs(hash(SCRIPTS_ROOT))}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_fake_moviepy(monkeypatch: pytest.MonkeyPatch):
    """Install the minimal MoviePy surface needed to detect local dispatch."""

    class FakeClip:
        def set_duration(self, duration):
            return self

        def write_videofile(self, output, **kwargs):
            Path(output).write_bytes(b"explicit local artifact")

        def close(self):
            return None

    moviepy = ModuleType("moviepy")
    editor = ModuleType("moviepy.editor")
    editor.ImageClip = lambda path: FakeClip()
    editor.TextClip = object
    editor.CompositeVideoClip = object
    editor.AudioFileClip = object

    video = ModuleType("moviepy.video")
    video_fx = ModuleType("moviepy.video.fx")
    video_fx_all = ModuleType("moviepy.video.fx.all")
    video_fx_all.resize = lambda clip, *args, **kwargs: clip
    video_fx_all.scroll = lambda clip, *args, **kwargs: clip

    audio = ModuleType("moviepy.audio")
    audio_fx = ModuleType("moviepy.audio.fx")
    audio_fx_all = ModuleType("moviepy.audio.fx.all")
    audio_fx_all.audio_fadein = lambda clip, *args, **kwargs: clip
    audio_fx_all.audio_fadeout = lambda clip, *args, **kwargs: clip
    audio_fx_all.volumex = lambda clip, *args, **kwargs: clip

    for name, fake_module in {
        "numpy": ModuleType("numpy"),
        "moviepy": moviepy,
        "moviepy.editor": editor,
        "moviepy.video": video,
        "moviepy.video.fx": video_fx,
        "moviepy.video.fx.all": video_fx_all,
        "moviepy.audio": audio,
        "moviepy.audio.fx": audio_fx,
        "moviepy.audio.fx.all": audio_fx_all,
    }.items():
        monkeypatch.setitem(sys.modules, name, fake_module)

    return FakeClip


@pytest.mark.parametrize("provider", ["kieai", "runway", "pika"])
def test_real_provider_failure_never_returns_placeholder_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    module = load_script("text_to_video")
    placeholder_called = False

    class FailingProvider:
        def __init__(self, provider_name, config):
            assert provider_name == provider

        def generate_video(self, **kwargs):
            raise RuntimeError("provider request failed")

    def forbidden_placeholder(*args, **kwargs):
        nonlocal placeholder_called
        placeholder_called = True
        return str(tmp_path / "placeholder.mp4")

    monkeypatch.setattr(module, "AIProvider", FailingProvider)
    monkeypatch.setattr(
        module, "create_placeholder_video", forbidden_placeholder, raising=False
    )

    with pytest.raises(RuntimeError, match=rf"{provider}.*provider request failed"):
        module.text_to_video(
            "a requested real generation",
            provider=provider,
            output=tmp_path / "result.mp4",
        )

    assert placeholder_called is False


def test_explicit_mock_provider_remains_supported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("text_to_video")
    output = tmp_path / "mock.mp4"

    class MockProvider:
        def __init__(self, provider_name, config):
            assert provider_name == "mock"

        def generate_video(self, **kwargs):
            kwargs["output"].write_bytes(b"explicit mock artifact")
            return kwargs["output"]

    monkeypatch.setattr(module, "AIProvider", MockProvider)
    monkeypatch.setattr(
        module,
        "create_placeholder_video",
        lambda *args, **kwargs: pytest.fail("successful mock generation must not fall back"),
        raising=False,
    )

    result = module.text_to_video("mock request", provider="mock", output=output)

    assert Path(result) == output
    assert output.read_bytes() == b"explicit mock artifact"


@pytest.mark.parametrize("provider", ["runway", "pika", "mock"])
@pytest.mark.parametrize(
    ("option", "value"),
    [("seed", 42), ("negative_prompt", "unwanted artifact")],
)
def test_provider_rejects_explicit_unsupported_generation_options_before_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    option: str,
    value,
) -> None:
    module = load_script("ai_providers")
    config = {provider: {"api_key": "test-only"}}
    ai = module.AIProvider(provider, config)
    method_name = {
        "runway": "_generate_runway",
        "pika": "_generate_pika",
        "mock": "_generate_mock",
    }[provider]
    generator_called = False

    def generator(*args, **kwargs):
        nonlocal generator_called
        generator_called = True
        return tmp_path / "unexpected.mp4"

    monkeypatch.setattr(ai, method_name, generator)

    with pytest.raises(ValueError, match=rf"{provider}.*--{option.replace('_', '-')}"):
        ai.generate_video(
            "provider-specific request",
            output=tmp_path / "result.mp4",
            **{option: value},
        )

    assert generator_called is False


def test_mock_provider_allows_absent_optional_generation_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("ai_providers")
    ai = module.AIProvider("mock", {})
    output = tmp_path / "mock.mp4"
    monkeypatch.setattr(ai, "_generate_mock", lambda *args, **kwargs: output)

    result = ai.generate_video(
        "ordinary mock request",
        output=output,
        seed=None,
        negative_prompt=None,
    )

    assert result == output


def test_real_provider_cli_returns_nonzero_without_ready_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    module = load_script("text_to_video")

    class FailingProvider:
        def __init__(self, provider_name, config):
            assert provider_name == "kieai"

        def generate_video(self, **kwargs):
            raise RuntimeError("provider request failed")

    monkeypatch.setattr(module, "AIProvider", FailingProvider)
    monkeypatch.setattr(
        module,
        "create_placeholder_video",
        lambda *args, **kwargs: str(tmp_path / "placeholder.mp4"),
        raising=False,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "text_to_video.py",
            "real provider request",
            "--provider",
            "kieai",
            "--output",
            str(tmp_path / "result.mp4"),
        ],
    )

    assert module.main() != 0
    output = capsys.readouterr().out
    assert "provider request failed" in output
    assert "Video ready" not in output


class FakeDownloadResponse:
    def __init__(self, body: bytes, content_type: str):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        assert chunk_size > 0
        if self.body:
            yield self.body


@pytest.mark.parametrize(
    ("body", "content_type", "probe_returncode"),
    [
        (b"", "video/mp4", 0),
        (b"<html>provider error</html>", "text/html", 0),
        (b"not-video" * 256, "video/mp4", 1),
    ],
    ids=["empty", "html", "undecodable"],
)
def test_download_rejects_empty_html_and_nonvideo_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    body: bytes,
    content_type: str,
    probe_returncode: int,
) -> None:
    module = load_script("ai_providers")
    output = tmp_path / "result.mp4"
    output.write_bytes(b"existing-good-output")

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FakeDownloadResponse(body, content_type),
    )
    monkeypatch.setattr(
        module,
        "subprocess",
        SimpleNamespace(
            run=lambda *args, **kwargs: SimpleNamespace(
                returncode=probe_returncode,
                stdout=json.dumps(
                    {"streams": [{"codec_type": "video"}], "format": {"duration": "2.0"}}
                ),
                stderr="invalid video",
            )
        ),
        raising=False,
    )

    provider = module.AIProvider("kieai", {"kieai": {"api_key": "test-only"}})
    with pytest.raises(RuntimeError, match="downloaded video"):
        provider._download_video("https://provider.invalid/result", output)

    assert output.read_bytes() == b"existing-good-output"
    assert not list(tmp_path.glob("*.part"))


def test_download_accepts_only_probe_verified_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("ai_providers")
    output = tmp_path / "result.mp4"
    payload = b"verified-video-data" * 128
    probe_calls = []

    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FakeDownloadResponse(payload, "video/mp4; charset=binary"),
    )

    def successful_probe(command, **kwargs):
        probe_calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"streams": [{"codec_type": "video"}], "format": {"duration": "1.25"}}
            ),
            stderr="",
        )

    monkeypatch.setattr(
        module,
        "subprocess",
        SimpleNamespace(run=successful_probe),
        raising=False,
    )

    provider = module.AIProvider("kieai", {"kieai": {"api_key": "test-only"}})
    result = provider._download_video("https://provider.invalid/result", output)

    assert result == output
    assert output.read_bytes() == payload
    assert len(probe_calls) == 1
    assert probe_calls[0][1]["timeout"] <= 30


def test_download_accepts_real_decodable_positive_duration_video(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("ai_providers")
    fixture = tmp_path / "fixture.mp4"
    output = tmp_path / "result.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.5",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(fixture),
        ],
        check=True,
        timeout=30,
    )
    payload = fixture.read_bytes()
    assert len(payload) >= 1024
    monkeypatch.setattr(
        module.requests,
        "get",
        lambda *args, **kwargs: FakeDownloadResponse(payload, "video/mp4"),
    )

    provider = module.AIProvider("kieai", {"kieai": {"api_key": "test-only"}})
    result = provider._download_video("https://provider.invalid/result", output)

    assert result == output
    assert output.read_bytes() == payload


@pytest.mark.parametrize("provider", ["kieai", "runway", "pika"])
def test_nonlocal_image_failures_do_not_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    module = load_script("image_to_video")
    install_fake_moviepy(monkeypatch)
    image = tmp_path / "source.png"
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\x00"
        b"\x00\x03\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    class FailingProvider:
        def __init__(self, provider_name, config):
            assert provider_name == provider

        def image_to_video(self, **kwargs):
            raise RuntimeError("provider image generation failed")

    monkeypatch.setattr(module, "AIProvider", FailingProvider)
    monkeypatch.setattr(
        module,
        "apply_ken_burns",
        lambda *args, **kwargs: pytest.fail("non-local failure invoked local renderer"),
    )

    with pytest.raises(RuntimeError, match="provider image generation failed"):
        module.image_to_video(
            image,
            output=tmp_path / "result.mp4",
            provider=provider,
        )


def test_explicit_local_image_mode_remains_supported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("image_to_video")
    install_fake_moviepy(monkeypatch)
    image = tmp_path / "source.png"
    image.write_bytes(b"test image contents")
    output = tmp_path / "local.mp4"

    class ForbiddenProvider:
        def __init__(self, *args, **kwargs):
            pytest.fail("explicit local mode invoked an AI provider")

    monkeypatch.setattr(module, "AIProvider", ForbiddenProvider)

    result = module.image_to_video(
        image,
        output=output,
        motion="none",
        provider="local",
        duration=1,
    )

    assert result == output
    assert output.read_bytes() == b"explicit local artifact"


@pytest.mark.parametrize("provider", ["heygen", "synthesia", "d-id"])
def test_nonlocal_avatar_failures_do_not_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    module = load_script("avatar_video")

    monkeypatch.setattr(
        module,
        "_generate_with_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("provider avatar generation failed")
        ),
    )
    monkeypatch.setattr(
        module,
        "_generate_local",
        lambda *args, **kwargs: pytest.fail("non-local failure invoked local renderer"),
    )

    with pytest.raises(RuntimeError, match="provider avatar generation failed"):
        module.avatar_video(
            script_text="Presenter script",
            output=tmp_path / "result.mp4",
            provider=provider,
        )


def test_explicit_local_avatar_mode_remains_supported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    output = tmp_path / "local.mp4"

    monkeypatch.setattr(
        module,
        "_generate_with_provider",
        lambda *args, **kwargs: pytest.fail("local mode invoked a provider"),
    )
    monkeypatch.setattr(module, "_generate_local", lambda *args, **kwargs: output)

    result = module.avatar_video(
        script_text="Local presentation",
        output=output,
        provider="local",
    )

    assert result == output


def test_local_avatar_voice_request_fails_instead_of_silent_omit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    monkeypatch.setattr(
        module,
        "_generate_local",
        lambda *args, **kwargs: pytest.fail("requested voice was silently omitted"),
    )

    with pytest.raises(NotImplementedError, match="voice synthesis is not implemented"):
        module.avatar_video(
            script_text="Narrated local presentation",
            voice_id="requested-voice",
            output=tmp_path / "local.mp4",
            provider="local",
        )


def test_local_avatar_missing_custom_background_fails_instead_of_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    missing_background = tmp_path / "missing-background.png"
    monkeypatch.setattr(
        module,
        "_generate_local",
        lambda *args, **kwargs: pytest.fail("missing background was silently substituted"),
    )

    with pytest.raises(FileNotFoundError, match="Custom background image not found"):
        module.avatar_video(
            script_text="Local presentation",
            background="custom",
            background_path=missing_background,
            output=tmp_path / "local.mp4",
            provider="local",
        )


def test_local_avatar_custom_background_requires_a_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    monkeypatch.setattr(
        module,
        "_generate_local",
        lambda *args, **kwargs: pytest.fail("custom background used a generic color"),
    )

    with pytest.raises(ValueError, match="Custom background requires --background-image"):
        module.avatar_video(
            script_text="Local presentation",
            background="custom",
            output=tmp_path / "local.mp4",
            provider="local",
        )


def test_avatar_function_rejects_script_path_and_text_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    script = tmp_path / "script.txt"
    script.write_text("File version")
    monkeypatch.setattr(
        module,
        "_generate_local",
        lambda *args, **kwargs: pytest.fail("one script input was silently ignored"),
    )

    with pytest.raises(ValueError, match="exactly one of script_path or script_text"):
        module.avatar_video(
            script_path=script,
            script_text="Inline version",
            output=tmp_path / "local.mp4",
            provider="local",
        )


def test_avatar_cli_rejects_script_and_text_together(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = load_script("avatar_video")
    script = tmp_path / "script.txt"
    script.write_text("File version")
    monkeypatch.setattr(module, "avatar_video", lambda **kwargs: tmp_path / "result.mp4")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "avatar_video.py",
            "--script",
            str(script),
            "--text",
            "Inline version",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 2


def test_avatar_cli_still_requires_one_script_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    module = load_script("avatar_video")
    monkeypatch.setattr(sys, "argv", ["avatar_video.py"])

    assert module.main() == 1
    assert "provide --script or --text" in capsys.readouterr().out
