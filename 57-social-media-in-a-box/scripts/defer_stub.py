#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: GRACEFUL DEFER STUB
# -----------------------------------------------------------------------------
# Some v0.2.0-adjacent capabilities are HONESTLY deferred to a named later
# version (merge plan §2 disposition ledger — DEFER, not DROP). Requesting one
# must FAIL CLOSED with a clear "deferred to vX.Y.Z" message, never a silent
# no-op and never a fabricated success. Baseline config-carried behavior is
# never blocked meanwhile (off-by-default), so no client loses a capability
# they already had.
#
#   narrated-video   -> v0.3.0  (C8: 55-60s multi-clip Reel + Fish-Audio voiceover)
#   syndicate        -> v0.4.0  (C9: WordPress / Medium / Substack / YouTube-direct)
#   persona-adapter  -> v0.5.0  (C10: Skill-22 persona INPUT adapter; use config baseline)
#   memory-adapter   -> v0.5.0  (C11: Skill-31 memory-core 'Dreaming' performance feed)
#
# EXIT: 0 --self-test PASS / 2 deferred (fail-closed) / 3 usage.
# USAGE:
#   python3 defer_stub.py --capability syndicate
#   python3 defer_stub.py --self-test
# =============================================================================
"""Fail-closed deferral stubs for Social Media in a Box (Skill 57)."""

import argparse
import sys

EXIT_PASS = 0
EXIT_DEFERRED = 2
EXIT_USAGE = 3

AF_DEFERRED = "AF-SM-DEFERRED"

# capability -> (target version, one-line what, baseline-that-still-works)
DEFERRED = {
    "narrated-video": ("0.3.0",
        "narrated Reels (55-60s multi-clip + continuous Fish-Audio voiceover, FFmpeg concat)",
        "the Sora 25.0s single-shot video lane (`--mode video`) works today"),
    "syndicate": ("0.4.0",
        "non-GHL add-on channels (WordPress / Medium / Substack / YouTube-direct)",
        "GHL-direct posting for every connected platform works today"),
    "persona-adapter": ("0.5.0",
        "the Skill-22 persona INPUT adapter (5-layer alignment -> brandInfo/tone/avatar)",
        "the config-carried persona baseline (personaSource:config) works today"),
    "memory-adapter": ("0.5.0",
        "the Skill-31 memory-core 'Dreaming' performance-insight feed",
        "the theme-of-week log half is already folded (P1 themeOfWeek in the state spine)"),
}


def message(capability):
    ver, what, baseline = DEFERRED[capability]
    return ("DEFERRED [%s]: '%s' (%s) is deferred to v%s. This stub fails CLOSED rather than "
            "silently no-op; %s, so nothing you have today is blocked."
            % (AF_DEFERRED, capability, what, ver, baseline))


def run(capability):
    if capability not in DEFERRED:
        print("FATAL: unknown capability %r (known: %s)"
              % (capability, ", ".join(sorted(DEFERRED))), file=sys.stderr)
        return EXIT_USAGE
    print(message(capability), file=sys.stderr)
    return EXIT_DEFERRED


def self_test():
    ok = True
    for cap in DEFERRED:
        rc = run(cap)
        good = rc == EXIT_DEFERRED and ("v" + DEFERRED[cap][0]) in message(cap)
        ok = ok and good
        print("  [%s] %-16s -> exit %d (deferred to v%s)"
              % ("PASS" if good else "MISS", cap, rc, DEFERRED[cap][0]))
    rc = run("does-not-exist")
    good = rc == EXIT_USAGE
    ok = ok and good
    print("  [%s] unknown capability -> exit %d (usage)" % ("PASS" if good else "MISS", rc))
    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed deferral stubs (Skill 57).")
    ap.add_argument("--capability", choices=sorted(DEFERRED))
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.capability:
        ap.error("--capability is required (or use --self-test)")
    return run(args.capability)


if __name__ == "__main__":
    sys.exit(main())
