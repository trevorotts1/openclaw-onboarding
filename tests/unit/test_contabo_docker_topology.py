#!/usr/bin/env python3
"""Contabo/Hostinger Docker topology contract (ILG-002, item g).

Every client Command Center runs INSIDE the client's own container on the
Contabo/VPS host (never on the operator Mac): own app, own
mission-control.db, own port, Cloudflare as access layer only
(memory: contabo-clients-own-command-center-in-their-docker-never-mac).
Host UI secrets live in the host /docker/<project>/.env, never only inside
the container (memory: openclaw-hostinger-env-file-location).

Hermetic: fixture trees + stub PATH, no Docker daemon, no network.
"""
import json
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "platform/vps/bootstrap.sh"
COMMON = REPO / "platform/common.sh"
RESOLVER = REPO / "shared-utils/resolve-oc-root.sh"
CREATE_TUNNEL = REPO / "32-command-center-setup/scripts/create-tunnel.sh"
RUN_FULL_INSTALL = REPO / "32-command-center-setup/scripts/run-full-install.sh"
INGRESS_LIB = REPO / "shared-utils/cc-tunnel-ingress.sh"


class ShellFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("OPENCLAW_", "OC_", "BASH_FUNC_")) and k not in ("BASH_ENV", "ENV")}
        self.env.update(HOME=str(self.home), PATH=str(self.bin) + ":/usr/bin:/bin",
                        FIXTURE_OS="Linux", FIXTURE_CONTAINER="0", FIXTURE_DOCKER_NAMES="",
                        FIXTURE_DOCKER_ALL="", FIXTURE_DOCKER_USER="node",
                        FIXTURE_DOCKER_CALLS=str(self.root / "docker-calls"))
        self.stub("uname", 'printf "%s\\n" "$FIXTURE_OS"')
        self.stub("df", "printf 'Filesystem Blocks Used Available Capacity Mounted\\nfixture 99999999 0 99999999 0%% /\\n'")
        self.stub("curl", "exit 97")
        self.stub("docker", """
case "$1" in
  ps) if [ "${2:-}" = -a ]; then printf '%s\\n' "$FIXTURE_DOCKER_ALL"; else printf '%s\\n' "$FIXTURE_DOCKER_NAMES"; fi ;;
  inspect) printf '%s\\n' "$FIXTURE_DOCKER_USER" ;;
  *) exit 97 ;;
esac""")

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)

    def run_shell(self, body, **env):
        values = dict(self.env, **env)
        script = ("set -e\nsource " + shlex.quote(str(COMMON)) + "\n"
                  "oc_container_marked() { [[ \"$FIXTURE_CONTAINER\" == 1 ]]; }\n"
                  "_SCRIPT_DIR=" + shlex.quote(str(self.root)) + "\n" + body)
        return subprocess.run(["/bin/bash", "-c", script], env=values,
                              capture_output=True, text=True, timeout=15)


class DockerTopologyTests(ShellFixture):
    def fields(self):
        return "printf \"RESULT:%s|%s|%s\\n\" \"$OC_PLATFORM\" \"$OPENCLAW_RUNTIME_TOPOLOGY\" \"$OC_CONFIG\""

    def test_empty_docker_output_falls_through_to_native(self):
        """No containers at all: native Linux install, empty match list never blocks."""
        result = self.run_shell("source " + shlex.quote(str(BOOTSTRAP)) + "\n" + self.fields(),
                                FIXTURE_DOCKER_NAMES="", FIXTURE_DOCKER_ALL="")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESULT:vps|native|" + str(self.home / ".openclaw"), result.stdout)
        self.assertFalse((self.root / "docker-calls").exists())

    def test_stopped_openclaw_container_refuses_host_install(self):
        """A stopped client container is still the client: refuse, never install beside it."""
        result = self.run_shell("source " + shlex.quote(str(BOOTSTRAP)),
                                FIXTURE_DOCKER_NAMES="", FIXTURE_DOCKER_ALL="openclaw-stopped")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stopped", result.stderr.lower())

    def test_resolver_prefers_explicit_root_pin(self):
        """OPENCLAW_ROOT pin wins over /data (one client among many on a shared host)."""
        data = Path("/data/.openclaw")
        body = "source " + shlex.quote(str(RESOLVER)) + "\nresolve_oc_root"
        pinned = self.root / "pinned-client"
        pinned.mkdir()
        result = self.run_shell(body, OPENCLAW_ROOT=str(pinned))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(pinned))
        _ = data  # /data is host state; this test only proves the pin wins when set.

    def test_platform_maps_to_cc_boundary_values(self):
        """run-full-install translates vps->vps-docker / mac->mac-mini for platform.ts."""
        text = RUN_FULL_INSTALL.read_text()
        self.assertIn('vps) plat_value="vps-docker"', text)
        self.assertIn('mac) plat_value="mac-mini"', text)
        for line in text.splitlines():
            if "plat_value=" in line and "==" in line:
                self.fail("platform value must be translated, never passed through raw: " + line)

    def test_tunnel_token_never_on_argv(self):
        """Connector token travels via mode-600 --token-file, never a ps-visible --token."""
        text = CREATE_TUNNEL.read_text()
        self.assertIn("--token-file", text)
        self.assertIn("chmod 600", text)
        self.assertNotIn("tunnel run --token $TUNNEL_TOKEN", text)
        self.assertNotIn("tunnel run --token ${TUNNEL_TOKEN", text)

    def test_tunnel_port_uses_ingress_lib(self):
        """create-tunnel sources cc-tunnel-ingress.sh; the 4000 literal stays single-sourced."""
        text = CREATE_TUNNEL.read_text()
        self.assertIn("cc-tunnel-ingress.sh", text)
        lib = INGRESS_LIB.read_text()
        self.assertIn("CC_INGRESS_PORT:=4000", lib.replace(": ", ":").replace(" ", "") or lib)

    def test_interview_prefers_configured_public_url(self):
        """CC_PUBLIC_URL beats MC_TENANT_PUBLIC_URL beats slug default; strict HTTPS origin."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "launch", REPO / "32-command-center-setup/scripts/interview-launch.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            m.initialize(state, "client-a", "Client A", "owner@example.test",
                         {"CC_PUBLIC_URL": "https://cc.example.com",
                          "MC_TENANT_PUBLIC_URL": "https://mc.example.com"})
            self.assertEqual(json.loads(state.read_text())["commandCenterUrl"],
                             "https://cc.example.com")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            m.initialize(state, "client-a", "Client A", "owner@example.test",
                         {"MC_TENANT_PUBLIC_URL": "https://mc.example.com"})
            self.assertEqual(json.loads(state.read_text())["commandCenterUrl"],
                             "https://mc.example.com")
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            m.initialize(state, "client-a", "Client A", "owner@example.test", {})
            self.assertEqual(json.loads(state.read_text())["commandCenterUrl"],
                             "https://client-a.zerohumanworkforce.com")
        with self.assertRaises(ValueError):
            m.public_origin("http://localhost:4000")


if __name__ == "__main__":
    unittest.main()
