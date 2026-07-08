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

# The failing (phase_id, note) captured at a gate failure so the fail-soft board
# seam (_mc_board_blocked, FIX-XC-06) can move the card to `blocked` with the AF
# code as the note. Mutated in place (no `global`) — read only by the board seam.
_LAST_BLOCK: dict = {}


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
    """Run a prover and return its exit code. FIX-S36-62: the child's stdout+stderr
    are captured and, on FAILURE, re-printed to this process's stderr so the exact
    AF-SM-* code(s) reach the operator (the old DEVNULL redirects swallowed them,
    leaving only a bare 'FAILED (exit 2)'). Success stays quiet to keep the phase
    log readable."""
    cmd = [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    if proc.returncode != 0 and proc.stdout:
        sys.stderr.write("--- %s output (exit %d) ---\n%s\n" % (script, proc.returncode, proc.stdout.rstrip()))
    return proc.returncode


def _json(run_dir, rel, default=None):
    try:
        return json.loads((run_dir / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---- per-phase checkers -----------------------------------------------------
def _offline_token_ok(run_dir):
    """A LOGGED owner token that authorizes an OFFLINE preflight (dry-run posture)
    on a box that would otherwise probe live. Fail-closed shape: a dict with
    owner_approved/approved true + a non-empty reason. Absent/malformed -> no token."""
    tok = _json(run_dir, "working/copy/preflight-offline-token.json")
    if not isinstance(tok, dict):
        return False
    return (tok.get("owner_approved") is True or tok.get("approved") is True) \
        and bool(str(tok.get("reason", "")).strip())


def _chk_preflight(run_dir):
    """P0 readiness gate. FIX-S36-59:
      * ALWAYS pass --report so the Owner Q&A source-of-truth (credits/balance/token
        + the C2 connected-accounts reconcile) is written to disk, never memorized.
      * --live is the DEFAULT on a real client box. Offline (dry-run) is permitted
        only when the config carries a `probes` object (the authored offline probe
        data) OR a LOGGED owner offline token is staged OR SMIB_PREFLIGHT_OFFLINE is
        set. A box with neither probes nor a token has NO offline evidence, so the
        gate MUST confirm the real endpoints (fail-closed) rather than pass blind."""
    cfg = run_dir / "working" / "copy" / "config.json"
    if not cfg.is_file():
        return False, "missing working/copy/config.json"
    cfg_obj = _json(run_dir, "working/copy/config.json", {}) or {}
    has_probes = isinstance(cfg_obj.get("probes"), dict) and bool(cfg_obj.get("probes"))
    token_ok = _offline_token_ok(run_dir)
    env_offline = bool(os.environ.get("SMIB_PREFLIGHT_OFFLINE"))
    live = not (has_probes or token_ok or env_offline)
    report = run_dir / "working" / "preflight" / "preflight_report.json"
    args = [cfg, "--report", report]
    if live:
        args.append("--live")
    rc = _run_script("preflight_gate.py", args)
    mode = "LIVE probe (client box)" if live else (
        "offline (probes)" if has_probes else
        "offline (logged owner token)" if token_ok else "offline (SMIB_PREFLIGHT_OFFLINE)")
    return rc == 0, ("preflight PASS [%s], report -> working/preflight/preflight_report.json" % mode
                     if rc == 0 else "preflight_gate.py FAILED (exit %d) [%s]" % (rc, mode))


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
    # SK2-13: this is the RUNTIME scan over generated client content, so require the
    # client-name list — an unconfigured list must fail closed (a silent pass could
    # let a client name leak into published content), unlike the build-time scan.
    rc = _run_script("scrub_gate.py", ["--require-names", run_dir / "working"])
    return rc == 0, ("scrub PASS" if rc == 0 else "scrub_gate.py FAILED (exit %d)" % rc)


def _chk_manifest(run_dir):
    rc = _run_script("build_manifest.py", ["--run-dir", run_dir])
    if rc != 0:
        return False, "build_manifest.py FAILED (exit %d)" % rc
    if not (run_dir / "delivery" / "PROCESS-CERTIFICATE.json").is_file():
        return False, "no certificate issued"
    return True, "certificate issued"


def _live_mode(run_dir):
    """True on a real client box (no offline evidence), False in a dry-run/offline
    posture. Shared by preflight (P0) and publish (P7) so a run is live-or-offline
    coherently. Offline evidence = config `probes` OR a logged owner offline token
    OR SMIB_PREFLIGHT_OFFLINE."""
    cfg_obj = _json(run_dir, "working/copy/config.json", {}) or {}
    has_probes = isinstance(cfg_obj.get("probes"), dict) and bool(cfg_obj.get("probes"))
    return not (has_probes or _offline_token_ok(run_dir) or os.environ.get("SMIB_PREFLIGHT_OFFLINE"))


def _live_ghl_post_listing(cfg):
    """FIX-S36-60: GET the live GHL social post listing for the location with the
    CLIENT's own PIT (never printed). Returns a list of GHL post-id strings present
    in the account, or None when the listing is unconfirmable (fail-closed upstream)."""
    import urllib.request
    pit = str(cfg.get("pit") or os.environ.get("GHL_API_KEY", ""))
    loc = str(cfg.get("locationId", ""))
    if not pit or not loc:
        return None
    url = "https://services.leadconnectorhq.com/social-media-posting/%s/posts" % loc
    try:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer %s" % pit,
                                                   "Version": "2021-07-28"})
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec - client's own endpoint
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    posts = data.get("posts") or data.get("results") or data.get("data")
    if isinstance(posts, dict):
        posts = posts.get("posts") or posts.get("results")
    if not isinstance(posts, list):
        return None
    ids = []
    for p in posts:
        if isinstance(p, dict):
            pid = p.get("id") or p.get("_id") or p.get("postId")
            if pid is not None:
                ids.append(str(pid))
    return ids


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

    cfg = _json(run_dir, "working/copy/config.json", {}) or {}
    live = _live_mode(run_dir)

    # -- §4.4 NO-DOUBLE-POST (FIX-S36-61) -------------------------------------
    # P7 BUILDS the de-dup snapshot from the local SQLite ledger itself (this run's
    # recorded posts vs every other run's, within the lookback) + the live GHL
    # listing in --live mode, rather than only running IF a hand-authored
    # working/creative/dedup.json happens to exist (the old fail-open-by-construction
    # hole). A corrupt/unreadable ledger DB fails CLOSED ('cannot be built').
    try:
        sys.path.insert(0, str(SCRIPTS))
        import ledger  # noqa: E402
    except Exception as exc:  # noqa: BLE001
        return False, "de-dup BLOCK: cannot import the ledger to build the snapshot (%s)" % exc
    db = run_dir / "working" / "media" / "ledger.db"
    location_id = str(cfg.get("locationId", ""))
    ml = _json(run_dir, "working/media/media_ledger.json", {}) or {}
    run_id = str(ml.get("run") or run_dir.name)
    if db.is_file():
        try:
            live_listing = _json(run_dir, "working/publish/live_listing.json") if not live else None
            snap = ledger.build_dedup_snapshot(db, location_id, run_id, live_listing=live_listing)
        except Exception as exc:  # noqa: BLE001 — corrupt/unreadable ledger -> fail-closed
            return False, ("de-dup BLOCK (AF-SM-DOUBLE-POST): the ledger snapshot could not be built "
                           "(fail-closed): %s" % exc)
        blocks, cleared = ledger.check_dedup_snapshot(
            snap.get("existing"), snap.get("outgoing"),
            lookback_days=snap.get("lookback_days", ledger.DEFAULT_LOOKBACK_DAYS),
            live_listing=snap.get("live_listing"), repost_token=snap.get("repost_token"))
        if blocks and not cleared:
            return False, ("de-dup BLOCK (AF-SM-DOUBLE-POST): %d collision(s) built from the ledger. "
                           "Clear with `clean`/reschedule or a logged owner re-post token." % len(blocks))
    # A creative-interjection dedup snapshot (staged file) is ALSO honored (back-compat).
    dedup = run_dir / "working" / "creative" / "dedup.json"
    if dedup.is_file():
        rc = _run_script("ledger.py", ["dedup-snapshot", "--input", dedup])
        if rc != 0:
            return False, "de-dup BLOCK (AF-SM-DOUBLE-POST): a duplicate content-fingerprint or " \
                          "occupied slot was detected. Clear with `clean`/reschedule or a logged " \
                          "owner re-post token."

    # -- POST-PUBLISH LIVE VERIFY (FIX-S36-60) --------------------------------
    # `done` is claimed ONLY from an INDEPENDENT live GHL post-listing verify, not
    # from the poster's OWN publish_results.json (the exact evidence the SKILL calls
    # insufficient). The poster records the GHL post ids it created in
    # working/publish/posted_ids.json; each MUST appear in the live listing.
    posted_ids = _json(run_dir, "working/publish/posted_ids.json")
    posted_ids = [str(x) for x in posted_ids] if isinstance(posted_ids, list) else []
    if live:
        listing = _live_ghl_post_listing(cfg)
        if listing is None:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: the live GHL post listing was unconfirmable "
                           "(fail-closed); cannot claim done without an independent verify")
        if not posted_ids:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: no working/publish/posted_ids.json to verify "
                           "against the live GHL listing (the poster must record the ids it created)")
        present = set(listing)
        missing = [pid for pid in posted_ids if pid not in present]
        if missing:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: %d posted id(s) absent from the live GHL "
                           "listing (%s)" % (len(missing), ", ".join(missing[:5])))
        return True, ("publish results normalized (%d) + %d post id(s) verified present in the live "
                      "GHL listing" % (len(results), len(posted_ids)))
    # Offline/dry-run posture: verify against staged evidence when present, else a
    # labeled dry-run pass (mirrors the P0 connected-accounts offline posture).
    evidence = _json(run_dir, "working/publish/published_listing.json")
    if isinstance(evidence, list) and posted_ids:
        present = {str(x) for x in evidence}
        missing = [pid for pid in posted_ids if pid not in present]
        if missing:
            return False, ("AF-SM-PUBLISH-UNVERIFIED: %d posted id(s) absent from the staged listing "
                           "evidence (%s)" % (len(missing), ", ".join(missing[:5])))
        return True, "publish results normalized (%d) + posted ids verified vs staged listing" % len(results)
    return True, ("publish results normalized (%d); offline dry-run posture — live GHL post-listing "
                  "verify runs on the client box" % len(results))


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


