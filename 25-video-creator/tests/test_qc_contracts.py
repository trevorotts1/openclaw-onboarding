import os
import subprocess


def run_qc(skill_root, tmp_path, provider, keys=None):
    home = tmp_path / "home"
    (home / ".openclaw" / "skills" / "25-video-creator").mkdir(parents=True)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["VIDEO_CREATOR_PROVIDER"] = provider
    for name in ("KIE_API_KEY", "PIKA_API_KEY", "RUNWAY_API_KEY"):
        env.pop(name, None)
    env.update(keys or {})
    return subprocess.run(
        ["bash", str(skill_root / "qc-video-creator.sh")],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_keyless_mock_local_qc_passes(skill_root, tmp_path):
    for provider in ("mock", "local"):
        result = run_qc(skill_root, tmp_path / provider, provider)
        assert result.returncode == 0, result.stdout


def test_selected_real_provider_requires_its_key(skill_root, tmp_path):
    missing = run_qc(skill_root, tmp_path / "missing", "kieai")
    configured = run_qc(
        skill_root, tmp_path / "configured", "kieai", {"KIE_API_KEY": "SET"}
    )
    assert missing.returncode != 0
    assert configured.returncode == 0, configured.stdout
