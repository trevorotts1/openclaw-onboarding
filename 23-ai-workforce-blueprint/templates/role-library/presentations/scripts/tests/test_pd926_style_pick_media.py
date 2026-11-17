"""PD-926 (FL05 engine reporting) -- the style-pick message carries the actual
style-sample images under a count cap and a size cap, and never names a path
the recipient cannot open.

Trevor's answer (option (a), 5:49 PM Eastern 2026-11-13) is the requirement:
the images ride the style-pick message ONLY, the transport enforces the caps,
and the text carries no filesystem path once the images are attached.

The proof this file pins:
  1. select_style_pick_media() drops an image over the count cap, the
     per-image cap or the total cap and reports every drop.
  2. strip_style_sample_paths() removes the sample paths from PD-042's real
     message shape and leaves answerable prose behind.
  3. End to end through the script: two images reach the gateway as two
     --media flags, the text has no path, a send whose images all fail the
     caps is REFUSED (exit 6, gateway not called), and a payload without the
     style-pick field is byte-identical to before (other 21 call sites).
"""
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
NOTIFY = SCRIPTS / "presentation-notify.py"

CHAT_ID = "8505558285"
MIB = 1024 * 1024
PICK_MESSAGE = (
    "Style A — clean editorial white with a warm accent\n"
    "Your 3 style samples are ready: working/style-preview/variant-A-slide-01.png, "
    "working/style-preview/variant-A-slide-02.png, "
    "working/style-preview/variant-A-slide-03.png.\n"
    "Reply A, B or C to pick the look for your whole presentation. "
    "I will wait for you."
)


def _load_notify_module():
    spec = importlib.util.spec_from_file_location("presentation_notify_pd926",
                                                  str(NOTIFY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _png(directory: Path, name: str, size: int = 8) -> Path:
    p = directory / name
    with open(p, "wb") as fh:
        fh.truncate(size)          # sparse: instant, exact size on APFS
    return p


def _fake_gateway(bin_dir: Path, record: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    cli = bin_dir / "openclaw"
    cli.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\0" "$@" > "{record}"\n'
        'echo \'{"message_id": "pd926"}\'\n')
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _run(payload, tmp_path, env_extra=None):
    record = tmp_path / "gateway-argv.txt"
    _fake_gateway(tmp_path / "bin", record)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PRESENTATION_NOTIFY_")}
    env.update({"PATH": f"{tmp_path / 'bin'}{os.pathsep}{env.get('PATH', '')}",
                "HOME": str(tmp_path)})
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, str(NOTIFY)],
                       input=json.dumps(payload), text=True,
                       capture_output=True, timeout=120, env=env)
    argv = (record.read_bytes().decode().split("\0")
            if record.exists() else [])
    if argv and argv[-1] == "":
        argv.pop()
    return r, argv


# --------------------------------------------------------------------------
# 1. the caps
# --------------------------------------------------------------------------

class TestStylePickCaps:
    def test_count_cap_ten_images(self, tmp_path):
        T = _load_notify_module()
        paths = [_png(tmp_path, f"s{i}.png") for i in range(12)]
        attached, rejected = T.select_style_pick_media([str(p) for p in paths])
        assert len(attached) == 10
        assert len(rejected) == 2
        assert all("10-image cap" in why for _, why in rejected)

    def test_per_image_cap_ten_mib(self, tmp_path):
        T = _load_notify_module()
        big = _png(tmp_path, "big.png", 10 * MIB + 1)
        small = _png(tmp_path, "small.png")
        attached, rejected = T.select_style_pick_media([str(big), str(small)])
        assert attached == [str(small)]
        assert rejected[0][1].endswith("per-image cap")

    def test_total_cap_twenty_mib(self, tmp_path):
        T = _load_notify_module()
        paths = [_png(tmp_path, f"t{i}.png", 8 * MIB) for i in range(3)]
        attached, rejected = T.select_style_pick_media([str(p) for p in paths])
        assert len(attached) == 2              # 8 + 8 = 16 MiB fits, 24 does not
        assert rejected and "total cap" in rejected[0][1]

    def test_non_images_and_missing_files_are_dropped(self, tmp_path):
        T = _load_notify_module()
        txt = tmp_path / "notes.txt"
        txt.write_text("x")
        attached, rejected = T.select_style_pick_media(
            [str(txt), str(tmp_path / "gone.png"),
             str(_png(tmp_path, "ok.png"))])
        assert [Path(p).name for p in attached] == ["ok.png"]
        assert [why for _, why in rejected] == [
            "not an image", "not a readable regular file"]

    def test_run_dir_resolves_the_manifests_relative_paths(self, tmp_path):
        T = _load_notify_module()
        run = tmp_path / "run"
        (run / "working" / "style-preview").mkdir(parents=True)
        _png(run / "working" / "style-preview", "variant-A-slide-01.png")
        attached, rejected = T.select_style_pick_media(
            ["working/style-preview/variant-A-slide-01.png"], str(run))
        assert attached == [str(run / "working/style-preview/"
                                    "variant-A-slide-01.png")]
        assert rejected == []

    def test_a_non_list_payload_is_refused_not_guessed(self):
        T = _load_notify_module()
        attached, rejected = T.select_style_pick_media({"path": "x.png"})
        assert attached == []
        assert "not a list" in rejected[0][1]


