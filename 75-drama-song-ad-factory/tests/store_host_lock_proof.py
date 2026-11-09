#!/usr/bin/env python3
"""XR5 per-host lock proof: run both state_store suites on THIS host and print
one JSON line (platform, filesystem of the temp dir, exit codes). Run on each
supported host: python3 -I store_host_lock_proof.py
"""
import json, os, platform, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = {"w53": os.path.join(HERE, "test_state_store_s75w53_store_r4.py"),
          "w02u4": os.path.join(HERE, os.pardir, "scripts", "core", "test_state_store_s75w02u4.py")}
def fs(path):
    try:
        out = subprocess.run(["df", "-T", path] if sys.platform.startswith("linux") else ["df", path],
                             capture_output=True, text=True).stdout.splitlines()[-1]
        return out.split()[1] if sys.platform.startswith("linux") else out.split()[0]
    except Exception as e:
        return "unknown:%s" % e
res = {"platform": platform.platform(), "python": platform.python_version(), "tmp_fs": fs(tempfile.gettempdir())}
for k, p in SUITES.items():
    r = subprocess.run([sys.executable, "-I", "-B", p], cwd=os.path.dirname(p), capture_output=True, text=True)
    res[k] = {"exit": r.returncode, "last": (r.stdout.strip().splitlines() or [""])[-1]}
res["pass"] = all(res[k]["exit"] == 0 for k in SUITES)
print(json.dumps(res)); sys.exit(0 if res["pass"] else 1)
