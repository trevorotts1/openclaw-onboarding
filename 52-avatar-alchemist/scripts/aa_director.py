#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aa_director.py — the Avatar-Alchemist foreman (Skill 52).

Schedules the 40-generator BRAND pipeline in dependency waves computed from
AA-PIPELINE-MANIFEST.json `depends_on` (the digest-verified DAG), throttled to
min(slots, provider_cap). Dispatches ONE sub-agent per stage with only that
stage's three prompt files + its resolved dependency artifacts, and REFUSES to
dispatch any stage whose depends_on receipts are missing. Idempotent on
RUN-LEDGER.json (--resume never re-generates a verified stage). Parks fail-closed
on non-recoverable conditions. Issues the signed certificate only when every
phase passes (delegates the gate to aa_delivery_gate.py).

Front-door nonce: a real run REQUIRES the one-time nonce entry.sh minted this run.
But the nonce is a PRESENCE check only (a 48-char hex string is trivial to
hand-write) — so a real dispatch does NOT trust "entry.sh must have run because
a nonce file exists." Instead, at every real dispatch this module RE-VERIFIES,
in-process, right now: gate-integrity (pinned hashes), the stdlib-only dep
scan, the Anthropic-id bypass-scan, and the egress scan (aa_egress_gate.py).
A hand-forged `printf 'XXXXXXXXXXXXXXXX' > .entry-nonce` no longer buys a
dispatch: the SAME checks entry.sh runs are re-run here, unconditionally,
regardless of how aa_director.py was invoked.

version=book is REFUSED here in code, not by procedure: before any dispatch,
this module loads `<run-dir>/intake.json` and runs aa_intake_gate.verify().
A non-'brand' version, or ANY intake violation, hard-stops with NO dispatch —
the 40-stage brand pipeline is structurally unreachable for a book intake, it
is not merely discouraged by INSTRUCTIONS.md. A machine-readable route signal
is written to `<run-dir>/route.json` either way.

This module's deterministic scheduling core is fully self-tested offline; the LLM
dispatch itself is the OpenClaw sub-agent seam (client providers only).

Repairs R1-R6 (see REPAIRS.md) are OFF BY DEFAULT so a run is FAITHFUL to Trevor's
original LIVE workflow output. --apply-repairs opts INTO them; the foreman records
the mode in RUN-LEDGER.json and prepends a mode banner to every dispatched stage so
sub-agents follow the live behavior (default) or apply the 'REPAIR R#' directives
(opt-in). R7 (the Anthropic ban) is NOT a fidelity repair and is ALWAYS enforced.

