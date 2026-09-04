#!/usr/bin/env python3
"""SMOKE-1 fix (2026-09-01): P9.1-SPEECH-PDF's manifest cmd chained two
scripts with && — but the engine tokenizes executor.cmd with shlex.split and
runs it via subprocess without a shell, so && arrives as a literal ARGV
token and argparse exits 2. This runner executes the chain without a shell:
same two steps, same order, same artifacts."""
import subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

def main() -> int:
    a = sys.argv[1:]
    # args: --speech S --intake I --arc A --out SPEC --pdf-out PDF
    def get(flag):
        return a[a.index(flag) + 1]
    speech, intake, arc = get("--speech"), get("--intake"), get("--arc")
    spec_out, pdf_out = get("--out"), get("--pdf-out")
    r1 = subprocess.run([sys.executable, str(SCRIPTS / "speech_spec_build.py"),
                         "--speech", speech, "--intake", intake,
                         "--arc", arc, "--out", spec_out])
    if r1.returncode != 0:
        return r1.returncode
    r2 = subprocess.run([sys.executable, str(SCRIPTS / "presenters_speech_pdf.py"),
                         "--spec", spec_out, "--out", pdf_out])
    return r2.returncode

if __name__ == "__main__":
    sys.exit(main())