def _deliver_slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def _deliver_week(run_dir):
    """Deterministic ISO week token (YYYY-Www) for the labeled-deliverable folder.
    Derived from plan.json weekOf (a date) when present, else the media-ledger run
    suffix, else 'unknown-week'. Never a wall-clock read (keeps the golden stable)."""
    import datetime
    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    wk = str(plan.get("weekOf", "")).strip()
    if wk:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                d = datetime.datetime.strptime(wk, fmt).date()
                iso = d.isocalendar()
                return "%04d-W%02d" % (iso[0], iso[1])
            except ValueError:
                pass
        return _deliver_slug(wk) or "unknown-week"
    ml = _json(run_dir, "working/media/media_ledger.json", {}) or {}
    run = str(ml.get("run", ""))
    if "_" in run:
        return run.rsplit("_", 1)[-1]
    return "unknown-week"


def _chk_deliver(run_dir):
    """FIX-XC-11h — the DELIVERY phase (P-DELIVER): assemble the labeled-deliverable
    manifest from this run's PASS artifacts and shell label_deliverables.py --copy
    FAIL-CLOSED (a declared artifact source that is missing on disk BLOCKS — nothing
    unlabeled or phantom ever 'delivers'). The deterministic LOGICAL dest root (the
    ~/Downloads convention, never a physical temp path) is recorded to
    delivery/deliverables-manifest.json so build_manifest binds it onto the
    certificate. Physical copy target is $SMIB_DELIVER_DEST (tests/CI) else the
    ~/Downloads convention. This is the ONLY call site of label_deliverables.py —
    it was pinned + self-tested + advertised with ZERO callers before this fix."""
    cfg = _json(run_dir, "working/copy/config.json", {}) or {}
    brand = str(cfg.get("brandName", "") or "brand")
    brand_slug = _deliver_slug(brand) or "brand"
    week = _deliver_week(run_dir)

    artifacts = []
    # (a) producer-declared deliverables win (authoritative; missing src => fail-closed).
    declared = _json(run_dir, "working/delivery/deliverables.json")
    if isinstance(declared, list):
        for a in declared:
            if isinstance(a, dict) and a.get("src"):
                artifacts.append(a)
    else:
        # (b) derive from LOCAL media files that actually exist on disk.
        media = run_dir / "working" / "media"
        exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".mov", ".pdf"}
        if media.is_dir():
            for f in sorted(media.rglob("*")):
                if f.is_file() and f.suffix.lower() in exts:
                    artifacts.append({"platform": "asset", "artifact": f.stem,
                                      "aspect": "1x1", "ext": f.suffix.lstrip("."), "src": str(f)})

    plan = _json(run_dir, "working/plan/plan.json", {}) or {}
    theme = str(plan.get("themeOfWeek", "")).strip()
    week_plan_md = "# %s — Week %s\n\n%s\n" % (brand, week, theme or "(weekly social plan)")

    label_manifest = {"brand": brand, "week": week, "artifacts": artifacts,
                      "week_plan_md": week_plan_md}
    lm_path = run_dir / "working" / "delivery" / "label-manifest.json"
    try:
        lm_path.parent.mkdir(parents=True, exist_ok=True)
        lm_path.write_text(json.dumps(label_manifest, indent=2), encoding="utf-8")
    except OSError as exc:
        return False, "AF-SM-DELIVER-MISSING: could not stage the label manifest: %s" % exc

    default_dest = "~/Downloads/Social-Media-in-a-Box"
    physical_dest = os.environ.get("SMIB_DELIVER_DEST", default_dest)
    rc = _run_script("label_deliverables.py",
                     ["--manifest", lm_path, "--dest", physical_dest, "--copy"])
    if rc != 0:
        return False, ("AF-SM-DELIVER-MISSING: label_deliverables.py refused (exit %d) — a declared "
                       "deliverable source is missing on disk (nothing phantom is labeled)" % rc)

    # Deterministic LOGICAL dest root recorded on the certificate (the ~/Downloads
    # convention; independent of any $SMIB_DELIVER_DEST test override).
    dest_root = "%s/%s/%s" % (default_dest, brand_slug, week)
    labels = []
    for a in artifacts:
        try:
            sys.path.insert(0, str(SCRIPTS))
            import label_deliverables as _ld  # noqa: E402
            labels.append(_ld.label_name(brand, week, a.get("day"), a.get("platform", ""),
                                         a.get("artifact", ""), a.get("aspect", "1x1"), a.get("ext", "png")))
        except Exception:  # noqa: BLE001
            pass
    rec = {"dest_root": dest_root, "brand_slug": brand_slug, "week": week,
           "count": len(artifacts), "labels": labels,
           "week_plan": "SMIB_%s_%s_week-plan.md" % (brand_slug, week)}
    try:
        (run_dir / "delivery").mkdir(parents=True, exist_ok=True)
        (run_dir / "delivery" / "deliverables-manifest.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
    except OSError as exc:
        return False, "AF-SM-DELIVER-MISSING: could not record the deliverables manifest: %s" % exc
    return True, ("labeled deliverables written (%d artifact(s) + week-plan) -> %s"
                  % (len(artifacts), dest_root))


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
    "_chk_deferred": _chk_deferred, "_chk_deliver": _chk_deliver,
}