# --------------------------------------------------------------------------
# 2. no path survives in the text
# --------------------------------------------------------------------------

class TestPathScrub:
    def test_pd042_message_shape_loses_its_paths(self):
        T = _load_notify_module()
        out = T.strip_style_sample_paths(PICK_MESSAGE)
        assert ".png" not in out
        assert "style-preview" not in out
        assert "Your 3 style samples are ready." in out
        assert "Reply A, B or C" in out
        assert "Style A — clean editorial white with a warm accent" in out

    def test_prose_without_paths_is_untouched(self):
        T = _load_notify_module()
        text = "Style B — bold. Reply A, B or C; I will wait."
        assert T.strip_style_sample_paths(text) == text


# --------------------------------------------------------------------------
# 3. end to end through the script
# --------------------------------------------------------------------------

class TestTransportEndToEnd:
    def test_two_images_reach_the_gateway_and_no_path_reaches_the_text(
            self, tmp_path):
        run = tmp_path / "run"
        (run / "working" / "style-preview").mkdir(parents=True)
        _png(run / "working" / "style-preview", "variant-A-slide-01.png")
        _png(run / "working" / "style-preview", "variant-A-slide-02.png")
        payload = {"chat_id": CHAT_ID, "kind": "ack", "message": PICK_MESSAGE,
                   "style_pick_samples":
                       ["working/style-preview/variant-A-slide-01.png",
                        "working/style-preview/variant-A-slide-02.png"],
                   "run_dir": str(run)}
        r, argv = _run(payload, tmp_path)
        assert r.returncode == 0, r.stderr
        media = [argv[i + 1] for i, a in enumerate(argv) if a == "--media"]
        assert media == [
            str(run / "working/style-preview/variant-A-slide-01.png"),
            str(run / "working/style-preview/variant-A-slide-02.png")]
        sent = argv[argv.index("--message") + 1]
        assert ".png" not in sent and "style-preview" not in sent
        assert "Your 3 style samples are ready." in sent

    def test_no_image_survives_the_caps_then_the_send_is_refused(
            self, tmp_path):
        payload = {"chat_id": CHAT_ID, "kind": "ack", "message": PICK_MESSAGE,
                   "style_pick_samples": [str(tmp_path / "gone.png")]}
        r, argv = _run(payload, tmp_path)
        assert r.returncode == 6
        assert "no image survived the caps" in r.stderr
        assert argv == []                       # gateway never called

    def test_payload_without_the_field_is_unchanged(self, tmp_path):
        """The other 21 call sites: no field, no media, text byte-identical."""
        payload = {"chat_id": CHAT_ID, "kind": "progress",
                   "message": f"a path {tmp_path}/x.png stays as it was"}
        r, argv = _run(payload, tmp_path)
        assert r.returncode == 0, r.stderr
        assert "--media" not in argv
        assert f"{tmp_path}/x.png" in argv[argv.index("--message") + 1]

    def test_legacy_text_only_transport_refuses_to_pretend(self, tmp_path):
        png = _png(tmp_path, "s.png")
        payload = {"chat_id": CHAT_ID, "kind": "ack", "message": PICK_MESSAGE,
                   "style_pick_samples": [str(png)]}
        r, _ = _run(payload, tmp_path,
                    {"PRESENTATION_NOTIFY_DIRECT_TELEGRAM": "1"})
        assert r.returncode == 6
        assert "text-only" in r.stderr
