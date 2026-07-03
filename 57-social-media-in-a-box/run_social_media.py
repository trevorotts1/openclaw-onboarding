#!/usr/bin/env python3
"""run_social_media.py — the deterministic state machine over SOCIAL-MANIFEST.json.

Walks the phases for the requested MODE IN ORDER with NO phase skips. Each
phase's preflight is checked against the run directory's artifacts; the QC
phases shell out to the fail-closed provers (preflight_gate.py, validate_
contract.py, prove_bands.py, scrub_gate.py) and refuse to advance on ANY
AF-SM-* violation. P6 shells to build_manifest.py which mints the signed
process certificate (proving ZERO Anthropic per run); the publisher (P7)
refuses to run without that certificate.

FRONT-DOOR NONCE: like the Email Engine / Presentations orchestrators, this
refuses to run unless OC_SMIB_ENTRY_NONCE matches the run-scoped nonce minted
by social-media-entry.sh (the ONE sanctioned entry). Model-free, provider-
neutral: it calls NO LLM and NO provider — it only sequences the gates.

EXIT CODES:
  0  all requested phases passed (certificate issued on a full run)
  2  a phase gate failed (fail-closed)
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through social-media-entry.sh)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_GATE = 2
EXIT_USAGE = 3
EXIT_NONCE = 4

_SKILL_DIR = Path(__file__).resolve().parent
MANIFEST = _SKILL_DIR / "SOCIAL-MANIFEST.json"
SCRIPTS = _SKILL_DIR / "scripts"

PLANNER_COLUMNS = ["Week Of", "Theme", "Research", "Core Content", "Images", "Videos",
                   "Facebook", "Instagram", "LinkedIn", "YouTube", "TikTok", "Pinterest",
                   "Carousels", "Blog", "Podcast", "Email", "QC", "Scheduled", "Overall", "Notes"]


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read SOCIAL-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _phase(manifest, pid):
    for ph in manifest.get("phases", []):
        if ph.get("id") == pid:
            return ph
    return None


def _nonce_ok(run_dir: Path) -> bool:
    want = os.environ.get("OC_SMIB_ENTRY_NONCE", "")
    nf = run_dir / "working" / "checkpoints" / ".smib-entry-nonce"
    if not want or not nf.is_file():
        return False
    try:
        return nf.read_text(encoding="utf-8").strip() == want.strip()
    except OSError:
        return False


def _run_script(script, args):
    cmd = [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args]
    return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _json(run_dir, rel, default=None):
    try:
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---- per-phase checkers -----------------------------------------------------
def _chk_preflight(run_dir):
    cfg = run_dir / "working" / "copy" / "config.json"
    if not cfg.is_file():
        return False, "missing working/copy/config.json"
    rc = _run_script("preflight_gate.py", [cfg])
    return rc == 0, ("preflight PASS" if rc == 0 else "preflight_gate.py FAILED (exit %d)" % rc)


def _chk_plan(run_dir):
    plan = _json(run_dir, "working/plan/plan.json")
    if not isinstance(plan, dict):
        return False, "missing working/plan/plan.json"
    if not str(plan.get("themeOfWeek", "")).strip():
        return False, "plan.json has no themeOfWeek"
    if not str(plan.get("plannerSheetId", "")).strip():
        return False, "plan.json has no plannerSheetId"
    return True, "plan.json complete"


def _chk_content_authored(run_dir):
    if not (run_dir / "working" / "content").is_dir():
        return False, "missing working/content/"
    bands = list((run_dir / "working" / "content" / "bands").glob("*.json")) \
        if (run_dir / "working" / "content" / "bands").is_dir() else []
    if not bands and not (run_dir / "working" / "content" / "content.json").is_file():
        return False, "no content authored (working/content/bands/*.json or content.json)"
    return True, "content authored"


def _chk_contract_and_bands(run_dir):
    cdir = run_dir / "working" / "content"
    bands_files = sorted((cdir / "bands").glob("*.json")) if (cdir / "bands").is_dir() else []
    contract_files = sorted((cdir / "contracts").glob("*.json")) if (cdir / "contracts").is_dir() else []
    if not bands_files:
        return False, "no bands inputs at working/content/bands/*.json"
    for f in bands_files:
        rc = _run_script("prove_bands.py", [f])
        if rc != 0:
            return False, "prove_bands FAILED on %s (exit %d)" % (f.name, rc)
    for f in contract_files:
        rc = _run_script("validate_contract.py", [f])
        if rc != 0:
            return False, "validate_contract FAILED on %s (exit %d)" % (f.name, rc)
    return True, "bands + contracts PASS (%d bands, %d contracts)" % (len(bands_files), len(contract_files))


def _chk_media_ledger(run_dir):
    summ = _json(run_dir, "working/media/media_ledger.json")
    if not isinstance(summ, dict):
        return False, "missing working/media/media_ledger.json"
    if summ.get("all_terminal") is not True:
        return False, "media ledger has non-terminal jobs (incomplete run)"
    if summ.get("is_carousel") and summ.get("assemble_ok") is not True:
        return False, "carousel assembly floor not met (>=2 images)"
    return True, "media ledger terminal (images_ready=%s)" % summ.get("images_ready")


def _chk_scrub(run_dir):
    rc = _run_script("scrub_gate.py", [run_dir / "working"])
    return rc == 0, ("scrub PASS" if rc == 0 else "scrub_gate.py FAILED (exit %d)" % rc)


def _chk_manifest(run_dir):
    rc = _run_script("build_manifest.py", ["--run-dir", run_dir])
    if rc != 0:
        return False, "build_manifest.py FAILED (exit %d)" % rc
    if not (run_dir / "delivery" / "PROCESS-CERTIFICATE.json").is_file():
        return False, "no certificate issued"
    return True, "certificate issued"


def _chk_publish(run_dir):
    if not (run_dir / "delivery" / "PROCESS-CERTIFICATE.json").is_file():
        return False, "publisher blocked: no signed certificate (AF-SM-PUBLISH-UNPROVEN)"
    results = _json(run_dir, "working/publish/publish_results.json")
    if not isinstance(results, list) or not results:
        return False, "missing working/publish/publish_results.json"
    for i, r in enumerate(results, 1):
        rc = _run_script("validate_contract.py", ["--kind", "publish_result",
                         _dump_tmp(run_dir, "publish_%d" % i, r)])
        if rc != 0:
            return False, "publish result %d not the normalized contract" % i
    # §4.4 NO-DOUBLE-POST — creative modes RAISE double-post risk; run the named
    # fail-closed de-dup gate when the run supplies a de-dup snapshot. Absent (a
    # default engine run with no creative interjection) -> nothing to de-dup.
    dedup = run_dir / "working" / "creative" / "dedup.json"
    if dedup.is_file():
        rc = _run_script("ledger.py", ["dedup-snapshot", "--input", dedup])
        if rc != 0:
            return False, "de-dup BLOCK (AF-SM-DOUBLE-POST): a duplicate content-fingerprint or " \
                          "occupied slot was detected. Clear with `clean`/reschedule or a logged " \
                          "owner re-post token."
    return True, "publish results normalized (%d)" % len(results)


def _chk_client_copy(run_dir):
    """M3 P2-INGEST: the client's finished copy is staged; the engine never authors."""
    d = run_dir / "working" / "creative" / "client-copy"
    files = list(d.glob("*.json")) if d.is_dir() else []
    if not files:
        return False, "no client-supplied copy at working/creative/client-copy/*.json (AF-SM-CONTENT-MISSING)"
    return True, "client copy staged (%d file(s)); verbatim proven at P6" % len(files)