def _run_checker(name, run_dir):
    """FIX-XC-03k: resolve and run a phase checker. An UNMAPPED checker is a DISABLED
    gate — it fails CLOSED (was a silent soft-pass at the call site, so a manifest/
    checker-name drift could quietly no-op a required phase). Enforcement, not
    description: a required gate can never be a silent pass. Mirrors 55's
    run_product_bio._run_checker."""
    fn = _CHECKERS.get(name)
    if fn is None:
        return False, ("checker %s is not mapped — fail-closed (a required gate cannot be a "
                       "silent no-op)" % name)
    return fn(run_dir)

# v0.2.0 modes: engine-driven (v0.1.0) + fold (C3-C7) + creative (M1-M4) + syndicate defer (C9).
MODES = ["week", "day", "carousel", "video", "podcast-cover", "plan", "clean",
         "podcast", "newsletter", "blog", "engage",
         "brief", "campaign", "client-copy", "reactive", "syndicate"]

# DEFER map (fail-closed, clear 'deferred to vX.Y.Z' message; baseline config never blocked).
# F4.3: persona-adapter (C10) is now IMPLEMENTED (scripts/persona_adapter.py) and no
# longer deferred — personaSource:adapter/client-choice run the adapter, not a defer stub.
_DEFERRED = {
    "narrated-video": "0.3.0", "syndicate": "0.4.0",
    "memory-adapter": "0.5.0",
}


