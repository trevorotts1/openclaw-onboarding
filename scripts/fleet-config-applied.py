#!/usr/bin/env python3
"""Read-only: does each box's running gateway run the config its openclaw.json holds?

Back-to-back openclaw.json writes can supersede a gateway reload
("GatewayConfigReloadSupersededError"); the file then says one thing and the
live gateway runs another until some later restart. This asks every box's own
gateway (`openclaw gateway call config.get`) for two hashes -- the config file's
revision and the config it applied -- and prints only whether they match.
Nothing is changed and no config value is printed.

  python3 scripts/fleet-config-applied.py [--boxes-file ~/.openclaw/fleet/boxes.json]

Per box: APPLIED | PENDING (needs a gateway restart) | UNDETERMINED (why).
"""
import argparse
import json
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROBE = r'''python3 -c '
import json, subprocess
try:
    out = subprocess.run(["openclaw", "gateway", "call", "config.get", "--json"],
                         capture_output=True, text=True, timeout=30).stdout
    d = json.loads(out)
    d = d.get("payload") or d.get("result") or d
    a, b = d.get("configRevisionHash"), d.get("appliedConfigHash")
    print("APPLIED" if a and a == b else "PENDING" if a and b else "UNDETERMINED gateway reports no applied hash")
except Exception as e:
    print("UNDETERMINED", type(e).__name__)
' '''


def remote(box: dict) -> list:
    if box.get("container"):
        env = ["-e", f"OPENCLAW_ROOT={box['openclaw_root']}"] if box.get("openclaw_root") else []
        cmd = ["docker", "exec", "-u", box.get("docker_exec_user") or "node", *env, box["container"], "bash", "-lc", PROBE]
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", box["ssh_target"], shlex.join(cmd)]
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", box["ssh_target"], "zsh -lc " + shlex.quote(PROBE)]


def check(box: dict) -> tuple:
    name = box.get("client") or box["name"]
    try:
        r = subprocess.run(remote(box), capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return name, "UNDETERMINED ssh timed out"
    line = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode == 255:
        return name, "UNDETERMINED ssh failed: " + (r.stderr.strip().splitlines() or ["?"])[-1][:80]
    return name, line or f"UNDETERMINED no answer (exit {r.returncode})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boxes-file", default=str(Path.home() / ".openclaw/fleet/boxes.json"))
    args = ap.parse_args()
    boxes = json.loads(Path(args.boxes_file).expanduser().read_text())
    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = sorted(pool.map(check, boxes))
    for name, verdict in rows:
        print(f"{name:40} {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