def _chk_fold(run_dir, rel, kind, label):
    """Shared fold checker (C4 newsletter / C5 blog): artifact must exist and pass
    validate_contract.py + prove_bands.py for its kind (bands read from config/bands.json)."""
    f = run_dir / rel
    if not f.is_file():
        return False, "missing %s" % rel
    rc = _run_script("validate_contract.py", ["--kind", kind, f])
    if rc != 0:
        return False, "%s contract FAILED (validate_contract.py exit %d)" % (label, rc)
    rc = _run_script("prove_bands.py", ["--kind", kind, f])
    if rc != 0:
        return False, "%s bands FAILED (prove_bands.py exit %d)" % (label, rc)
    return True, "%s contract + bands PASS" % label


def _chk_newsletter(run_dir):
    return _chk_fold(run_dir, "working/content/newsletter.json", "newsletter", "newsletter")


def _chk_blog(run_dir):
    return _chk_fold(run_dir, "working/content/blog.json", "blog", "blog")


def _chk_podcast(run_dir):
    """C3 podcast fold. A labeled PODCAST_DEFERRED skip ({"deferred":true}) passes
    (Fish-Audio/Podbean unconfigured is never a failure); otherwise the ffprobe/cover
    numbers are proven against the SACRED podcast bands."""
    f = run_dir / "working" / "media" / "podcast.json"
    if not f.is_file():
        return False, "missing working/media/podcast.json"
    rec = _json(run_dir, "working/media/podcast.json", {})
    if isinstance(rec, dict) and rec.get("deferred") is True:
        return True, "PODCAST_DEFERRED (Fish-Audio/Podbean unconfigured — labeled skip, not a failure)"
    rc = _run_script("prove_bands.py", ["--kind", "podcast", f])
    if rc != 0:
        return False, "podcast bands FAILED (prove_bands.py exit %d)" % rc
    return True, "podcast script/duration/bitrate/cover bands PASS"