def _run_persona_adapter(run_dir: Path) -> bool:
    """F4.3 C10 persona INPUT adapter. Runs BEFORE the phases so downstream
    generation and the certificate can consume the resolved persona.
      personaSource:config        -> baseline no-op (nothing changes).
      personaSource:adapter       -> canonical 5-layer selection (LOGGED).
      personaSource:client-choice -> the client's named persona, FINAL/never judged.
    Returns True to BLOCK the run (an explicitly-requested adapter/client-choice
    that could not resolve — never a silent no-op); False to proceed."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import persona_adapter
        rc = persona_adapter.run(run_dir)
    except Exception as exc:  # noqa: BLE001 — adapter must not crash the run for baseline users
        cfg = _json(run_dir, "working/copy/config.json", {}) if run_dir else {}
        cfg = cfg if isinstance(cfg, dict) else {}
        if str(cfg.get("personaSource", "config")).strip().lower() in ("adapter", "client-choice"):
            print("BLOCKED: personaSource=%r requested but the persona adapter errored (%s). "
                  "Fix and re-run (fail-closed; baseline personaSource:config is never affected)."
                  % (cfg.get("personaSource"), exc), file=sys.stderr)
            return True
        print("[persona-adapter] best-effort skip (%s)" % exc, file=sys.stderr)
        return False
    if rc == persona_adapter.EXIT_UNRESOLVED:
        print("BLOCKED: an explicit persona source was requested but no persona could be "
              "resolved (see message above). Fail-closed; fix config and re-run.", file=sys.stderr)
        return True
    return False


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
    # F4.3: persona-adapter (C10) is IMPLEMENTED — personaSource:adapter no longer
    # defers here; it is handled by _run_persona_adapter() before the phases.
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
        ok, msg = _run_checker(checker, run_dir)
        print("   [%s] %s: %s" % ("OK" if ok else "FAIL", checker, msg))
        gates[pid] = {"passed": bool(ok)}
        # Persist gates BEFORE the manifest phase so build_manifest can read P0..P5.
        if pid != "P6-MANIFEST":
            _write_gates(run_dir, gates)
        if not ok:
            _write_gates(run_dir, gates)
            _LAST_BLOCK.clear()
            _LAST_BLOCK.update({"phase_id": pid, "note": msg})
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


def self_test():
    """Built-in gate self-test (FIX-XC-03k / FIX-XC-11h). Proves: (1) an unmapped
    checker fails CLOSED (was a silent soft-pass); (2) EVERY checker named in
    SOCIAL-MANIFEST.json is mapped in _CHECKERS (a manifest/checker-name drift can
    no longer disable a gate); (3) the P-DELIVER checker labels real artifacts and
    fail-closes on a missing declared source. No nonce/run/provider needed."""
    import tempfile
    ok = True

    def _ck(label, cond):
        nonlocal ok
        cond = bool(cond)
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    good, _ = _run_checker("_chk_does_not_exist", _SKILL_DIR)
    _ck("unmapped checker -> fail-closed (not soft-pass)", good is False)

    manifest = _load_manifest()
    declared = sorted({(ph.get("preflight") or {}).get("checker")
                       for ph in manifest.get("phases", [])
                       if (ph.get("preflight") or {}).get("checker")})
    unmapped = [c for c in declared if c not in _CHECKERS]
    _ck("every manifest checker is mapped (no gate drift): %s" % (unmapped or "all mapped"),
        not unmapped)

    # P-DELIVER golden: a local media file is labeled + copied; dest root recorded.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "media").mkdir(parents=True)
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "plan").mkdir(parents=True)
        (rd / "working" / "copy" / "config.json").write_text(
            json.dumps({"brandName": "Brand One"}), encoding="utf-8")
        (rd / "working" / "plan" / "plan.json").write_text(
            json.dumps({"weekOf": "2026-07-06", "themeOfWeek": "t"}), encoding="utf-8")
        (rd / "working" / "media" / "slide.png").write_bytes(b"\x89PNG stub")
        old = os.environ.get("SMIB_DELIVER_DEST")
        os.environ["SMIB_DELIVER_DEST"] = str(Path(td) / "dl")
        try:
            good, _ = _chk_deliver(rd)
        finally:
            if old is None:
                os.environ.pop("SMIB_DELIVER_DEST", None)
            else:
                os.environ["SMIB_DELIVER_DEST"] = old
        rec = _json(rd, "delivery/deliverables-manifest.json", {})
        _ck("_chk_deliver golden -> PASS + records dest_root",
            good is True and isinstance(rec, dict) and str(rec.get("dest_root", "")).startswith("~/"))

    # P-DELIVER fail-closed: a declared deliverable whose source is missing BLOCKS.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"
        (rd / "working" / "copy").mkdir(parents=True)
        (rd / "working" / "delivery").mkdir(parents=True)
        (rd / "working" / "copy" / "config.json").write_text(
            json.dumps({"brandName": "Brand One"}), encoding="utf-8")
        (rd / "working" / "delivery" / "deliverables.json").write_text(
            json.dumps([{"platform": "tiktok", "artifact": "video", "aspect": "9:16",
                         "ext": "mp4", "src": str(Path(td) / "no-such-file.mp4")}]), encoding="utf-8")
        old = os.environ.get("SMIB_DELIVER_DEST")
        os.environ["SMIB_DELIVER_DEST"] = str(Path(td) / "dl")
        try:
            good, msg = _chk_deliver(rd)
        finally:
            if old is None:
                os.environ.pop("SMIB_DELIVER_DEST", None)
            else:
                os.environ["SMIB_DELIVER_DEST"] = old
        _ck("_chk_deliver missing declared source -> FAIL (AF-SM-DELIVER-MISSING)",
            good is False and "AF-SM-DELIVER-MISSING" in msg)

    print("== run_social_media self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


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


def _mc_board_blocked(run_dir, task_id):
    """FIX-XC-06: on a gate failure, move the card to `blocked` (never `done`) with
    the failing phase + AF code as the note, so a failed run is VISIBLE on the board
    instead of stranding forever at in_progress. FAIL-SOFT — never affects exit code."""
    try:
        sys.path.insert(0, str(SCRIPTS))
        import mc_board
        info = _LAST_BLOCK or {}
        mc_board.block_run(run_dir, task_id, phase_id=info.get("phase_id", ""),
                           note=info.get("note", "a fail-closed gate blocked the run"))
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] blocked best-effort skip (%s)" % exc, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Social Media in a Box orchestrator (Skill 57).")
    ap.add_argument("--mode", choices=MODES)
    ap.add_argument("--run-dir", help="the run directory (contains working/)")
    ap.add_argument("--plan", action="store_true", help="print the mode's phase plan and exit")
    ap.add_argument("--narrated", action="store_true",
                    help="request the narrated video lane (C8) — DEFERRED to v0.3.0 (fails closed)")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in gate self-tests (unmapped-checker + manifest-mapping + P-DELIVER) and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.mode:
        ap.error("--mode is required (or use --self-test)")

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
    # F4.3 — C10 persona INPUT adapter (before phases; fail-closed only when an
    # explicit persona source was requested and could not resolve).
    if _run_persona_adapter(run_dir):
        return EXIT_GATE
    _mc_task = _mc_board_begin(run_dir, args.mode)
    rc = run(manifest, args.mode, run_dir)
    if rc == EXIT_PASS:
        _mc_board_done(run_dir, _mc_task)
    else:
        # A gate failure after the card was opened: mark it blocked so it never
        # strands invisibly at in_progress (FIX-XC-06). FAIL-SOFT.
        _mc_board_blocked(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())
