#!/usr/bin/env python3
"""Unit qc-kie-docs-host: the F14 scanner exempts ONLY the docs host. stdlib only.

Proves (order qc-kie-docs-host):
- the pre-fix endpoint pattern flags a docs.kie.ai citation (the fail-first
  witness: this is the bug the unit fixes)
- a fixture citing https://docs.kie.ai/suno-api/generate-music/ now PASSES
  (exit 0) — before the fix this same fixture exits 2
- https://api.kie.ai/api/v1/generate still FAILS (exit 2, file named)
- ONE line carrying BOTH a docs URL and an api URL still FAILS and names the
  file (the per-occurrence case: a line-level grep -v would pass the two
  checks above and fail this one)
- any other subdomain (upload.kie.ai, a host nobody has thought of yet) and
  bare kie.ai still FAIL
- the real core tree the test lives in is clean (exit 0)

Zero network, zero paid calls, zero ffmpeg.
Run: python3 core/kie_dispatch/test_qc_docs_host.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SCAN = os.path.normpath(os.path.join(CORE, "..", "qc-no-direct-kie.sh"))

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)

def scan(core_dir):
    return subprocess.run(
        ["bash", SCAN], capture_output=True, text=True,
        env=dict(os.environ, DRAMA75_CORE=core_dir,
                 PYTHONDONTWRITEBYTECODE="1"))

def fixture(name, body):
    """A throwaway core/ with one non-dispatch module in it."""
    tmp = tempfile.mkdtemp(prefix="qcdocs-")
    d = os.path.join(tmp, "core", "rogue")
    os.makedirs(d)
    with open(os.path.join(d, name), "w") as f:
        f.write(body)
    return os.path.join(tmp, "core")

def old_pattern_hits(core_dir):
    """The pre-fix endpoint expression, verbatim from main."""
    return subprocess.run(
        ["grep", "-rInE", "--exclude=test_*.py",
         "-e", r"(https?://)?(api\.)?kie\.ai", core_dir],
        capture_output=True, text=True).stdout

def main():
    check("scanner exists", os.path.isfile(SCAN), SCAN)

    docs_body = ('# provenance for the limit table\n'
                 'SOURCE = "https://docs.kie.ai/suno-api/generate-music/"\n'
                 'NOTE = "re-read the generate-music schema on docs.kie.ai (free)"\n')

    # (a) docs host passes — and the pre-fix pattern would have bitten it.
    docs = fixture("prompt_limits.py", docs_body)
    env = scan(docs)
    check("(a) docs.kie.ai citation passes (exit 0)", env.returncode == 0,
          "rc=%s out=%s err=%s" % (env.returncode, env.stdout[-200:],
                                   env.stderr[-300:]))
    check("(a) fail-first witness: pre-fix pattern flags the same file",
          "prompt_limits.py" in old_pattern_hits(docs),
          old_pattern_hits(docs)[:200])

    # (b) a real api call outside kie_dispatch still fails, and is named.
    api = fixture("rogue_caller.py",
                  'URL = "https://api.kie.ai/api/v1/generate"\n')
    env = scan(api)
    check("(b) api.kie.ai still fails (exit 2)", env.returncode == 2,
          "rc=%s" % env.returncode)
    check("(b) offender named", "rogue_caller.py" in env.stderr,
          env.stderr[-300:])

    # (b hardened) one line, both URLs: the decision must be per OCCURRENCE.
    mixed = fixture(
        "mixed_caller.py",
        'URL = "https://docs.kie.ai/suno-api/generate-music/ https://api.kie.ai/api/v1/generate"\n')
    env = scan(mixed)
    check("(b+) mixed docs+api line fails (exit 2)", env.returncode == 2,
          "rc=%s err=%s" % (env.returncode, env.stderr[-300:]))
    check("(b+) mixed line names the file", "mixed_caller.py" in env.stderr,
          env.stderr[-300:])
    # the same line must NOT fail when it carries only the docs URL
    mixed_ok = fixture(
        "mixed_caller.py",
        'URL = "https://docs.kie.ai/suno-api/generate-music/ https://docs.kie.ai/market/kling/ai-avatar-standard"\n')
    env = scan(mixed_ok)
    check("(b+) docs-only twin of that line passes (exit 0)",
          env.returncode == 0,
          "rc=%s err=%s" % (env.returncode, env.stderr[-300:]))

    # (c) every other host still bites: unknown subdomain, bare host.
    for host, label in (("https://upload.kie.ai/x", "unknown subdomain"),
                        ("https://kie.ai/api/v1/x", "bare kie.ai"),
                        ("kie.ai", "bare host, no scheme")):
        d = fixture("caller.py", 'URL = "%s"\n' % host)
        env = scan(d)
        check("(c) %s still fails (exit 2)" % label, env.returncode == 2,
              "rc=%s err=%s" % (env.returncode, env.stderr[-200:]))

    # (d) the real core tree is clean with the fixed scanner.
    env = scan(CORE)
    check("(d) real core tree clean (exit 0)", env.returncode == 0,
          "rc=%s err=%s" % (env.returncode, env.stderr[-300:]))

    print("")
    if FAILS:
        print("%d checks failed:" % len(FAILS))
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all qc-kie-docs-host checks passed (8 blocks)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
