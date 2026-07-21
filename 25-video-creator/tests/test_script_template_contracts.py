import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest


SKILL_ROOT = Path(
    os.environ.get("SKILL25_ROOT", Path(__file__).resolve().parents[1])
)
SCRIPTS = SKILL_ROOT / "scripts"


def _load_script(module_name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    if "requests" not in sys.modules:
        sys.modules["requests"] = types.SimpleNamespace(RequestException=Exception)
    if module_name == "template_video":
        dependency_exports = {
            "text_to_video": "text_to_video",
            "image_to_video": "image_to_video",
            "multi_clip_assembly": "assemble_clips",
            "add_music": "add_music",
        }
        for dependency, export in dependency_exports.items():
            stub = types.ModuleType(dependency)
            setattr(stub, export, lambda *args, **kwargs: None)
            sys.modules[dependency] = stub
    unique_name = f"skill25_{module_name}_{abs(hash(str(SKILL_ROOT)))}"
    spec = importlib.util.spec_from_file_location(
        unique_name, SCRIPTS / f"{module_name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stub_moviepy(monkeypatch, **members):
    moviepy = types.ModuleType("moviepy")
    editor = types.ModuleType("moviepy.editor")
    defaults = {
        "AudioFileClip": object,
        "ColorClip": object,
        "CompositeAudioClip": object,
        "CompositeVideoClip": object,
        "TextClip": object,
        "VideoFileClip": object,
        "concatenate_videoclips": object,
    }
    defaults.update(members)
    for name, value in defaults.items():
        setattr(editor, name, value)
    monkeypatch.setitem(sys.modules, "moviepy", moviepy)
    monkeypatch.setitem(sys.modules, "moviepy.editor", editor)


def test_failed_scene_prevents_complete_success(tmp_path, monkeypatch):
    module = _load_script("script_to_video")
    script = tmp_path / "two-scenes.txt"
    script.write_text(
        "\nSCENE 1: [first]\nDURATION: 1s\n"
        "\nSCENE 2: [second]\nDURATION: 1s\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "generate_scene_clip",
        lambda scene, provider, quality: (
            tmp_path / "scene-1.mp4" if scene.number == 1 else None
        ),
    )
    monkeypatch.setattr(
        module, "assemble_clips", lambda paths, scenes, output, quality: output
    )

    with pytest.raises(RuntimeError, match=r"scene\(s\): 2"):
        module.script_to_video(script, output=tmp_path / "result.mp4", provider="local")


def test_real_scene_provider_failure_does_not_fall_back(tmp_path, monkeypatch):
    module = _load_script("script_to_video")
    _stub_moviepy(monkeypatch)

    class FailingProvider:
        def __init__(self, provider, config):
            pass

        def generate_video(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(module, "AIProvider", FailingProvider)
    monkeypatch.setattr(module, "load_config", lambda: {})
    scene = module.Scene(number=7, visual="required visual", duration=1)

    with pytest.raises(
        RuntimeError, match=r"Scene 7 generation with provider 'kieai' failed"
    ):
        module.generate_scene_clip(scene, "kieai", "web")


def test_real_scene_provider_requires_visual_instead_of_using_local_fallback(
    monkeypatch,
):
    module = _load_script("script_to_video")
    _stub_moviepy(monkeypatch)
    scene = module.Scene(number=8, visual="", text="Local substitute", duration=1)

    with pytest.raises(
        ValueError,
        match=r"Scene 8 requires a non-empty visual prompt for provider 'runway'",
    ):
        module.generate_scene_clip(scene, "runway", "web")


def test_voiceover_and_bgm_are_rejected_before_rendering(tmp_path, monkeypatch):
    module = _load_script("script_to_video")
    script = tmp_path / "audio-directives.txt"
    script.write_text(
        "\nSCENE 1: [first]\n"
        "VOICEOVER: This narration is required.\n"
        "BGM: required-track.mp3\n"
        "DURATION: 1s\n",
        encoding="utf-8",
    )
    called = []
    monkeypatch.setattr(
        module,
        "generate_scene_clip",
        lambda *args, **kwargs: called.append(True),
    )

    with pytest.raises(ValueError, match=r"VOICEOVER.*BGM"):
        module.script_to_video(script, output=tmp_path / "result.mp4", provider="local")
    assert called == []


@pytest.mark.parametrize("directive", ["TRANSITION: slide_left", "IMAGE: still.png"])
def test_unimplemented_scene_directives_fail_during_parsing(tmp_path, directive):
    module = _load_script("script_to_video")
    script = tmp_path / "unsupported-directive.txt"
    script.write_text(
        f"\nSCENE 1: [first]\n{directive}\nDURATION: 1s\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=directive.split(":", 1)[0]):
        module.ScriptParser(script).parse()


def test_unknown_scene_directive_fails_during_parsing(tmp_path):
    module = _load_script("script_to_video")
    script = tmp_path / "unknown-directive.txt"
    script.write_text(
        "\nSCENE 1: [first]\nVISUAL: ignored prompt\nDURATION: 1s\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Unsupported directive.*VISUAL"):
        module.ScriptParser(script).parse()


def test_real_provider_rejects_unapplied_text_overlay(monkeypatch):
    module = _load_script("script_to_video")
    _stub_moviepy(monkeypatch)
    provider_calls = []

    class FakeProvider:
        def __init__(self, provider, config):
            provider_calls.append(provider)

    monkeypatch.setattr(module, "AIProvider", FakeProvider)
    scene = module.Scene(
        number=4,
        visual="required visual prompt",
        text="Required overlay",
        duration=1,
    )

    with pytest.raises(ValueError, match=r"TEXT overlay.*'kieai' cannot apply"):
        module.generate_scene_clip(scene, "kieai", "web")
    assert provider_calls == []


def test_explicit_mock_and_local_render_requested_text(tmp_path, monkeypatch):
    module = _load_script("script_to_video")
    rendered_text = []

    class FakeClip:
        def set_duration(self, duration):
            return self

        def set_position(self, position):
            return self

        def write_videofile(self, *args, **kwargs):
            return None

        def close(self):
            return None

    _stub_moviepy(
        monkeypatch,
        ColorClip=lambda *args, **kwargs: FakeClip(),
        TextClip=lambda text, *args, **kwargs: (
            rendered_text.append(text) or FakeClip()
        ),
        CompositeVideoClip=lambda clips: FakeClip(),
    )
    monkeypatch.chdir(tmp_path)
    scene = module.Scene(
        number=5,
        visual="visual prompt",
        text="Required overlay",
        duration=1,
    )

    for provider in ("local", "mock"):
        rendered_text.clear()
        assert module.generate_scene_clip(scene, provider, "web") == Path(
            "temp_scene_5.mp4"
        )
        assert "Required overlay" in rendered_text


@pytest.mark.parametrize("option", ["--template", "--chapters"])
def test_unsupported_script_cli_flags_are_rejected(tmp_path, option, monkeypatch, capsys):
    module = _load_script("script_to_video")
    script = tmp_path / "script.txt"
    script.write_text("\nSCENE 1: [visual]\nDURATION: 1s\n", encoding="utf-8")
    argv = ["script_to_video.py", str(script), option]
    if option == "--template":
        argv.append("product_showcase")
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        module.main()
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "unrecognized arguments" in captured.err
    assert "Video ready" not in captured.out


def test_unsupported_script_python_options_fail_before_parsing(tmp_path):
    module = _load_script("script_to_video")

    with pytest.raises(ValueError, match="templates are not supported"):
        module.script_to_video(tmp_path / "missing.txt", template="product_showcase")
    with pytest.raises(ValueError, match="Chapter marker generation is not supported"):
        module.script_to_video(tmp_path / "missing.txt", chapters=True)


@pytest.mark.parametrize(
    ("template_name", "required_field"),
    [
        ("product_showcase", "product_name"),
        ("social_post", "headline"),
        ("tutorial", "title"),
        ("testimonial", "quote"),
        ("podcast_clip", "audio_file"),
        ("event_promo", "event_name"),
        ("announcement", "title"),
    ],
)
def test_templates_reject_missing_required_client_data(template_name, required_field):
    module = _load_script("template_video")
    engine = module.TemplateEngine(template_name, {})

    with pytest.raises(ValueError, match=required_field):
        engine._validate_data()


def test_template_validation_runs_before_rendering(monkeypatch):
    module = _load_script("template_video")
    engine = module.TemplateEngine("product_showcase", {})
    rendered = []
    monkeypatch.setattr(
        engine, "_product_showcase", lambda: rendered.append(True) or Path("video.mp4")
    )

    with pytest.raises(ValueError, match="product_name"):
        engine.generate()
    assert rendered == []


def test_product_template_rejects_missing_required_images(tmp_path):
    module = _load_script("template_video")
    missing_image = tmp_path / "missing.png"
    engine = module.TemplateEngine(
        "product_showcase",
        {
            "product_name": "Example",
            "images": [str(missing_image)],
            "features": ["One feature"],
        },
    )

    with pytest.raises(ValueError, match="image file.*not found"):
        engine._validate_data()


def test_template_rejects_missing_requested_music(tmp_path):
    module = _load_script("template_video")
    engine = module.TemplateEngine(
        "social_post",
        {"headline": "Example", "music": str(tmp_path / "missing.mp3")},
    )

    with pytest.raises(ValueError, match="music file not found"):
        engine._validate_data()


def test_template_rejects_fields_it_cannot_render():
    module = _load_script("template_video")
    engine = module.TemplateEngine(
        "social_post",
        {"headline": "Example", "text_animations": ["bounce"]},
    )

    with pytest.raises(ValueError, match=r"Unsupported field.*text_animations"):
        engine._validate_data()


def test_event_template_consumes_required_description(tmp_path, monkeypatch):
    module = _load_script("template_video")
    rendered_text = []

    class FakeFinal:
        def write_videofile(self, *args, **kwargs):
            return None

        def close(self):
            return None

    _stub_moviepy(
        monkeypatch,
        concatenate_videoclips=lambda clips, method: FakeFinal(),
    )
    engine = module.TemplateEngine(
        "event_promo",
        {
            "event_name": "Launch",
            "date": "2030-01-01",
            "location": "Main Hall",
            "description": "A required description that must reach the render graph",
        },
    )
    engine.output = tmp_path / "event.mp4"
    monkeypatch.setattr(
        engine,
        "_create_text_slide",
        lambda text, duration, bg_color: rendered_text.append(text) or object(),
    )

    engine._event_promo()

    assert "A required description that must reach the render graph" in rendered_text


def test_product_template_does_not_fabricate_default_cta(tmp_path, monkeypatch):
    module = _load_script("template_video")
    rendered_text = []
    image_path = tmp_path / "product.png"
    image_path.write_bytes(b"fixture")

    class FakeClip:
        def set_duration(self, duration):
            return self

        def resize(self, **kwargs):
            return self

        def write_videofile(self, *args, **kwargs):
            return None

        def close(self):
            return None

    _stub_moviepy(
        monkeypatch,
        ImageClip=lambda path: FakeClip(),
        concatenate_videoclips=lambda clips, method: FakeClip(),
    )
    engine = module.TemplateEngine(
        "product_showcase",
        {
            "product_name": "Example",
            "images": [str(image_path)],
            "features": ["One feature"],
        },
    )
    engine.output = tmp_path / "product.mp4"
    monkeypatch.setattr(
        engine,
        "_create_text_slide",
        lambda text, duration, bg_color=(40, 40, 50): (
            rendered_text.append(text) or FakeClip()
        ),
    )

    engine._product_showcase()

    assert all("Learn More" not in text for text in rendered_text)
    assert len(rendered_text) == 2


def test_template_cli_passes_requested_output_to_engine(tmp_path, monkeypatch):
    module = _load_script("template_video")
    requested = tmp_path / "custom" / "requested.mp4"
    captured = {}

    class FakeEngine:
        def __init__(self, template_name, data, output=None):
            captured["template"] = template_name
            captured["output"] = output

        def generate(self):
            return requested

    monkeypatch.setattr(module, "TemplateEngine", FakeEngine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "template_video.py",
            "social_post",
            "--json",
            '{"headline": "Example"}',
            "--output",
            str(requested),
        ],
    )

    assert module.main() == 0
    assert captured == {"template": "social_post", "output": requested}


def test_template_cli_rejects_multiple_data_sources(tmp_path, monkeypatch, capsys):
    module = _load_script("template_video")
    data_file = tmp_path / "template.json"
    data_file.write_text('{"headline": "from file"}', encoding="utf-8")
    rendered = []

    class FakeEngine:
        def __init__(self, *args, **kwargs):
            rendered.append("constructed")

        def generate(self):
            rendered.append("rendered")
            return tmp_path / "video.mp4"

    monkeypatch.setattr(module, "TemplateEngine", FakeEngine)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "template_video.py",
            "social_post",
            "--data",
            str(data_file),
            "--json",
            '{"headline": "from json"}',
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        module.main()
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "not allowed with argument" in captured.err
    assert "Video ready" not in captured.out
    assert rendered == []


@pytest.mark.parametrize(
    ("quality", "provider_resolution"),
    [
        ("social", "1080p"),
        ("web", "1080p"),
        ("broadcast", "1080p"),
        ("cinema", "4k"),
    ],
)
def test_quality_presets_use_provider_resolution_vocabulary(
    quality, provider_resolution, tmp_path, monkeypatch
):
    module = _load_script("script_to_video")
    _stub_moviepy(monkeypatch)
    captured = {}

    class FakeProvider:
        def __init__(self, provider, config):
            pass

        def generate_video(self, **kwargs):
            captured.update(kwargs)
            return tmp_path / "scene.mp4"

    monkeypatch.setattr(module, "AIProvider", FakeProvider)
    monkeypatch.setattr(module, "load_config", lambda: {})
    scene = module.Scene(number=1, visual="required visual", duration=1)

    assert module.generate_scene_clip(scene, "kieai", quality) == tmp_path / "scene.mp4"
    assert captured["resolution"] == provider_resolution


def test_assembly_normalizes_and_verifies_requested_dimensions(tmp_path, monkeypatch):
    module = _load_script("script_to_video")
    concatenated_sizes = []
    verified = []

    class FakeClip:
        def __init__(self, size=(640, 480), duration=1):
            self.size = size
            self.duration = duration

        def resize(self, size):
            return FakeClip(tuple(size), self.duration)

        def set_position(self, position):
            return self

        def set_duration(self, duration):
            self.duration = duration
            return self

    class FakeFinal(FakeClip):
        def write_videofile(self, *args, **kwargs):
            return None

        def close(self):
            return None

    def concatenate(clips, method):
        concatenated_sizes.extend(clip.size for clip in clips)
        return FakeFinal(clips[0].size)

    _stub_moviepy(
        monkeypatch,
        VideoFileClip=lambda path: FakeClip(),
        ColorClip=lambda size, color: FakeClip(tuple(size)),
        CompositeVideoClip=lambda clips, size=None: FakeClip(tuple(size)),
        concatenate_videoclips=concatenate,
    )
    monkeypatch.setattr(
        module,
        "_verify_video_dimensions",
        lambda output, expected: verified.append((output, expected)),
        raising=False,
    )
    output = tmp_path / "social.mp4"

    module.assemble_clips(
        [tmp_path / "scene.mp4"], [module.Scene(number=1)], output, "social"
    )

    assert concatenated_sizes == [(1080, 1920)]
    assert verified == [(output, (1080, 1920))]