Exit 0 = ok/brand-dispatch, 2 = schedule/precedence/front-door/intake violation,
3 = usage/IO error, 4 = version=book correctly ROUTED or PARKED (hard-stop, by
design — this is not a failure, it is the version gate doing its job).
Flags: --plan --dry-run --status --resume --recover --fast-ads --apply-repairs --self-test
"""
from __future__ import annotations
import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aa_gate_integrity_check as gic   # noqa: E402
import aa_intake_gate as intake_gate    # noqa: E402
import aa_egress_gate as egress_gate    # noqa: E402
import aa_links_gate as links_gate      # noqa: E402


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "AA-PIPELINE-MANIFEST.json"


AD_TAIL = [f"{n:02d}-ad-set-{n-21}" for n in range(23, 35)]  # ad sets 2..13 (fast-ads collapse targets)


def dispatch_preamble(apply_repairs: bool) -> str:
    """The mode banner the foreman prepends to EVERY dispatched stage. It governs
    whether the sub-agent applies the baked 'REPAIR R#' directives. Default = OFF
    (faithful to the live workflow); --apply-repairs turns them ON. R7 (Anthropic
    ban) is unconditional and stated in both modes."""
    if apply_repairs:
        return ("MODE: repairs ON (--apply-repairs). APPLY every 'REPAIR R#' directive in this "
                "prompt (R1 blended-tone gets the 4 tone ANALYSIS docs; R2 solution-aware-pt2 "
                "injects the Solution-Aware doc; R3 cheat-sheet references the 7-Tier framework; "
                "R4 each ad set uses its TRUE restored category; R5 fill the product/offer line; "
                "R6 the hero uses the Answer-9 doc). R7: NEVER emit an Anthropic/claude model id.")
    return ("MODE: faithful-live (repairs OFF, default). IGNORE every 'REPAIR R#' directive and "
            "reproduce the ORIGINAL live behavior (R1 blended-tone gets only the tone-style NAMES; "
            "R2 solution-aware-pt2 keeps the source Problem-Aware injection; R3 leaves the cheat-sheet "
            "as source; R4 ad sets follow the source 'category 2' wiring; R5 leaves the product line "
            "as source; R6 the Answer-9 doc stays unused). R7: NEVER emit an Anthropic/claude model id.")


# ===========================================================================
# FIX-XC-05b — the real dispatch loop ("fortress with no army" fix). Converts
# the five schedule/precedence/token/receipt/model conventions from prose into
# ENFORCEMENT: for every wave/stage the foreman refuses on a missing dep
# receipt, loads + token-resolves that stage's three prompt files, prepends the
# repairs banner, dispatches to the CLIENT model via one documented adapter
# seam, and writes the artifact + an HMAC-signed receipt + a ledger row bearing
# the REAL model id the dispatch returned. --resume skips receipted stages,
# per-stage recovery/max_fix_attempts drive a redo-then-PARK loop, and stage-02
# completion runs the links gate (--online on client boxes).
#
# The LLM call itself is the ONLY non-deterministic seam and is isolated behind
# `--dispatch-cmd` (a client-provided command: prompt on stdin, JSON
# {"text","model"} on stdout) or the documented `openclaw agent --json`
# default. Everything around it — precedence, substitution, provenance,
# provider purity, parking, idempotent resume — is deterministic and self-tested
# offline with a mock adapter.
# ===========================================================================
_INTAKE_TOKEN_RE = re.compile(r"\{\{intake\.([A-Za-z0-9_]+)\}\}")
_ARTIFACT_TOKEN_RE = re.compile(r"\{\{artifact\.([0-9A-Za-z\-]+)\}\}")
_LEFTOVER_TOKEN_RE = re.compile(r"\{\{(?!contact\.)[^}]+\}\}")


class DispatchError(RuntimeError):
    """A stage dispatch failed (adapter error or output failed post-check)."""


def substitute_tokens(text: str, intake: Dict[str, Any], artifacts: Dict[str, str]) -> str:
    """Resolve {{intake.<key>}} from intake.json and {{artifact.<stage_id>}} from
    the already-generated upstream artifacts. A referenced artifact that is not
    present is a HARD error (the precedence guard should have prevented it)."""
    def _i(m: "re.Match[str]") -> str:
        return str(intake.get(m.group(1), ""))

    def _a(m: "re.Match[str]") -> str:
        sid = m.group(1)
        if sid not in artifacts:
            raise DispatchError(f"prompt references artifact {sid!r} which is not on disk")
        return artifacts[sid]

    return _ARTIFACT_TOKEN_RE.sub(_a, _INTAKE_TOKEN_RE.sub(_i, text))


def _resolve_positional_upstream(text: str, depends_on: List[str], artifacts: Dict[str, str]) -> str:
    """Resolve the SANCTIONED generic {{artifact.upstream}} token used ONLY by the
    shared tone-core stages (04-07, byte-for-byte canonical IP). Each occurrence,
    in document order, is bound to depends_on[k]. Safe ONLY because the lockstep
    prover guarantees the occurrence count equals len(depends_on)."""
    n = text.count("{{artifact.upstream}}")
    if n == 0:
        return text
    if n != len(depends_on):
        raise DispatchError(f"{n} {{{{artifact.upstream}}}} tokens but {len(depends_on)} deps — "
                            f"not positionally resolvable (lockstep should have caught this)")
    out: List[str] = []
    pos = 0
    for k in range(n):
        j = text.find("{{artifact.upstream}}", pos)
        out.append(text[pos:j])
        sid = depends_on[k]
        if sid not in artifacts:
            raise DispatchError(f"positional upstream dep {sid!r} not on disk")
        out.append(artifacts[sid])
        pos = j + len("{{artifact.upstream}}")
    out.append(text[pos:])
    return "".join(out)


def compose_prompt(root: Path, sid: str, intake: Dict[str, Any], artifacts: Dict[str, str],
                   apply_repairs: bool, depends_on: Optional[List[str]] = None) -> str:
    """Load the stage's three prompt files (system/methodology/user), prepend the
    mode banner, and token-resolve the whole thing so the dispatched prompt is
    self-contained (zero unresolved {{...}} left)."""
    d = root / "prompts" / sid
    parts: List[str] = []
    for fn in ("system.md", "methodology.md", "user.md"):
        p = d / fn
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    composed = dispatch_preamble(apply_repairs) + "\n\n" + "\n\n".join(parts)
    # positional {{artifact.upstream}} (shared tone-core stages) first, then the
    # named {{artifact.<sid>}} / {{intake.<key>}} substitutions.
    composed = _resolve_positional_upstream(composed, depends_on or [], artifacts)
    resolved = substitute_tokens(composed, intake, artifacts)
    return resolved


def _receipt_sig(key: bytes, rec: Dict[str, Any]) -> str:
    body = {k: v for k, v in rec.items() if k != "sig"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canon.encode("utf-8"), hashlib.sha256).hexdigest()


def _receipt_verified(run_dir: Path, sid: str, key: Optional[bytes]) -> bool:
    """A stage is 'done' iff its on-disk artifact + receipt exist, the receipt's
    sha256 matches the artifact bytes, AND (if a run key is available) the
    receipt's HMAC signature verifies. This is what makes --resume safe and what
    catches a receipt/artifact tampered-with between runs."""
    ap = run_dir / "artifacts" / f"{sid}.md"
    rp = run_dir / "receipts" / f"G-STAGE-{sid}.json"
    if not ap.is_file() or not rp.is_file():
        return False
    try:
        rec = json.loads(rp.read_text(encoding="utf-8"))
        actual = hashlib.sha256(ap.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    except (OSError, ValueError):
        return False
    if rec.get("sha256") != actual:
        return False
    if key is not None and rec.get("sig"):
        if not hmac.compare_digest(_receipt_sig(key, rec), str(rec["sig"])):
            return False
    return True


def _dispatch(prompt: str, sid: str, model_hint: str, dispatch_cmd: Optional[str]) -> Tuple[str, str]:
    """The ONE adapter seam. With --dispatch-cmd, run that command (prompt on
    stdin) and parse JSON {"text","model"} from stdout. Otherwise fall back to
    the documented `openclaw agent --json` client-provider path. Never invokes
    an Anthropic endpoint — the returned model id is G-NOANTHROPIC-checked by the
    caller."""
    env = {**os.environ, "AA_STAGE": sid, "AA_MODEL_HINT": model_hint}
    if dispatch_cmd:
        proc = subprocess.run(dispatch_cmd, shell=True, input=prompt, capture_output=True,
                              text=True, env=env)
        if proc.returncode != 0:
            raise DispatchError(f"--dispatch-cmd rc={proc.returncode}: {proc.stderr.strip()[:200]}")
        raw = proc.stdout
    else:  # documented default seam (client providers only)
        argv = ["openclaw", "agent", "--json", "--stage", sid]
        if model_hint:
            argv += ["--model", model_hint]
        proc = subprocess.run(argv, input=prompt, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            raise DispatchError(f"openclaw agent rc={proc.returncode}: {proc.stderr.strip()[:200]}")
        raw = proc.stdout
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise DispatchError(f"dispatch output is not JSON: {exc}") from exc
    text = data.get("text")
    model = str(data.get("model", "")).strip()
    if not isinstance(text, str) or not text.strip():
        raise DispatchError("dispatch returned empty/absent 'text'")
    return text, model


def _stage_output_ok(text: str) -> bool:
    return bool(text.strip()) and not _LEFTOVER_TOKEN_RE.search(text)


def _park(run_dir: Path, sid: str, reason: str) -> None:
    rec = {"parked_stage": sid, "reason": reason,
           "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (run_dir / "PARKED.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"PARKED at {sid}: {reason} (see PARKED.json)")


# FIX-XC-09f — model-map is CONSUMED here (it used to be written by preflight.sh
# and read by nothing). At dispatch time the foreman loads the box's own
# model-map.json (the CLIENT's configured provider tiers, minted by preflight.sh
# from the box's real OpenClaw config — NEVER Anthropic), resolves each stage's
# declared tier (A/B/SEARCH) to the box's concrete model id, defaults the
# provider cap from provider_caps.concurrent (the fleet <=3-Ollama provisioning
# rule, not the old hardcoded 10), and records the resolved tier ids in
# RUN-LEDGER.json so provenance shows the ACTUAL model each stage was routed to.
DEFAULT_PROVIDER_CAP = 3  # fleet Ollama-only provisioning rule when no model-map resolves a cap (never 10)
_ABSTRACT_TIER_HINT = {"A": "tier-a", "B": "tier-b", "SEARCH": "tier-search"}


def load_model_map(run_dir: Optional[Path], root: Path) -> Optional[Dict[str, Any]]:
    """Locate + load the box's model-map.json (written by preflight.sh from the
    CLIENT's own configured providers). Search order: $AA_MODEL_MAP, then
    <run-dir>/model-map.json, then <skill-root>/model-map.json. Returns the parsed
    map (with a `_source` key added) or None when the box has no map yet (the
    foreman then falls back to abstract tier hints + the conservative default cap).
    Defense-in-depth: a map carrying an Anthropic-shaped tier id is REFUSED here
    (raises) — preflight already bans it, but the consumer never trusts that."""
    candidates: List[Path] = []
    env_path = os.environ.get("AA_MODEL_MAP")
    if env_path:
        candidates.append(Path(env_path))
    if run_dir is not None:
        candidates.append(run_dir / "model-map.json")
    candidates.append(root / "model-map.json")
    for p in candidates:
        if not p.is_file():
            continue
        try:
            mm = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for tier, tid in (mm.get("tiers") or {}).items():
            if _ANTHROPIC_ID_RE.search(str(tid)):
                raise ValueError(
                    f"AF-AV-NOANTHROPIC: model-map tier {tier}={tid!r} matches the Anthropic ban "
                    f"(client-path rule) — refusing to consume {p}")
        mm["_source"] = str(p)
        return mm
    return None


def _provider_cap_from_map(mm: Optional[Dict[str, Any]]) -> int:
    """Default the provider cap from the model-map's provider_caps.concurrent
    (the box's own Ollama-only <=3 rule). Absent a map, fall back to the
    conservative fleet default — NEVER the old hardcoded 10."""
    if mm:
        try:
            c = int((mm.get("provider_caps") or {}).get("concurrent"))
            if c > 0:
                return c
        except (TypeError, ValueError):
            pass
    return DEFAULT_PROVIDER_CAP


def _resolve_tier_id(stage: Dict[str, Any], model_map: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    """Resolve the stage's declared tier (A/B/SEARCH) to (tier_letter, model_id).
    With a model-map present the tier resolves to the box's OWN concrete id (the
    client's configured provider, never a hardcoded Anthropic id); absent a map the
    id is the abstract 'tier-a' hint the adapter may honor (unchanged legacy seam)."""
    tier = str(stage.get("tier", "") or (stage.get("model") or {}).get("tier", "")).upper()
    abstract = _ABSTRACT_TIER_HINT.get(tier, "")
    if model_map:
        tiers = model_map.get("tiers") or {}
        resolved = str(tiers.get(tier, "") or "").strip()
        if resolved:
            return tier, resolved
    return tier, abstract


def run_dispatch(manifest: Dict[str, Any], run_dir: Path, *,
                 dispatch_cmd: Optional[str], apply_repairs: bool, provider_cap: int,
                 fast_ads: bool, resume: bool, online_links: bool,
                 key: Optional[bytes], root: Optional[Path] = None,
                 model_map: Optional[Dict[str, Any]] = None) -> int:
    """Execute the full wave schedule. Returns 0 on a complete dispatch, 2 on a
    precedence/provider violation, 4 on a PARK (recovery exhausted).

    FIX-XC-09f: when `model_map` is provided each stage's declared tier resolves
    to the box's concrete model id (passed to the adapter as the model hint) and
    the resolved tier ids + the provider cap source are recorded in RUN-LEDGER.json."""
    root = root or _skill_root()
    stages_by_id = {s["stage_id"]: s for s in manifest["stages"]}
    intake_path = run_dir / "intake.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8")) if intake_path.is_file() else {}
    art_dir = run_dir / "artifacts"
    rec_dir = run_dir / "receipts"
    art_dir.mkdir(parents=True, exist_ok=True)
    rec_dir.mkdir(parents=True, exist_ok=True)
    led_path = run_dir / "RUN-LEDGER.json"
    led: Dict[str, Any] = {}
    if led_path.is_file():
        try:
            led = json.loads(led_path.read_text(encoding="utf-8"))
        except ValueError:
            led = {}
    led["apply_repairs"] = bool(apply_repairs)
    led.setdefault("run_id", run_dir.name)
    led.setdefault("stages", {})
    # FIX-XC-09f: pin the resolved model-map + provider cap into the ledger so the
    # run's provenance shows the ACTUAL provider tiers dispatch routed to (or that
    # the box had no map and the conservative fallback cap was used).
    led["model_map"] = {
        "source": (model_map or {}).get("_source"),
        "tiers": (model_map or {}).get("tiers") or {},
        "provider_cap": int(provider_cap),
        "provider_cap_source": "model-map.provider_caps.concurrent" if model_map else "fleet-default",
    }

    waves = compute_waves(manifest["stages"], fast_ads)
    dispatched = 0
    for wave in waves:
        for sub in throttle(wave, provider_cap):
            for sid in sub:
                stage = stages_by_id[sid]
                if resume and _receipt_verified(run_dir, sid, key):
                    print(f"[resume] skip {sid}: verified receipt already on disk")
                    continue
                # PRECEDENCE (enforced, not assumed): every dep must carry a
                # verified receipt before this stage is allowed to dispatch.
                missing = [d for d in stage["depends_on"] if not _receipt_verified(run_dir, d, key)]
                if missing:
                    _park(run_dir, sid, f"AF-AV-PRECEDENCE: depends_on receipts missing/invalid: {missing}")
                    return 2
                recovery = str(stage.get("recovery", "auto")).lower()
                max_fix = int(stage.get("max_fix_attempts", 1) or 1)
                attempts = 1 if recovery == "park" else max(1, max_fix)
                artifacts = {p.stem: p.read_text(encoding="utf-8") for p in art_dir.glob("*.md")}
                prompt = compose_prompt(root, sid, intake, artifacts, apply_repairs,
                                        depends_on=stage["depends_on"])
                # FIX-XC-09f: resolve this stage's declared tier to the box's OWN
                # concrete model id (from model-map.json) and pass THAT to the
                # adapter; absent a map, the abstract 'tier-a' hint is used.
                tier_letter, hint = _resolve_tier_id(stage, model_map)
                text: Optional[str] = None
                model = ""
                last_err = ""
                for attempt in range(1, attempts + 1):
                    try:
                        cand_text, model = _dispatch(prompt, sid, hint, dispatch_cmd)
                    except DispatchError as exc:
                        last_err = str(exc)
                        continue
                    # G-NOANTHROPIC on the REAL returned model id (fail-closed).
                    if _ANTHROPIC_ID_RE.search(model or ""):
                        _park(run_dir, sid, f"AF-AV-NOANTHROPIC: dispatch returned an Anthropic model id {model!r}")
                        return 2
                    if _stage_output_ok(cand_text):
                        text = cand_text
                        break
                    last_err = f"attempt {attempt}: output empty or has unresolved tokens"
                if text is None:
                    _park(run_dir, sid,
                          f"recovery={recovery} exhausted after {attempts} attempt(s); last error: {last_err}")
                    return 4
                (art_dir / f"{sid}.md").write_text(text, encoding="utf-8")
                sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
                rec: Dict[str, Any] = {
                    "stage": sid, "sha256": sha, "model": model, "attested_by": "foreman",
                    "dispatched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if key is not None:
                    rec["sig"] = _receipt_sig(key, rec)
                (rec_dir / f"G-STAGE-{sid}.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
                # FIX-XC-09f: record BOTH the resolved tier id the stage was routed
                # to (from model-map) AND the real model id the adapter returned.
                led["stages"][sid] = {
                    "tier": tier_letter,
                    "resolved_tier_id": hint,
                    "model": model,
                    "receipt": True,
                }
                led_path.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")
                dispatched += 1
                # stage-02 completion -> the (fail-soft) links gate; --online only
                # on client boxes (default offline -> degraded:search, never fatal).
                if sid.startswith("02-"):
                    links_argv = ["--run", str(run_dir)] + (["--online"] if online_links else [])
                    # best-effort, fail-soft side gate: it writes its own G-LINKS
                    # receipt to disk; suppress its console output so the foreman
                    # log stays clean (the receipt, not the print, is the record).
                    import contextlib
                    import io as _io
                    try:
                        with contextlib.redirect_stdout(_io.StringIO()):
                            links_rc = links_gate.main(links_argv)
                        print(f"[links] stage-02 link gate ran (rc={links_rc}, "
                              f"{'online' if online_links else 'offline/degraded:search'}); G-LINKS receipt written.")
                    except SystemExit:
                        pass
    print(f"DISPATCH COMPLETE: {dispatched} stage(s) dispatched, "
          f"{sum(1 for s in manifest['stages'] if _receipt_verified(run_dir, s['stage_id'], key))}/"
          f"{len(manifest['stages'])} stages carry a verified receipt.")
    return 0


def compute_waves(stages: List[Dict[str, Any]], fast_ads: bool = False) -> List[List[str]]:
    """Kahn layering from depends_on. Proves the DAG is acyclic and yields waves
    where every stage's deps are in strictly-earlier waves."""
    deps: Dict[str, set] = {}
    for s in stages:
        d = set(s["depends_on"])
        if fast_ads and s["stage_id"] in AD_TAIL:
            # collapse the harmony chain: sets 2..13 depend only on ad-set-1 (+ their base set)
            d = {x for x in d if not x.startswith(("23-", "24-", "25-", "26-", "27-", "28-",
                                                   "29-", "30-", "31-", "32-", "33-", "34-"))}
            d.add("22-ad-set-1")
        deps[s["stage_id"]] = d
    done: set = set()
    waves: List[List[str]] = []
    remaining = set(deps)
    while remaining:
        ready = sorted(sid for sid in remaining if deps[sid] <= done)
        if not ready:
            raise ValueError(f"cycle or missing dep among: {sorted(remaining)}")
        waves.append(ready)
        done |= set(ready)
        remaining -= set(ready)
    return waves


def throttle(wave: List[str], cap: int) -> List[List[str]]:
    return [wave[i:i + cap] for i in range(0, len(wave), cap)]


def verify_schedule(stages: List[Dict[str, Any]], waves: List[List[str]], fast_ads: bool) -> List[str]:
    """Assert no stage is scheduled before all its deps have completed in an earlier wave."""
    errs = []
    pos = {sid: i for i, w in enumerate(waves) for sid in w}
    by_id = {s["stage_id"]: s for s in stages}
    all_ids = set(by_id)
    scheduled = {sid for w in waves for sid in w}
    if scheduled != all_ids:
        errs.append(f"schedule covers {len(scheduled)}/{len(all_ids)} stages")
    for s in stages:
        sid = s["stage_id"]
        deps = set(s["depends_on"])
        if fast_ads and sid in AD_TAIL:
            deps = {"22-ad-set-1"}
        for d in deps:
            if d in pos and pos[d] >= pos.get(sid, -1):
                errs.append(f"{sid} scheduled in wave {pos.get(sid)} but dep {d} is in wave {pos[d]}")
    return errs


# ---------------------------------------------------------------------------
def _print_plan(manifest, fast_ads: bool, provider_cap: int, apply_repairs: bool = False) -> int:
    stages = manifest["stages"]
    waves = compute_waves(stages, fast_ads)
    errs = verify_schedule(stages, waves, fast_ads)
    mode = "ON (--apply-repairs)" if apply_repairs else "OFF (faithful-to-live default)"
    print(f"AVATAR-ALCHEMIST FOREMAN PLAN  (fast_ads={fast_ads}, provider_cap={provider_cap}, repairs={mode})")
    print(f"branch=brand  stages={len(stages)}  dependency-waves={len(waves)}")
    for i, w in enumerate(waves, 1):
        subs = throttle(w, provider_cap)
        tag = "" if len(subs) == 1 else f"  -> {len(subs)} sub-waves @cap {provider_cap}"
        print(f"  W{i:>2}: {len(w):>2} dispatched  {w}{tag}")
    peak = max(len(w) for w in waves)
    print(f"peak dispatched width = {peak}")
    if errs:
        print("SCHEDULE VIOLATIONS:")
        for e in errs:
            print("  " + e)
        return 2
    print("schedule OK: every stage follows its dependencies.")
    return 0


def _require_nonce(nonce_path: str | None) -> bool:
    if not nonce_path:
        return False
    p = Path(nonce_path)
    return p.is_file() and len(p.read_text(encoding="utf-8").strip()) >= 16


_FORBIDDEN_DEP_RE = re.compile(r"\bimport\s+(requests|openai|anthropic|httpx|aiohttp)\b")
_ANTHROPIC_ID_RE = re.compile(r"anthropic/|claude-[0-9]|claude-sonnet|claude-opus|claude-haiku", re.IGNORECASE)


def _skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _front_door_reverify() -> List[str]:
    """RE-RUN deps + bypass-scan (Anthropic ids + egress) + hash-pin in-process,
    regardless of the nonce's provenance. This is what closes the QC finding
    'aa_director accepts a hand-forged nonce and never re-verifies deps/
    bypass-scan/hash-pin' — those checks now live HERE, not only in entry.sh,
    so no invocation path can skip them. Returns a list of failure reasons
    (empty = clean)."""
    root = _skill_root()
    problems: List[str] = []

    # 1) deps: stdlib-only provers
    for py in (root / "scripts").glob("*.py"):
        try:
            src = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _FORBIDDEN_DEP_RE.search(src):
            problems.append(f"deps: {py.name} imports a forbidden external runtime dep")

    # 2) bypass-scan: no Anthropic ids in prompts/manifests
    for p in (root / "prompts").rglob("*.md"):
        try:
            if _ANTHROPIC_ID_RE.search(p.read_text(encoding="utf-8", errors="replace")):
                problems.append(f"bypass-scan: Anthropic/claude model id found in {p.relative_to(root)}")
        except OSError:
            continue
    for j in root.glob("*.json"):
        try:
            if _ANTHROPIC_ID_RE.search(j.read_text(encoding="utf-8", errors="replace")):
                problems.append(f"bypass-scan: Anthropic/claude model id found in {j.name}")
        except OSError:
            continue

    # 3) egress-scan: no ungoverned uploader path (AF-AV-EGRESS)
    egress_violations = egress_gate.scan_dir(root / "scripts")
    for code, msg in egress_violations:
        problems.append(f"egress-scan [{code}]: {msg}")

    # 4) hash-pin: gates match their pinned sha256, checked RIGHT NOW
    if gic.check() != 0:
        problems.append("hash-pin: gate-integrity check failed — a pinned gate is modified")

    return problems


def _detect_book_skill_present(root: Path) -> bool:
    """Dynamic detection of the separate Book skill (53) — never hardcoded."""
    parent = root.parent
    if not parent.is_dir():
        return False
    for d in parent.iterdir():
        if d.is_dir() and re.match(r"^53-.*book.*$", d.name, re.IGNORECASE):
            return True
    return False


def _version_gate(run_dir: Path) -> Tuple[int, Dict[str, Any]]:
    """Load <run_dir>/intake.json and enforce G0-INTAKE + G0-VERSION in code.
    Returns (exit_code_if_should_stop_or_0_if_brand_clear, route_record).
    exit codes: 0 = brand, clear to dispatch; 2 = intake/version violation;
    4 = version=book, correctly routed/parked (hard-stop, by design)."""
    root = _skill_root()
    intake_path = run_dir / "intake.json"
    if not intake_path.is_file():
        return 2, {"route": "refused", "reason": f"no intake.json at {intake_path}"}
    try:
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return 2, {"route": "refused", "reason": f"intake.json does not parse: {exc}"}

    book_present = _detect_book_skill_present(root)
    violations, notes = intake_gate.verify(intake, book_present)
    version = str(intake.get("version", "")).strip().lower()
    codes = {c for c, _ in violations}

    if version == "book":
        # version=book NEVER reaches the brand pipeline, regardless of whether
        # every other field is otherwise clean — this is a hard route, not a
        # violation to fix and retry into brand dispatch.
        route = "book-routed" if "AF-AV-BOOK-SKILL-MISSING" not in codes else "book-parked"
        return 4, {"route": route, "version": "book", "violations": [list(v) for v in violations],
                    "notes": notes, "book_skill_present": book_present}

    if violations:
        return 2, {"route": "refused", "version": version or None,
                    "violations": [list(v) for v in violations], "notes": notes}

    return 0, {"route": "brand-dispatch", "version": "brand",
               "violations": [], "notes": notes}


def _dispatch_self_test() -> bool:
    """Offline proof of the FIX-XC-05b dispatch loop with a MOCK adapter: a full
    3-stage run writes HMAC-signed receipts + ledger rows with the real returned
    model id; --resume skips receipted stages; an Anthropic model id parks
    (AF-AV-NOANTHROPIC); and recovery exhaustion parks (redo-then-PARK)."""
    import tempfile
    import textwrap
    ok = True
    mini = {
        "manifest_version": "selftest",
        "stages": [
            {"stage_id": "01-alpha", "depends_on": [], "recovery": "auto", "max_fix_attempts": 2},
            {"stage_id": "02-beta", "depends_on": ["01-alpha"], "recovery": "auto", "max_fix_attempts": 2},
            {"stage_id": "03-gamma", "depends_on": ["02-beta"], "recovery": "auto", "max_fix_attempts": 2},
        ],
    }
    with tempfile.TemporaryDirectory() as td:
        troot = Path(td) / "skill"
        (troot / "prompts" / "01-alpha").mkdir(parents=True)
        (troot / "prompts" / "02-beta").mkdir(parents=True)
        (troot / "prompts" / "03-gamma").mkdir(parents=True)
        (troot / "prompts" / "01-alpha" / "user.md").write_text(
            "Client {{intake.first_name}} in {{intake.niche}}. No upstream.", encoding="utf-8")
        (troot / "prompts" / "02-beta" / "user.md").write_text(
            "Upstream alpha: {{artifact.01-alpha}} for {{intake.first_name}}.", encoding="utf-8")
        (troot / "prompts" / "03-gamma" / "user.md").write_text(
            "Upstream beta: {{artifact.02-beta}}.", encoding="utf-8")

        def _mock(name: str, body: str) -> str:
            p = Path(td) / name
            p.write_text(body, encoding="utf-8")
            return f"{sys.executable} {p}"

        good = _mock("mock_good.py", textwrap.dedent('''
            import sys, json
            _ = sys.stdin.read()
            print(json.dumps({"text": "# ok\\n" + ("word " * 60), "model": "ollama-cloud/qwen3-235b"}))
        '''))
        anthro = _mock("mock_anthropic.py", textwrap.dedent('''
            import sys, json
            _ = sys.stdin.read()
            print(json.dumps({"text": "# ok\\n" + ("word " * 60), "model": "anthropic/claude-3-5-sonnet"}))
        '''))
        empty = _mock("mock_empty.py", textwrap.dedent('''
            import sys, json
            _ = sys.stdin.read()
            print(json.dumps({"text": "   ", "model": "ollama-cloud/qwen3-235b"}))
        '''))

        def _mkrun(sub: str) -> Path:
            rd = Path(td) / sub
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "intake.json").write_text(json.dumps(
                {"version": "brand", "first_name": "Amara", "niche": "visibility coaching"}), encoding="utf-8")
            import secrets
            (rd / ".foreman-key").write_text(secrets.token_bytes(32).hex(), encoding="utf-8")
            return rd

        # (1) full good run -> 3 signed receipts + ledger models
        rd = _mkrun("good")
        key = bytes.fromhex((rd / ".foreman-key").read_text().strip())
        rc = run_dispatch(mini, rd, dispatch_cmd=good, apply_repairs=False, provider_cap=10,
                          fast_ads=False, resume=False, online_links=False, key=key, root=troot)
        all_ok = rc == 0 and all(_receipt_verified(rd, s["stage_id"], key) for s in mini["stages"])
        led = json.loads((rd / "RUN-LEDGER.json").read_text())
        models_ok = all(led["stages"][s["stage_id"]]["model"] == "ollama-cloud/qwen3-235b" for s in mini["stages"])
        # prove substitution happened: 02-beta artifact is the mock body (tokens resolved, none leaked)
        beta = (rd / "artifacts" / "02-beta.md").read_text()
        subst_ok = "{{" not in beta
        if all_ok and models_ok and subst_ok:
            print("SELF-TEST ok: (FIX-XC-05b) full dispatch loop -> 3/3 HMAC-signed receipts, ledger "
                  "carries the REAL returned model id, prompt tokens resolved (zero {{...}} leaked).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: dispatch loop rc={rc} receipts_ok={all_ok} models_ok={models_ok} subst_ok={subst_ok}")

        # (2) --resume skips receipted stages (re-run with an ALWAYS-FAIL adapter:
        #     if resume did NOT skip, the empty adapter would park; it returns 0).
        rc2 = run_dispatch(mini, rd, dispatch_cmd=empty, apply_repairs=False, provider_cap=10,
                           fast_ads=False, resume=True, online_links=False, key=key, root=troot)
        if rc2 == 0 and not (rd / "PARKED.json").exists():
            print("SELF-TEST ok: --resume skips every already-receipted stage (idempotent; a would-fail "
                  "adapter is never even called).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: --resume did not skip receipted stages (rc={rc2}).")

        # (3) an Anthropic model id from the adapter PARKS the run (AF-AV-NOANTHROPIC)
        rda = _mkrun("anthro")
        keya = bytes.fromhex((rda / ".foreman-key").read_text().strip())
        rca = run_dispatch(mini, rda, dispatch_cmd=anthro, apply_repairs=False, provider_cap=10,
                           fast_ads=False, resume=False, online_links=False, key=keya, root=troot)
        parked = (rda / "PARKED.json")
        if rca == 2 and parked.exists() and "NOANTHROPIC" in parked.read_text():
            print("SELF-TEST ok: an Anthropic model id returned by the adapter -> rc 2 + PARKED "
                  "(AF-AV-NOANTHROPIC on the REAL returned model id).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: Anthropic model id not blocked (rc={rca}, parked={parked.exists()}).")

        # (4) recovery exhaustion (empty output, max_fix_attempts=2) -> redo-then-PARK
        rde = _mkrun("exhaust")
        keye = bytes.fromhex((rde / ".foreman-key").read_text().strip())
        rce = run_dispatch(mini, rde, dispatch_cmd=empty, apply_repairs=False, provider_cap=10,
                           fast_ads=False, resume=False, online_links=False, key=keye, root=troot)
        parkede = (rde / "PARKED.json")
        if rce == 4 and parkede.exists() and "01-alpha" in parkede.read_text():
            print("SELF-TEST ok: recovery exhausted (empty output x max_fix_attempts) -> rc 4 + PARKED "
                  "at the failing stage (redo-then-park, no partial delivery).")
        else:
            ok = False
            print(f"SELF-TEST FAIL: recovery exhaustion did not park (rc={rce}, parked={parkede.exists()}).")

        # (5) FIX-XC-09f: the model-map is CONSUMED at dispatch. A run with a
        #     model-map resolves each stage's tier (A/B) to the box's concrete id,
        #     defaults the provider cap from provider_caps.concurrent, and records
        #     BOTH the resolved tier ids and the cap source in RUN-LEDGER.json.
        mm = {
            "tiers": {"A": "ollama-cloud/qwen3-235b", "B": "openrouter/deepseek-chat",
                      "SEARCH": "box-web-search"},
            "provider_caps": {"concurrent": 3},
        }
        mini2 = {"manifest_version": "selftest-xc09f", "stages": [
            {"stage_id": "01-alpha", "depends_on": [], "tier": "A", "recovery": "auto", "max_fix_attempts": 2},
            {"stage_id": "02-beta", "depends_on": ["01-alpha"], "tier": "B", "recovery": "auto", "max_fix_attempts": 2},
        ]}
        rdm = _mkrun("modelmap")
        keym = bytes.fromhex((rdm / ".foreman-key").read_text().strip())
        capm = _provider_cap_from_map(mm)
        rcm = run_dispatch(mini2, rdm, dispatch_cmd=good, apply_repairs=False, provider_cap=capm,
                           fast_ads=False, resume=False, online_links=False, key=keym, root=troot,
                           model_map=mm)
        ledm = json.loads((rdm / "RUN-LEDGER.json").read_text())
        cap_ok = capm == 3 and ledm.get("model_map", {}).get("provider_cap") == 3
        src_ok = ledm.get("model_map", {}).get("provider_cap_source") == "model-map.provider_caps.concurrent"
        tiers_ok = (ledm["stages"]["01-alpha"].get("resolved_tier_id") == "ollama-cloud/qwen3-235b"
                    and ledm["stages"]["01-alpha"].get("tier") == "A"
                    and ledm["stages"]["02-beta"].get("resolved_tier_id") == "openrouter/deepseek-chat"
                    and ledm["stages"]["02-beta"].get("tier") == "B")
        if rcm == 0 and cap_ok and src_ok and tiers_ok:
            print("SELF-TEST ok: (FIX-XC-09f) model-map CONSUMED — provider cap defaulted from "
                  "provider_caps.concurrent (=3, not 10), each stage tier resolved to the box's "
                  "concrete id, resolved tier ids recorded in RUN-LEDGER.json.")
        else:
            ok = False
            print(f"SELF-TEST FAIL: model-map not consumed as expected (rc={rcm}, cap_ok={cap_ok}, "
                  f"src_ok={src_ok}, tiers_ok={tiers_ok}).")

        # (6) FIX-XC-09f: absent a model-map the cap falls back to the conservative
        #     fleet default (3), NEVER the old hardcoded 10, and tiers resolve to the
        #     abstract hint (unchanged legacy seam).
        _t, abstract = _resolve_tier_id({"tier": "A"}, None)
        if _provider_cap_from_map(None) == DEFAULT_PROVIDER_CAP == 3 and abstract == "tier-a":
            print("SELF-TEST ok: (FIX-XC-09f) no model-map -> cap falls back to the fleet default "
                  f"({DEFAULT_PROVIDER_CAP}), tier resolves to the abstract hint (legacy seam intact).")
        else:
            ok = False
            print("SELF-TEST FAIL: model-map-absent fallback wrong "
                  f"(cap={_provider_cap_from_map(None)}, abstract={abstract!r}).")

        # (7) FIX-XC-09f: a model-map carrying an Anthropic-shaped tier id is REFUSED
        #     by the consumer (defense-in-depth on the client-path ban), read from disk.
        rda2 = _mkrun("mm-anthropic")
        (rda2 / "model-map.json").write_text(json.dumps(
            {"tiers": {"A": "anthropic/claude-3-5-sonnet"}, "provider_caps": {"concurrent": 3}}),
            encoding="utf-8")
        refused = False
        try:
            load_model_map(rda2, troot)
        except ValueError as exc:
            refused = "NOANTHROPIC" in str(exc)
        if refused:
            print("SELF-TEST ok: (FIX-XC-09f) a model-map with an Anthropic-shaped tier id is REFUSED "
                  "by load_model_map (AF-AV-NOANTHROPIC, client-path ban).")
        else:
            ok = False
            print("SELF-TEST FAIL: an Anthropic-tainted model-map was not refused by the consumer.")

    return ok