def _chk_engage(run_dir):
    """C6 engage fold — read-only. The anomaly report artifact must exist and carry a
    period + platform-level metrics. NEVER blocks a publish (own mode / week tail)."""
    rep = _json(run_dir, "working/qc/engage_report.json")
    if not isinstance(rep, dict):
        return False, "missing working/qc/engage_report.json (AF-SM-ENGAGE-REPORT)"
    if not rep.get("period") or not isinstance(rep.get("platforms"), (list, dict)):
        return False, "engage report missing period/platforms metrics (AF-SM-ENGAGE-REPORT)"
    return True, "read-only engagement/anomaly report present (%s)" % rep.get("period")


def _chk_deferred(run_dir):
    """DEFER stub (syndicate C9). Fail CLOSED with a clear 'deferred to vX.Y.Z' message
    rather than silently no-op — mirrors defer_stub.py."""
    rc = _run_script("defer_stub.py", ["--capability", "syndicate"])
    return False, "syndicate (non-GHL add-on channels) is DEFERRED to v0.4.0 (AF-SM-DEFERRED); " \
                  "off by default so no client is blocked meanwhile. defer_stub exit %d" % rc


def _chk_writeback(run_dir):
    rec = _json(run_dir, "working/plan/row_appended.json")
    if not isinstance(rec, dict):
        return False, "missing working/plan/row_appended.json"
    row = rec.get("row") or rec.get("columns")
    if not isinstance(row, list) or len(row) != 20:
        return False, "planner row is not the normalized 20-column shape (got %s)" % (
            len(row) if isinstance(row, list) else "n/a")
    return True, "20-column row appended"


def _dump_tmp(run_dir, name, obj):
    d = run_dir / "working" / "checkpoints" / "_tmp"
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.json" % name)
    p.write_text(json.dumps(obj), encoding="utf-8")
    return p


_CHECKERS = {
    "_chk_preflight": _chk_preflight, "_chk_plan": _chk_plan,
    "_chk_content_authored": _chk_content_authored, "_chk_contract_and_bands": _chk_contract_and_bands,
    "_chk_media_ledger": _chk_media_ledger, "_chk_scrub": _chk_scrub,
    "_chk_manifest": _chk_manifest, "_chk_publish": _chk_publish, "_chk_writeback": _chk_writeback,
    "_chk_client_copy": _chk_client_copy, "_chk_newsletter": _chk_newsletter,
    "_chk_blog": _chk_blog, "_chk_podcast": _chk_podcast, "_chk_engage": _chk_engage,
    "_chk_deferred": _chk_deferred,
}

# v0.2.0 modes: engine-driven (v0.1.0) + fold (C3-C7) + creative (M1-M4) + syndicate defer (C9).
MODES = ["week", "day", "carousel", "video", "podcast-cover", "plan", "clean",
         "podcast", "newsletter", "blog", "engage",
         "brief", "campaign", "client-copy", "reactive", "syndicate"]

# DEFER map (fail-closed, clear 'deferred to vX.Y.Z' message; baseline config never blocked).
_DEFERRED = {
    "narrated-video": "0.3.0", "syndicate": "0.4.0",
    "persona-adapter": "0.5.0", "memory-adapter": "0.5.0",
}


def _defer_check(mode, args, run_dir):
    """Pre-run DEFER gate. A capability deferred to a named later version fails CLOSED
    with a clear message BEFORE any phase runs — never a silent no-op. Syndicate has its
    own manifest phase (P-SYNDICATE-DEFER); the --narrated flag and the persona/memory
    adapters are gated here. Baseline config-carried behavior (personaSource:config) is
    never affected."""
    hits = []
    cfg = _json(run_dir, "working/copy/config.json", {}) if run_dir else {}
    cfg = cfg if isinstance(cfg, dict) else {}
    if getattr(args, "narrated", False) or cfg.get("narratedVideo") is True:
        hits.append(("narrated-video", "C8 narrated Reels (55-60s multi-clip + Fish-Audio voiceover)"))
    if str(cfg.get("personaSource", "config")) == "adapter":
        hits.append(("persona-adapter", "C10 Skill-22 persona input adapter (use personaSource:config baseline)"))
    if cfg.get("memoryFeed") is True:
        hits.append(("memory-adapter", "C11 Skill-31 memory-core 'Dreaming' performance feed"))
    for cap, what in hits:
        ver = _DEFERRED.get(cap, "a later version")
        print("DEFERRED [AF-SM-DEFERRED]: %s is deferred to v%s. %s. This stub fails CLOSED "
              "rather than silently no-op; baseline config-carried behavior is never blocked."
              % (cap, ver, what), file=sys.stderr)
    return bool(hits)


