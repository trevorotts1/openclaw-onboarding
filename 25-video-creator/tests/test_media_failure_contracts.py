import sys
import types

import pytest


class FakeClip:
    duration = 2.0
    w = 1920
    h = 1080
    fps = 30

    def __init__(self, audio=None):
        self.audio = audio

    def resize(self, **_kwargs):
        return self

    def close(self):
        pass

    def fadeout(self, _duration):
        return self

    def fadein(self, _duration):
        return self

    def set_audio(self, audio):
        return FakeClip(audio=audio)

    def write_videofile(self, *_args, **_kwargs):
        pass


def install_fake_moviepy(monkeypatch, loader=None):
    editor = types.ModuleType("moviepy.editor")
    editor.VideoFileClip = loader or (lambda _path: FakeClip())
    editor.AudioFileClip = lambda _path: FakeClip()
    editor.CompositeAudioClip = lambda tracks: FakeClip(audio=tracks)
    editor.concatenate_audioclips = lambda tracks: FakeClip(audio=tracks)
    editor.concatenate_videoclips = lambda clips, **_kwargs: FakeClip()

    video_fx = types.ModuleType("moviepy.video.fx.all")
    video_fx.fadein = lambda clip, _duration: clip
    video_fx.fadeout = lambda clip, _duration: clip
    audio_fx = types.ModuleType("moviepy.audio.fx.all")
    audio_fx.audio_fadein = object()
    audio_fx.audio_fadeout = object()
    audio_fx.volumex = object()

    modules = {
        "moviepy": types.ModuleType("moviepy"),
        "moviepy.editor": editor,
        "moviepy.video": types.ModuleType("moviepy.video"),
        "moviepy.video.fx": types.ModuleType("moviepy.video.fx"),
        "moviepy.video.fx.all": video_fx,
        "moviepy.audio": types.ModuleType("moviepy.audio"),
        "moviepy.audio.fx": types.ModuleType("moviepy.audio.fx"),
        "moviepy.audio.fx.all": audio_fx,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_requested_clip_failure_prevents_ready_assembly(load_script, monkeypatch, tmp_path):
    install_fake_moviepy(monkeypatch)
    module = load_script("multi_clip_assembly")
    valid = tmp_path / "valid.mp4"
    valid.touch()
    missing = tmp_path / "missing.mp4"

    with pytest.raises(RuntimeError, match="missing.mp4"):
        module.assemble_clips([valid, missing], output=tmp_path / "out.mp4")


def test_assembly_requires_requested_music_file(load_script, tmp_path):
    module = load_script("multi_clip_assembly")
    video = tmp_path / "video.mp4"
    video.touch()

    with pytest.raises(FileNotFoundError, match="missing-music.mp3"):
        module.assemble_clips(
            [video], music=str(tmp_path / "missing-music.mp3"), output=tmp_path / "out.mp4"
        )


@pytest.mark.parametrize(
    "audio_request",
    [
        {"music_source": "missing-music.mp3"},
        {"voiceover": "missing-voice.mp3"},
        {"genre": "calm"},
    ],
)
def test_every_requested_audio_source_must_attach(
    load_script, monkeypatch, tmp_path, audio_request
):
    install_fake_moviepy(monkeypatch)
    module = load_script("add_music")
    video = tmp_path / "video.mp4"
    video.touch()
    kwargs = dict(audio_request)
    if "music_source" in kwargs:
        kwargs["music_source"] = str(tmp_path / kwargs["music_source"])
    if "voiceover" in kwargs:
        kwargs["voiceover"] = tmp_path / kwargs["voiceover"]

    with pytest.raises((FileNotFoundError, RuntimeError)):
        module.add_music(video, output=tmp_path / "out.mp4", **kwargs)


def test_mixed_batch_export_returns_nonzero(load_script, monkeypatch, tmp_path, capsys):
    module = load_script("export")
    monkeypatch.setattr(
        module,
        "batch_export",
        lambda *_args, **_kwargs: [
            ("ok.mp4", True, tmp_path / "ok-out.mp4"),
            ("bad.mp4", False, "decode failed"),
        ],
    )
    monkeypatch.setattr(sys, "argv", ["export.py", str(tmp_path), "--batch"])

    assert module.main() != 0
    output = capsys.readouterr().out
    assert "1 succeeded, 1 failed" in output


def test_all_successful_batch_export_returns_zero(load_script, monkeypatch, tmp_path):
    module = load_script("export")
    monkeypatch.setattr(
        module,
        "batch_export",
        lambda *_args, **_kwargs: [("ok.mp4", True, tmp_path / "ok-out.mp4")],
    )
    monkeypatch.setattr(sys, "argv", ["export.py", str(tmp_path), "--batch"])

    assert module.main() == 0


def test_empty_batch_export_returns_nonzero(load_script, monkeypatch, tmp_path, capsys):
    module = load_script("export")
    monkeypatch.setattr(module, "batch_export", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(sys, "argv", ["export.py", str(tmp_path), "--batch"])

    assert module.main() != 0
    assert "no input files matched" in capsys.readouterr().out


def test_batch_rejects_discarded_global_output(load_script, monkeypatch, tmp_path, capsys):
    module = load_script("export")
    monkeypatch.setattr(
        module,
        "batch_export",
        lambda *_args, **_kwargs: [("ok.mp4", True, tmp_path / "ok-out.mp4")],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["export.py", str(tmp_path), "--batch", "--output", str(tmp_path / "ignored.mp4")],
    )

    assert module.main() != 0
    assert "--output cannot be used with --batch" in capsys.readouterr().out


def test_batch_rejects_file_input(load_script, monkeypatch, tmp_path, capsys):
    module = load_script("export")
    video = tmp_path / "video.mp4"
    video.touch()
    monkeypatch.setattr(
        module,
        "export_video",
        lambda *_args, **_kwargs: pytest.fail("single export must not run in batch mode"),
    )
    monkeypatch.setattr(sys, "argv", ["export.py", str(video), "--batch"])

    assert module.main() != 0
    assert "--batch requires a directory input" in capsys.readouterr().out


def test_music_and_genre_are_mutually_exclusive_in_function(
    load_script, monkeypatch, tmp_path
):
    install_fake_moviepy(monkeypatch)
    module = load_script("add_music")
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.touch()
    music.touch()

    with pytest.raises(ValueError, match="either music_source or genre"):
        module.add_music(video, music_source=str(music), genre="calm")


def test_music_and_genre_are_mutually_exclusive_in_cli(
    load_script, monkeypatch, tmp_path
):
    module = load_script("add_music")
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.touch()
    music.touch()
    monkeypatch.setattr(module, "add_music", lambda *_args, **_kwargs: tmp_path / "out.mp4")
    monkeypatch.setattr(
        sys,
        "argv",
        ["add_music.py", str(video), "--music", str(music), "--genre", "calm"],
    )

    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code != 0
