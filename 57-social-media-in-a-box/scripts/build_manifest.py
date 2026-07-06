#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: BUILD MANIFEST + SIGNED CERTIFICATE
# -----------------------------------------------------------------------------
# DETERMINISTIC, FAIL-CLOSED. The publisher physically cannot run without the
# complete signed manifest this emits. It records / proves:
#   * config hash (secrets EXCLUDED — never hashed-in, never printed)
#   * shipped prompt-file hashes vs the canonical PROMPT-HASHES.json pin  -> AF-SM-PROMPT-HASH
#   * every gate's PASS certificate for the run's declared phases         -> AF-SM-PROCESS-INTEGRITY
#   * a per-call provenance record EXISTS (else zero-Anthropic is a lie)  -> AF-SM-PROVENANCE-MISSING
#   * the model/provider used per call — MUST show ZERO Anthropic         -> AF-SM-NOANTHROPIC
#   * agency isolation: no two roster entries share a pit or locationId   -> AF-SM-AGENCY-SHARED-PIT
# On PASS it writes delivery/PROCESS-CERTIFICATE.{json,md} with a deterministic
# certificate_sha (over the ordered gates + prompt-hash-ok + zero-anthropic +
# the run identity — NOT the wall clock), mirroring run_email_engine's cert.
#
# EXIT: 0 PASS (certificate issued) / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 build_manifest.py --run-dir DIR [--config C.json] [--prompts-dir D]
#           [--canonical PROMPT-HASHES.json] [--sign SIGNER] [--json]
#   python3 build_manifest.py --self-test
# =============================================================================
"""Fail-closed run manifest + signed process certificate for Skill 57."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_PROMPT_HASH = "AF-SM-PROMPT-HASH"
AF_PROCESS = "AF-SM-PROCESS-INTEGRITY"
AF_NOANTHROPIC = "AF-SM-NOANTHROPIC"
AF_AGENCY = "AF-SM-AGENCY-SHARED-PIT"
AF_PROVENANCE = "AF-SM-PROVENANCE-MISSING"
AF_OVERRIDE = "AF-SM-OVERRIDE-UNLOGGED"
AF_CLIENTCOPY = "AF-SM-CLIENT-COPY-MUTATED"

_SKILL_DIR = Path(__file__).resolve().parent.parent
SECRET_FIELDS = ("pit", "openrouterKey", "kieKey", "geminiKey", "accessToken")
# The universal safety spine every certified run must carry, PLUS at least one
# content/media-validation gate. v0.2.0 fold modes (podcast/newsletter/blog) validate
# their content inside their own fold phase, so the required "a contract ran" guarantee
# is satisfied by ANY of these — not P3-CONTRACT specifically (which fold/cover modes omit).
REQUIRED_ALWAYS = ("P0-PREFLIGHT", "P5-SCRUB")
CONTENT_GATES = ("P3-CONTRACT", "P4-MEDIA", "P9-NEWSLETTER", "P10-BLOG", "P11-PODCAST")
_ANTHROPIC_RE = re.compile(
    r"claude-(?:opus|sonnet|haiku|instant|fable|[0-9])|anthropic/claude-(?:[0-9]|opus|sonnet|haiku)"
    r"|us\.anthropic\.claude|sk-ant-|@anthropic-ai/|ANTHROPIC_API_KEY", re.I)


def _sha256_file(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def _config_hash(cfg):
    """Hash the config with secrets EXCLUDED (never hashed-in, never printed)."""
    safe = {k: v for k, v in cfg.items() if k not in SECRET_FIELDS and k != "probes"}
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode("utf-8")).hexdigest()


def check_prompt_hashes(prompts_dir, canonical):
    """Compare shipped prompt hashes to the canonical pin. Missing pin -> record only."""
    fails = []
    pd = Path(prompts_dir)
    shipped = {}
    if pd.is_dir():
        for f in sorted(pd.glob("*.md")):
            shipped[f.name] = _sha256_file(f)
    if canonical and Path(canonical).is_file():
        try:
            pin = json.loads(Path(canonical).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return [(AF_PROMPT_HASH, "cannot read canonical pin: %s" % exc)], shipped
        pinned = pin.get("hashes", pin)
        for name, want in pinned.items():
            got = shipped.get(name)
            if got is None:
                fails.append((AF_PROMPT_HASH, "shipped prompts missing pinned file %s" % name))
            elif got != want:
                fails.append((AF_PROMPT_HASH, "prompt %s hash mismatch vs canonical" % name))
    return fails, shipped


def check_gates(gates):
    fails = []
    if not isinstance(gates, dict) or not gates:
        return [(AF_PROCESS, "no gate results found (working/checkpoints/gates.json)")]
    for phase, rec in gates.items():
        passed = rec.get("passed") if isinstance(rec, dict) else rec
        if passed is not True:
            fails.append((AF_PROCESS, "gate %s did not PASS" % phase))
    for req in REQUIRED_ALWAYS:
        if req not in gates:
            fails.append((AF_PROCESS, "required gate %s absent from the run" % req))
    if not any(g in gates for g in CONTENT_GATES):
        fails.append((AF_PROCESS, "no content/media validation gate ran (one of %s required)"
                      % ", ".join(CONTENT_GATES)))
    return fails


def check_provenance(calls):
    """A ZERO-Anthropic certificate is a FALSE proof without a provenance record.
    The certificate's central claim ('proves ZERO Anthropic per run') can only be
    made if the run recorded which model/provider each call used. An absent or
    empty working/provenance/calls.json is fail-closed -> AF-SM-PROVENANCE-MISSING."""
    if not (isinstance(calls, list) and len(calls) > 0):
        return [(AF_PROVENANCE, "no provenance calls recorded (working/provenance/calls.json); "
                 "cannot certify zero-Anthropic without a per-call model/provider record")]
    return []


def check_no_anthropic(calls):
    """Every recorded model/provider call must be non-Anthropic (G-NOANTHROPIC).

    Two independent tests: (1) the regex over "<model> <provider>" catches
    claude-* / anthropic/claude-* / sk-ant- / @anthropic-ai/ / bedrock ids; and
    (2) an EXACT provider-FIELD test — `{"provider":"anthropic"}` (or "claude")
    paired with a NON-claude model id (e.g. a bare model name) sails past the
    regex, so the provider field is matched directly. Either trip is a hard
    AF-SM-NOANTHROPIC (fail-closed)."""
    fails = []
    models = []
    for c in calls or []:
        if not isinstance(c, dict):
            continue
        model = str(c.get("model", ""))
        provider = str(c.get("provider", ""))
        models.append(model)
        blob = "%s %s" % (model, provider)
        if _ANTHROPIC_RE.search(blob):
            fails.append((AF_NOANTHROPIC, "call %r used an Anthropic model/provider" % c.get("step", "?")))
        elif provider.strip().lower() in ("anthropic", "claude"):
            # exact provider-field match (the regex misses a bare {provider:"anthropic"}
            # carrying a non-claude model id) — still a client-path Anthropic call.
            fails.append((AF_NOANTHROPIC, "call %r declares provider %r (exact provider-field match)"
                          % (c.get("step", "?"), provider)))
    return fails, models


def check_agency_isolation(cfg):
    fails = []
    if cfg.get("mode") != "agency":
        return fails
    roster = cfg.get("roster")
    rf = cfg.get("rosterFile")
    if roster is None and rf and Path(rf).is_file():
        try:
            roster = json.loads(Path(rf).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            roster = None
    if not isinstance(roster, list) or not roster:
        return [(AF_AGENCY, "agency mode but no roster[] found")]
    seen_pit, seen_loc = {}, {}
    for i, entry in enumerate(roster, 1):
        if not isinstance(entry, dict):
            continue
        pit = entry.get("pit")
        loc = entry.get("locationId")
        if pit in seen_pit:
            fails.append((AF_AGENCY, "roster entries %d and %d share a Private Integration Token"
                          % (seen_pit[pit], i)))
        elif pit is not None:
            seen_pit[pit] = i
        if loc in seen_loc:
            fails.append((AF_AGENCY, "roster entries %d and %d share a locationId" % (seen_loc[loc], i)))
        elif loc is not None:
            seen_loc[loc] = i
    return fails


def check_overrides_logged(run_dir):
    """AF-SM-OVERRIDE-UNLOGGED (creative layer §4.3 step 5 / §6 step 5).

    Deviation is FREE (the client gets EXACTLY what they ask for, never floored or
    capped); a SILENT deviation is the only forbidden one. The prover records which
    bands it actually overrode into working/creative/applied.json (a list of band
    keys). Every applied band MUST have a matching logged entry in working/creative/
    overrides.json (who asked, verbatim ask, scope) or the certificate is refused."""
    applied = _read_json(Path(run_dir) / "working" / "creative" / "applied.json", [])
    logged = _read_json(Path(run_dir) / "working" / "creative" / "overrides.json", {})
    applied = applied if isinstance(applied, list) else []
    logged_keys = set(logged.keys()) if isinstance(logged, dict) else set()
    fails = []
    for band in applied:
        if band not in logged_keys:
            fails.append((AF_OVERRIDE, "band override %r was applied without a logged "
                          "overrides.json entry (silent deviation forbidden)" % band))
    return fails, (logged if isinstance(logged, dict) else {})


def check_client_copy(run_dir, cta=""):
    """AF-SM-CLIENT-COPY-MUTATED (M3 / injection point I6).

    Protects the CLIENT's creativity FROM the engine: in client-copy mode the published
    bytes MUST equal the client's supplied copy, modulo a programmatic ctaLink APPEND.
    The engine may only APPEND (never edit or truncate the client's words). Absent
    working/creative/client-copy/ -> not a client-copy run -> nothing to check."""
    d = Path(run_dir) / "working" / "creative" / "client-copy"
    fails, shas = [], []
    if not d.is_dir():
        return fails, shas
    cta = str(cta or "")
    for f in sorted(d.glob("*.json")):
        rec = _read_json(f, {}) or {}
        supplied = str(rec.get("supplied") or rec.get("copy") or rec.get("body") or "")
        shas.append(hashlib.sha256(supplied.encode("utf-8")).hexdigest())
        published = rec.get("published")
        if published is None:
            continue  # not yet published; the guarantee is checked once bytes exist
        pub = str(published)
        if pub == supplied:
            continue
        if pub.startswith(supplied):
            remainder = pub[len(supplied):]
            if remainder.strip() == "" or (cta and cta in remainder):
                continue  # engine only APPENDED (whitespace / the configured ctaLink)
        fails.append((AF_CLIENTCOPY, "%s: published bytes do not match the client's supplied copy "
                      "(the engine may only APPEND a ctaLink, never edit the client's words)" % f.name))
    return fails, shas


def _read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build(run_dir, config=None, prompts_dir=None, canonical=None, signer="social-media-in-a-box"):
    run_dir = Path(run_dir)
    cfg = _read_json(config) if config else _read_json(run_dir / "working" / "copy" / "config.json", {})
    cfg = cfg if isinstance(cfg, dict) else {}
    gates = _read_json(run_dir / "working" / "checkpoints" / "gates.json", {})
    calls = _read_json(run_dir / "working" / "provenance" / "calls.json", [])

    fails = []
    ph_fails, shipped_hashes = check_prompt_hashes(prompts_dir or (_SKILL_DIR / "prompts"),
                                                   canonical or (_SKILL_DIR / "PROMPT-HASHES.json"))
    fails += ph_fails
    fails += check_gates(gates if isinstance(gates, dict) else {})
    fails += check_provenance(calls if isinstance(calls, list) else [])
    na_fails, models = check_no_anthropic(calls if isinstance(calls, list) else [])
    fails += na_fails
    fails += check_agency_isolation(cfg)
    ov_fails, logged_overrides = check_overrides_logged(run_dir)
    fails += ov_fails
    cc_fails, client_copy_shas = check_client_copy(run_dir, cfg.get("ctaLink", ""))
    fails += cc_fails

    creative = _creative_block(run_dir, cfg, logged_overrides, client_copy_shas)

    # FIX-XC-11h: record WHERE the run's labeled local deliverables landed. The
    # P-DELIVER checker (run_social_media._chk_deliver) shells label_deliverables.py
    # --copy and writes delivery/deliverables-manifest.json with a deterministic
    # LOGICAL dest_root (the ~/Downloads convention, never a physical temp path).
    # Absent (fold/plan/engage modes that ship no local media) -> None. Recorded on
    # the certificate but NOT bound into certificate_sha (it is provenance, not a gate).
    deliver_rec = _read_json(run_dir / "delivery" / "deliverables-manifest.json", {}) or {}
    deliverable_dest_root = deliver_rec.get("dest_root") if isinstance(deliver_rec, dict) else None

    manifest = {
        "schema": "social-media-process-certificate-v1",
        "skill": "social-media-in-a-box", "skill_number": 57,
        "brand_slug": re.sub(r"[^a-z0-9]+", "-", str(cfg.get("brandName", "")).lower()).strip("-"),
        "mode": cfg.get("mode", "single-brand"),
        "config_hash": _config_hash(cfg),
        "prompt_hashes": shipped_hashes,
        "prompt_hashes_ok": not ph_fails,
        "gates": gates,
        "models_used": models,
        "zero_anthropic": not na_fails,
        "agency_isolation_ok": not any(c == AF_AGENCY for c, _ in fails),
        "all_gates_pass": not any(c == AF_PROCESS for c, _ in fails),
        "creative": creative,
        "overrides_logged_ok": not ov_fails,
        "client_copy_verbatim_ok": not cc_fails,
        "deliverable_dest_root": deliverable_dest_root,
        "signer": signer,
        "deploy_mode": "publish-on-cert",
        "failures": [{"code": c, "message": m} for c, m in fails],
        "pass": not fails,
    }
    sha_src = json.dumps({
        "cfg": manifest["config_hash"],
        "prompts": sorted(shipped_hashes.items()),
        "gates": sorted((k, bool(v.get("passed") if isinstance(v, dict) else v)) for k, v in
                        (gates.items() if isinstance(gates, dict) else [])),
        "zero_anthropic": manifest["zero_anthropic"],
        "prompt_hashes_ok": manifest["prompt_hashes_ok"],
        "creative": creative,  # the certificate binds BOTH "nothing unsafe" AND "exactly what was asked"
    }, sort_keys=True)
    manifest["certificate_sha"] = hashlib.sha256(sha_src.encode("utf-8")).hexdigest()
    return manifest, fails


def _canonical_persona(run_dir):
    """The C10 adapter's resolved canonical persona for the certificate, or None
    for the baseline (config) path. Compact shape — id, name, source, mode — read
    from working/copy/persona-selection.json (written by persona_adapter.py)."""
    sel = _read_json(Path(run_dir) / "working" / "copy" / "persona-selection.json")
    if not isinstance(sel, dict) or sel.get("error"):
        return None
    pid = sel.get("persona_id")
    gov = sel.get("governance_persona_id")
    if not pid and not gov:
        return None
    return {
        "persona_id": pid,
        "persona_name": sel.get("persona_name"),
        "persona_source": sel.get("source"),
        "no_persona_required": bool(sel.get("no_persona_required")),
        "governance_persona_id": gov,
    }


def _creative_block(run_dir, cfg, logged_overrides, client_copy_shas):
    """The signed certificate's `creative` block (§6 step 6). Proves the client got
    EXACTLY what they asked for: mode, brief sha, theme source, per-band logged
    overrides, client-copy shas, persona source, em-dash policy, series length, arc,
    style pick. Defaults reproduce a v0.1.0 default week byte-for-byte."""
    cre = _read_json(Path(run_dir) / "working" / "creative" / "creative.json", {}) or {}
    brief = _read_json(Path(run_dir) / "working" / "creative" / "brief.json")
    brief_sha = None
    if isinstance(brief, (dict, list)):
        brief_sha = hashlib.sha256(json.dumps(brief, sort_keys=True).encode("utf-8")).hexdigest()
    block = {
        "mode": cre.get("mode"),
        "theme_source": cre.get("theme_source"),
        "brief_sha": brief_sha,
        "overrides": logged_overrides,
        "client_copy_shas": client_copy_shas,
        "persona_source": cfg.get("personaSource", "config"),
        "em_dash_policy": cfg.get("emDashPolicy", "ban-all"),
        "series_length": cfg.get("seriesLength", 7),
        "arc_template": cfg.get("arcTemplate", "tv-season"),
        "style_pick": cfg.get("stylePick"),
    }
    # F4.3 — surface the C10-adapter's resolved canonical persona on the certificate
    # WHEN one was resolved (personaSource:adapter/client-choice). The baseline
    # personaSource:config path writes no persona-selection.json, so this key is
    # ABSENT there and a default week's creative block stays byte-for-byte identical.
    cp = _canonical_persona(run_dir)
    if cp:
        block["canonical_persona"] = cp
    return block


def _write_certificate(run_dir, manifest):
    out_dir = Path(run_dir) / "delivery"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        md = [
            "# Social Media in a Box — PROCESS CERTIFICATE",
            "",
            "- **Skill:** 57 (social-media-in-a-box)",
            "- **Brand slug:** %s" % manifest["brand_slug"],
            "- **Mode:** %s" % manifest["mode"],
            "- **Config hash (secrets excluded):** `%s`" % manifest["config_hash"],
            "- **Prompt hashes match canonical:** %s" % manifest["prompt_hashes_ok"],
            "- **All gates pass:** %s" % manifest["all_gates_pass"],
            "- **ZERO Anthropic in run:** %s" % manifest["zero_anthropic"],
            "- **Agency isolation OK:** %s" % manifest["agency_isolation_ok"],
            "- **Overrides logged OK:** %s" % manifest.get("overrides_logged_ok", True),
            "- **Client-copy verbatim OK:** %s" % manifest.get("client_copy_verbatim_ok", True),
            "- **Creative (frame proven, picture free):** mode=%s theme_source=%s persona=%s "
            "em_dash=%s series_len=%s arc=%s" % (
                manifest["creative"].get("mode"), manifest["creative"].get("theme_source"),
                manifest["creative"].get("persona_source"), manifest["creative"].get("em_dash_policy"),
                manifest["creative"].get("series_length"), manifest["creative"].get("arc_template")),
            "- **Models used:** %s" % ", ".join(manifest["models_used"] or ["(none recorded)"]),
        ] + ([
            "- **Labeled deliverables dest root:** `%s`" % manifest["deliverable_dest_root"],
        ] if manifest.get("deliverable_dest_root") else []) + [
            "- **Certificate SHA:** `%s`" % manifest["certificate_sha"],
            "",
            "Issued by `build_manifest.py`. The publisher (P7) refuses to run without this "
            "certificate. Client runtime uses the client's OWN provider chain — the "
            "`zero_anthropic` proof above is a hard gate. `done` is claimed only from this "
            "certificate plus a live GHL post-listing verify.",
        ]
        (out_dir / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    except OSError:
        pass


def _emit(manifest, fails, as_json):
    if as_json:
        print(json.dumps(manifest, indent=2))
        return
    print("== Social Media in a Box :: build manifest + certificate ==")
    print("zero_anthropic: %s  prompt_hashes_ok: %s  all_gates_pass: %s  agency_ok: %s"
          % (manifest["zero_anthropic"], manifest["prompt_hashes_ok"],
             manifest["all_gates_pass"], manifest["agency_isolation_ok"]))
    if not fails:
        print("RESULT: PASS — certificate SHA %s (publisher unlocked)." % manifest["certificate_sha"][:12])
    else:
        print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(fails))
        for c, m in fails:
            print("  [%s] %s" % (c, m))


def run(run_dir, config=None, prompts_dir=None, canonical=None, signer=None, as_json=False):
    rd = Path(run_dir)
    if not rd.is_dir():
        print("FATAL: --run-dir not found: %s" % rd, file=sys.stderr)
        return EXIT_USAGE
    manifest, fails = build(rd, config, prompts_dir, canonical, signer or "social-media-in-a-box")
    if not fails:
        _write_certificate(rd, manifest)
    _emit(manifest, fails, as_json)
    return EXIT_PASS if not fails else EXIT_AUTOFAIL


# =============================================================================
# SELF-TEST — temp run-dir fixtures.
# =============================================================================
def _mk_run(tmp, gates, calls, cfg, prompts=None, creative=None):
    rd = Path(tmp)
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "provenance").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "checkpoints" / "gates.json").write_text(json.dumps(gates), encoding="utf-8")
    (rd / "working" / "provenance" / "calls.json").write_text(json.dumps(calls), encoding="utf-8")
    (rd / "working" / "copy" / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if creative:
        cd = rd / "working" / "creative"
        cd.mkdir(parents=True, exist_ok=True)
        for rel, obj in creative.items():
            p = cd / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(obj), encoding="utf-8")
    pd = rd / "prompts"
    pd.mkdir(exist_ok=True)
    prompts = prompts or {"01.md": "hello"}
    for name, body in prompts.items():
        (pd / name).write_text(body, encoding="utf-8")
    pin = {"hashes": {name: hashlib.sha256(body.encode()).hexdigest() for name, body in prompts.items()}}
    (rd / "PROMPT-HASHES.json").write_text(json.dumps(pin), encoding="utf-8")
    return rd


def self_test():
    ok = True
    good_gates = {"P0-PREFLIGHT": {"passed": True}, "P2-CONTENT": {"passed": True},
                  "P3-CONTRACT": {"passed": True}, "P4-MEDIA": {"passed": True},
                  "P5-SCRUB": {"passed": True}}
    good_calls = [{"step": "core-concept", "provider": "openrouter", "model": "google/gemini-2.0-flash-001"},
                  {"step": "reformat", "provider": "openrouter", "model": "meta-llama/llama-3.1-70b"},
                  {"step": "grid-judge", "provider": "google", "model": "gemini-2.0-flash"}]
    good_cfg = {"brandName": "Brand One", "mode": "single-brand"}

    def build_at(gates, calls, cfg, prompts=None, creative=None):
        d = tempfile.mkdtemp(prefix="smib-mani-")
        rd = _mk_run(d, gates, calls, cfg, prompts, creative)
        return build(rd, config=None, prompts_dir=rd / "prompts", canonical=rd / "PROMPT-HASHES.json")

    def cp(name, gates, calls, cfg, prompts=None, creative=None):
        nonlocal ok
        _m, fails = build_at(gates, calls, cfg, prompts, creative)
        good = not fails
        ok = ok and good
        print("  [%s] VALID %-24s -> %s" % ("PASS" if good else "MISS", name, "" if good else fails[:3]))

    def cf(name, gates, calls, cfg, expect, prompts=None, creative=None):
        nonlocal ok
        _m, fails = build_at(gates, calls, cfg, prompts, creative)
        codes = [c for c, _ in fails]
        good = expect in codes
        ok = ok and good
        print("  [%s] VIOLATION %-20s -> has %s %s" % ("PASS" if good else "MISS", name, expect,
              "" if good else codes))

    print("== self-test: VALID (certificate issues) ==")
    cp("all-green", good_gates, good_calls, good_cfg)
    # fold mode: podcast (P11) certifies without P3-CONTRACT (fold phase validated content)
    fold_gates = {"P0-PREFLIGHT": {"passed": True}, "P11-PODCAST": {"passed": True},
                  "P5-SCRUB": {"passed": True}}
    cp("fold-podcast-no-p3", fold_gates, good_calls, good_cfg)
    # creative: a LOGGED band override + a VERBATIM client-copy record both certify
    cp("logged-override", good_gates, good_calls, good_cfg, creative={
        "applied.json": ["caption_fb_ig"],
        "overrides.json": {"caption_fb_ig": {"applied": [2000, 2400], "scope": "run",
                           "asked_by": "owner", "verbatim": "make captions ~2,200 chars this week"}}})
    cp("client-copy-verbatim", good_gates, good_calls,
       dict(good_cfg, ctaLink="\n\nJoin: https://x/y"), creative={
        "client-copy/mon.json": {"platform": "instagram", "supplied": "post this exactly",
                                 "published": "post this exactly\n\nJoin: https://x/y"}})

    print("== self-test: VIOLATION (fail-closed, no cert) ==")
    # AF-SM-OVERRIDE-UNLOGGED: a band was overridden with NO logged entry (silent deviation)
    cf("override-unlogged", good_gates, good_calls, good_cfg, AF_OVERRIDE, creative={
        "applied.json": ["caption_fb_ig", "hashtags_linkedin"],
        "overrides.json": {"caption_fb_ig": {"applied": [2000, 2400], "scope": "run"}}})
    # AF-SM-CLIENT-COPY-MUTATED: the engine EDITED the client's words (not just appended)
    cf("client-copy-mutated", good_gates, good_calls, good_cfg, AF_CLIENTCOPY, creative={
        "client-copy/mon.json": {"platform": "instagram", "supplied": "post this exactly",
                                 "published": "post this DIFFERENTLY now"}})
    g = dict(good_gates); g["P3-CONTRACT"] = {"passed": False}
    cf("gate-failed", g, good_calls, good_cfg, AF_PROCESS)
    g = dict(good_gates); del g["P5-SCRUB"]
    cf("required-gate-absent", g, good_calls, good_cfg, AF_PROCESS)
    bad_calls = good_calls + [{"step": "rogue", "provider": "anthropic", "model": "claude-opus-4-8"}]
    cf("anthropic-call", good_gates, bad_calls, good_cfg, AF_NOANTHROPIC)
    # FIX-XC-09c: a bare {provider:"anthropic"} carrying a NON-claude model id sails
    # past the regex; the exact provider-FIELD test must still trip AF-SM-NOANTHROPIC.
    field_calls = good_calls + [{"step": "rogue", "provider": "anthropic", "model": "some-internal-model"}]
    cf("anthropic-provider-field", good_gates, field_calls, good_cfg, AF_NOANTHROPIC)
    field_calls2 = good_calls + [{"step": "rogue", "provider": "Claude", "model": "gpt-x"}]
    cf("claude-provider-field", good_gates, field_calls2, good_cfg, AF_NOANTHROPIC)
    agency_cfg = {"brandName": "Agency", "mode": "agency",
                  "roster": [{"pit": "pit-a", "locationId": "loc1"}, {"pit": "pit-a", "locationId": "loc2"}]}
    cf("agency-shared-pit", good_gates, good_calls, agency_cfg, AF_AGENCY)
    cf("provenance-missing", good_gates, [], good_cfg, AF_PROVENANCE)

    # prompt-hash mismatch: tamper a shipped prompt after the pin is written
    d = tempfile.mkdtemp(prefix="smib-mani-")
    rd = _mk_run(d, good_gates, good_calls, good_cfg, {"01.md": "original"})
    (rd / "prompts" / "01.md").write_text("TAMPERED", encoding="utf-8")
    _m, fails = build(rd, prompts_dir=rd / "prompts", canonical=rd / "PROMPT-HASHES.json")
    good = AF_PROMPT_HASH in [c for c, _ in fails]
    ok = ok and good
    print("  [%s] VIOLATION prompt-hash-mismatch  -> has %s" % ("PASS" if good else "MISS", AF_PROMPT_HASH))

    # determinism: same inputs => same certificate_sha
    m1, _ = build_at(good_gates, good_calls, good_cfg)
    m2, _ = build_at(good_gates, good_calls, good_cfg)
    good = m1["certificate_sha"] == m2["certificate_sha"]
    ok = ok and good
    print("  [%s] certificate_sha deterministic" % ("PASS" if good else "MISS"))

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed run manifest + signed certificate (Skill 57).")
    ap.add_argument("--run-dir")
    ap.add_argument("--config")
    ap.add_argument("--prompts-dir")
    ap.add_argument("--canonical")
    ap.add_argument("--sign", dest="signer")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.run_dir:
        ap.error("--run-dir is required (or use --self-test)")
    return run(args.run_dir, config=args.config, prompts_dir=args.prompts_dir,
               canonical=args.canonical, signer=args.signer, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