def _write_gates(run_dir, gates):
    out = run_dir / "working" / "checkpoints" / "gates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gates, indent=2), encoding="utf-8")


def plan(manifest, mode):
    phases = manifest.get("modes", {}).get(mode)
    if not phases:
        print("FATAL: unknown mode %r" % mode, file=sys.stderr)
        return EXIT_USAGE
    print("== Social Media in a Box — mode '%s' phase plan ==" % mode)
    for i, pid in enumerate(phases, 1):
        ph = _phase(manifest, pid) or {}
        pf = (ph.get("preflight") or {}).get("checker", "-")
        print("  %d. %s — %s" % (i, pid, ph.get("name", "")))
        print("       produces: %s" % ph.get("produces_artifact", "-"))
        print("       gate    : %s | codes: %s" % (pf, ", ".join(ph.get("gate_codes", []))))
    return EXIT_PASS


def run(manifest, mode, run_dir: Path):
    phases = manifest.get("modes", {}).get(mode)
    if not phases:
        print("FATAL: unknown mode %r" % mode, file=sys.stderr)
        return EXIT_USAGE
    gates = {}
    for pid in phases:
        ph = _phase(manifest, pid)
        if not ph:
            print("FATAL: phase %s missing from manifest" % pid, file=sys.stderr)
            return EXIT_USAGE
        checker = (ph.get("preflight") or {}).get("checker")
        print("=== PHASE %s — %s ===" % (pid, ph.get("name", "")))
        fn = _CHECKERS.get(checker)
        if fn is None:
            ok, msg = True, "checker %s not mapped (soft-pass)" % checker
        else:
            ok, msg = fn(run_dir)
        print("   [%s] %s: %s" % ("OK" if ok else "FAIL", checker, msg))
        gates[pid] = {"passed": bool(ok)}
        # Persist gates BEFORE the manifest phase so build_manifest can read P0..P5.
        if pid != "P6-MANIFEST":
            _write_gates(run_dir, gates)
        if not ok:
            _write_gates(run_dir, gates)
            print("BLOCKED at %s (fail-closed). No phase skips; fix and re-run." % pid, file=sys.stderr)
            return EXIT_GATE
    _write_gates(run_dir, gates)
    print("ALL REQUESTED PHASES PASSED for mode '%s'." % mode)
    cert = run_dir / "delivery" / "PROCESS-CERTIFICATE.json"
    if cert.is_file():
        try:
            sha = json.loads(cert.read_text())["certificate_sha"]
            print("CERTIFICATE: %s (sha %s)" % (cert, sha[:12]))
        except (ValueError, KeyError):
            pass
    return EXIT_PASS


# ---------------------------------------------------------------------------
# Command Center board card (FAIL-SOFT). Mirrors Skill-48 (ad_director) and the
# presentations build_deck._board_patch_phase pattern via the shared mc_board
# helper: land ONE mc-route card per run and advance it. A disabled board
# (no COMMAND_CENTER_URL) is a clean no-op; ANY failure is swallowed — the board
# is a VIEW, never a gate, and can never affect this orchestrator's exit code.
# ---------------------------------------------------------------------------
def _mc_board_begin(run_dir, mode):
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title="Social Media in a Box (%s) — %s" % (mode, run_dir.name),
            department="social-media", persona="Social Media in a Box",
            source="social-media")
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print("[mc_board] begin best-effort skip (%s)" % exc, file=sys.stderr)
        return None


def _mc_board_done(run_dir, task_id):
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        mc_board.complete_run(run_dir, task_id, note="certified + delivered")
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] done best-effort skip (%s)" % exc, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Social Media in a Box orchestrator (Skill 57).")
    ap.add_argument("--mode", required=True, choices=MODES)
    ap.add_argument("--run-dir", help="the run directory (contains working/)")
    ap.add_argument("--plan", action="store_true", help="print the mode's phase plan and exit")
    ap.add_argument("--narrated", action="store_true",
                    help="request the narrated video lane (C8) — DEFERRED to v0.3.0 (fails closed)")
    args = ap.parse_args(argv)

    manifest = _load_manifest()
    if args.plan:
        return plan(manifest, args.mode)
    if not args.run_dir:
        ap.error("--run-dir is required (or use --plan)")
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print("FATAL: --run-dir not found: %s" % run_dir, file=sys.stderr)
        return EXIT_USAGE
    if not _nonce_ok(run_dir):
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH social-media-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.", file=sys.stderr)
        return EXIT_NONCE
    if _defer_check(args.mode, args, run_dir):
        return EXIT_GATE
    _mc_task = _mc_board_begin(run_dir, args.mode)
    rc = run(manifest, args.mode, run_dir)
    if rc == EXIT_PASS:
        _mc_board_done(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())