def run_self_test(manifest) -> int:
    ok = True
    stages = manifest["stages"]

    # (a) default schedule is acyclic, covers 40, respects deps
    waves = compute_waves(stages, fast_ads=False)
    errs = verify_schedule(stages, waves, fast_ads=False)
    covered = sum(len(w) for w in waves)
    if errs or covered != 40:
        ok = False
        print(f"SELF-TEST FAIL: default schedule errs={errs[:3]} covered={covered}")
    else:
        print(f"SELF-TEST ok: default schedule acyclic, 40/40 covered, deps respected ({len(waves)} waves).")

    # (b) peak width matches the honest profile (<=5 simultaneous authors, PRD 10.1)
    peak = max(len(w) for w in waves)
    if peak > 5:
        ok = False; print(f"SELF-TEST FAIL: default peak width {peak} > 5 (PRD 10.1)")
    else:
        print(f"SELF-TEST ok: default peak simultaneous authors = {peak} (<=5).")

    # (c) fast-ads collapses the ad tail into one wide wave and stays valid
    fw = compute_waves(stages, fast_ads=True)
    ferrs = verify_schedule(stages, fw, fast_ads=True)
    fpeak = max(len(w) for w in fw)
    if ferrs or fpeak < 6:
        ok = False; print(f"SELF-TEST FAIL: fast-ads errs={ferrs[:3]} peak={fpeak}")
    else:
        print(f"SELF-TEST ok: --fast-ads valid, collapses ad tail (peak width {fpeak}, {len(fw)} waves).")

    # (d) precedence guard: a stage with an unmet dep is refused
    fake_done = {"01-avatar-questions-1-30"}
    blocked = "08-blended-tone"
    deps = set(next(s for s in stages if s["stage_id"] == blocked)["depends_on"])
    refused = not (deps <= fake_done)
    if not refused:
        ok = False; print("SELF-TEST FAIL: precedence guard did not refuse a stage with unmet deps")
    else:
        print("SELF-TEST ok: precedence guard refuses dispatch when depends_on receipts are missing.")

    # (e) front-door nonce required for a real run
    if _require_nonce(None) or _require_nonce("/nonexistent/nonce"):
        ok = False; print("SELF-TEST FAIL: nonce guard accepted a missing/short nonce")
    else:
        print("SELF-TEST ok: front-door nonce required (missing/short nonce refused).")

    # (f) repairs are OFF by default; the dispatch banner differs by mode and R7 is
    #     stated unconditionally; the schedule is identical in both modes (topology
    #     preserved — repairs change prompt CONTENT + the R4 gate, never the DAG).
    off, on = dispatch_preamble(False), dispatch_preamble(True)
    if ("repairs OFF" in off and "repairs ON" in on and off != on
            and "Anthropic" in off and "Anthropic" in on
            and compute_waves(stages, False) == compute_waves(stages, False)):
        print("SELF-TEST ok: repairs default OFF; dispatch banner mode-specific; R7 unconditional.")
    else:
        ok = False; print("SELF-TEST FAIL: repairs banner/default gating wrong.")

    # (g) REPRO + BLOCK: a hand-forged nonce (the exact QC reproduction) no
    #     longer buys a dispatch, because the front door is RE-VERIFIED
    #     in-process regardless of the nonce's provenance. On a clean repo
    #     tree the re-verify must find ZERO problems (proves it is a REAL
    #     check, not a stub that always fails or always passes).
    problems = _front_door_reverify()
    if not problems:
        print("SELF-TEST ok: front-door RE-VERIFY (deps+bypass-scan+egress+hash-pin) passes clean "
              "on the real tree — proves it is a real, currently-passing check, not a stub.")
    else:
        ok = False
        print(f"SELF-TEST FAIL: front-door re-verify found problems on the clean tree: {problems[:5]}")
    # a hand-forged nonce (16 X's, exactly the QC repro) still satisfies the
    # WEAK presence check by itself — _require_nonce() was never meant to be
    # the sole guard. Proving the fix means proving main() ALWAYS pairs the
    # nonce check with a real, unconditional re-verify (checked again here so
    # this self-test fails if that pairing is ever refactored away).
    import inspect
    main_src = inspect.getsource(sys.modules[__name__].main)
    if "_front_door_reverify" in main_src and "_require_nonce" in main_src:
        print("SELF-TEST ok: (REPRO) a hand-forged 16-char nonce (e.g. 'XXXXXXXXXXXXXXXX') still "
              "satisfies the WEAK presence check alone, but main() unconditionally pairs it with "
              "_front_door_reverify() — a forged nonce cannot skip deps/bypass-scan/egress/hash-pin.")
    else:
        ok = False
        print("SELF-TEST FAIL: main() no longer pairs the nonce presence check with a real "
              "front-door re-verify — a hand-forged nonce could skip the real checks again.")

    # (h) version=book is refused IN CODE: a run-dir with a version=book
    #     intake.json must hard-stop (exit 4) and NEVER return the brand
    #     dispatch route, even though every other field is well-formed.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        book_intake = {
            "version": "book", "first_name": "Jordan", "last_name": "Rivers",
            "ideal_avatar": "aspiring women founders in wellness", "niche": "holistic business coaching",
            "primary_goal": "launch a profitable practice",
            "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
            "book_stories": "The night I closed my first clinic and started over.",
        }
        (rd / "intake.json").write_text(json.dumps(book_intake), encoding="utf-8")
        rc, route = _version_gate(rd)
        if rc == 4 and route["route"] in ("book-routed", "book-parked") and route["version"] == "book":
            print(f"SELF-TEST ok: (REPRO+BLOCK) version=book intake -> exit 4, route={route['route']!r}, "
                  f"brand pipeline UNREACHABLE (this exact scenario used to print "
                  f"'branch=brand stages=40' and dispatch).")
        else:
            ok = False; print(f"SELF-TEST FAIL: version=book -> rc={rc} route={route}")

        brand_intake = {
            "version": "brand", "first_name": "Jordan", "last_name": "Rivers",
            "ideal_avatar": "aspiring women founders in wellness", "niche": "holistic business coaching",
            "primary_goal": "launch a profitable practice",
            "tone_style_1": "Maya Angelou in Letter to My Daughter", "tone_style_2": "N/A",
            "tone": "inspirational, thought-provoking", "target_market": "US women 30-50",
            "tone_style_3": "N/A", "tone_style_4": "N/A",
            "offer_name": "The Rooted Practice Accelerator", "offer_type": "group coaching program",
            "offer_benefit": "a fully-booked practice in 90 days",
            "product_info": "12-week live cohort with templates and coaching",
            "brand_info": "Rooted Practice is a movement for purpose-led founders",
            "brand_start_date": "2021", "brand_why": "to end burnout culture in coaching",
            "brand_colors": "deep green, warm gold",
        }
        (rd / "intake.json").write_text(json.dumps(brand_intake), encoding="utf-8")
        rc, route = _version_gate(rd)
        if rc == 0 and route["route"] == "brand-dispatch":
            print("SELF-TEST ok: a clean version=brand intake clears the version gate -> brand-dispatch.")
        else:
            ok = False; print(f"SELF-TEST FAIL: valid brand intake -> rc={rc} route={route}")

        # a missing intake.json refuses (never defaults to brand)
        (rd / "intake.json").unlink()
        rc, route = _version_gate(rd)
        if rc == 2 and route["route"] == "refused":
            print("SELF-TEST ok: missing intake.json REFUSES dispatch (no default-to-brand).")
        else:
            ok = False; print(f"SELF-TEST FAIL: missing intake.json -> rc={rc} route={route}")

    # (i) the REAL dispatch loop (FIX-XC-05b), proven offline with a mock adapter
    if not _dispatch_self_test():
        ok = False

    print("SELF-TEST RESULT:", "PASS (exit 0)" if ok else "FAIL (exit 1)")
    return 0 if ok else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="Avatar-Alchemist foreman (wave scheduler + dispatcher).")
    ap.add_argument("--manifest")
    ap.add_argument("--plan", action="store_true", help="print the dependency-wave schedule")
    ap.add_argument("--dry-run", action="store_true", help="alias for --plan (no dispatch)")
    ap.add_argument("--status", action="store_true", help="print RUN-LEDGER status")
    ap.add_argument("--run-dir", help="run directory for --status/--resume")
    ap.add_argument("--nonce", help="one-time front-door nonce minted by entry.sh (required for a real run)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--recover", action="store_true")
    ap.add_argument("--fast-ads", action="store_true", help="collapse the ad-set harmony chain (fidelity trade-off, OFF by default)")
    ap.add_argument("--apply-repairs", action="store_true",
                    help="OPT IN to source repairs R1-R6 (default OFF = faithful to the live workflow). R7 Anthropic ban is always on.")
    ap.add_argument("--provider-cap", type=int, default=None,
                    help="max concurrent authors; DEFAULT resolves from model-map.json "
                         "provider_caps.concurrent (fleet Ollama-only boxes cap 3), never a hardcoded 10")
    ap.add_argument("--execute", action="store_true",
                    help="RUN the real dispatch loop (compose prompts, dispatch to the client model, "
                         "write artifacts + HMAC-signed receipts + ledger rows). Without it, the gates "
                         "run and the plan is described but no stage is dispatched.")
    ap.add_argument("--dispatch-cmd",
                    help="adapter command for a stage dispatch: prompt on stdin, JSON {\"text\",\"model\"} "
                         "on stdout (default seam: `openclaw agent --json`). Client providers only.")
    ap.add_argument("--online-links", action="store_true",
                    help="on stage-02 completion, run the links gate with --online (client boxes only; "
                         "default offline -> degraded:search, never fatal)")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    try:
        manifest = json.loads(Path(args.manifest or _manifest_path()).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"USAGE/IO ERROR: cannot load manifest: {exc}")
        return 3

    if args.self_test:
        return run_self_test(manifest)

    # FIX-XC-09f: load the box's model-map (consumed HERE, not by preflight alone)
    # and resolve the effective provider cap from provider_caps.concurrent when the
    # operator did not pass --provider-cap (fleet Ollama-only <=3 rule, never 10).
    try:
        model_map = load_model_map(Path(args.run_dir) if args.run_dir else None, _skill_root())
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    effective_cap = args.provider_cap if args.provider_cap is not None else _provider_cap_from_map(model_map)

    if args.plan or args.dry_run:
        return _print_plan(manifest, args.fast_ads, effective_cap, args.apply_repairs)
    if args.status:
        led = Path(args.run_dir or ".") / "RUN-LEDGER.json"
        if not led.is_file():
            print("no RUN-LEDGER.json yet."); return 0
        data = json.loads(led.read_text(encoding="utf-8"))
        rows = data.get("stages", {})
        done = sum(1 for r in rows.values() if r.get("receipt"))
        print(f"RUN {data.get('run_id','?')}: {done}/{len(manifest['stages'])} stages attested")
        return 0
    # a REAL dispatch requires the front-door nonce (presence check) — but this
    # is ONLY the first of two gates. A hand-forged nonce satisfies THIS check
    # alone; it does NOT satisfy the re-verify below.
    if not _require_nonce(args.nonce):
        print("REFUSED: no valid front-door nonce. Start the run via entry.sh "
              "(deps -> bypass-scan -> hash-pin -> nonce), then pass --nonce.")
        return 2

    # unconditional RE-VERIFY: deps + bypass-scan (Anthropic ids + egress) +
    # hash-pin, run BY THIS PROCESS, right now — regardless of whether entry.sh
    # actually ran, or whether the nonce is genuine or hand-forged. This is
    # what closes the "aa_director never re-verifies deps/bypass-scan/hash-pin"
    # finding: those checks are no longer something ONLY entry.sh can do.
    problems = _front_door_reverify()
    if problems:
        print("REFUSED: front-door re-verify failed (deps/bypass-scan/egress/hash-pin) — "
              "dispatch blocked regardless of the supplied nonce:")
        for p in problems:
            print(f"  {p}")
        return 2
    print("front-door RE-VERIFIED in-process (deps, bypass-scan, egress-scan, hash-pin all re-checked now).")

    # version gate: REFUSE in code to run the 40-stage brand pipeline for a
    # version=book intake (or any intake violation). --run-dir is required for
    # a real dispatch precisely so this check has an intake.json to read.
    if not args.run_dir:
        print("REFUSED: a real dispatch requires --run-dir (so the version/intake gate has "
              "<run-dir>/intake.json to read — no dispatch is possible without it).")
        return 2
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    vrc, route = _version_gate(run_dir)
    (run_dir / "route.json").write_text(json.dumps(route, indent=2) + "\n", encoding="utf-8")
    if vrc == 4:
        print(f"HARD-STOP: version=book -> route={route['route']!r} (see route.json). "
              f"The 40-stage BRAND pipeline is NEVER dispatched for a book intake — "
              f"this is the version gate doing its job, not an error.")
        return 4
    if vrc != 0:
        print(f"REFUSED: intake/version gate violation(s) — no dispatch (see route.json): "
              f"{route.get('violations')}")
        return 2
    print("version gate: intake.json is version=brand and clears G0-INTAKE + G0-VERSION -> brand-dispatch.")

    # record the repairs mode for the run so aa_build_check.py gates R4 correctly.
    led_path = run_dir / "RUN-LEDGER.json"
    led = {}
    if led_path.is_file():
        try:
            led = json.loads(led_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            led = {}
    led["apply_repairs"] = bool(args.apply_repairs)
    led.setdefault("stages", led.get("stages", {}))
    led_path.write_text(json.dumps(led, indent=2) + "\n", encoding="utf-8")
    print(f"front-door nonce accepted. repairs mode: "
          f"{'ON (--apply-repairs)' if args.apply_repairs else 'OFF (faithful-to-live default)'}.")
    print("DISPATCH BANNER (prepended to every stage): " + dispatch_preamble(args.apply_repairs))

    if not args.execute:
        print("LLM dispatch is the OpenClaw sub-agent seam (client providers only). Gates PASSED; "
              "pass --execute (with --dispatch-cmd or the openclaw default) to run the real dispatch "
              "loop, or --plan to inspect the wave schedule.")
        return 0

    # --- REAL dispatch loop (FIX-XC-05b) ------------------------------------
    key: Optional[bytes] = None
    key_path = run_dir / ".foreman-key"
    if key_path.is_file():
        try:
            key = bytes.fromhex(key_path.read_text(encoding="utf-8").strip())
        except ValueError:
            key = None
    if key is None:
        print("REFUSED: --execute requires the per-run foreman key (<run-dir>/.foreman-key, minted by "
              "entry.sh) so stage receipts can be HMAC-signed.")
        return 2
    src = "model-map.provider_caps.concurrent" if (args.provider_cap is None and model_map) else \
          ("--provider-cap flag" if args.provider_cap is not None else "fleet default (no model-map)")
    print(f"provider-cap = {effective_cap} (source: {src}); "
          f"model-map: {model_map.get('_source') if model_map else 'none — abstract tier hints'}.")
    rc = run_dispatch(manifest, run_dir, dispatch_cmd=args.dispatch_cmd,
                      apply_repairs=bool(args.apply_repairs), provider_cap=effective_cap,
                      fast_ads=args.fast_ads, resume=bool(args.resume),
                      online_links=bool(args.online_links), key=key, model_map=model_map)
    if rc == 0:
        print("Dispatch loop finished. Run aa_delivery_gate.py to certify + deliver.")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
