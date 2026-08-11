#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/rename_applier.py  (U03 tooling)
# PIPELINE RENAME APPLIER — the write surface of the U03 family: it applies a
# pipeline NAME change through Convert and Flow (LeadConnector) with the
# client's OWN private-integration token via PUT /opportunities/pipelines/{id}
# — and it REFUSES to write unless the operator explicitly passes --execute.
# Without --execute the tool is a DRY-RUN: it reads the live pipeline, proves
# the name law, and prints exactly the PUT it WOULD send — nothing is written,
# ever. Fail-closed: any ambiguity is a refusal, never a guessed write.
#
# WHY A DEDICATED MODULE: the pipeline bind is BY NAME (MASTERDOC floor 11;
# anthology_registry.py provision-pipeline); when a client needs the standard
# pipeline renamed, ONLY a controlled, verified, gated write may do it. This
# module is the single place that write exists in the engine's Python — the
# registry itself is READ-ONLY for pipelines by doctrine (pipelines are
# UI-created; the public v2 list surface is GET /opportunities/pipelines).
# The rename write is documented LIVE under Version: v3 (29-ghl-convert-and-
# flow/references/opportunities.md: update-pipeline — absent from the lagging
# OpenAPI spec files, scopes opportunities.readonly / opportunities.write).
#
# THE STAGES ARRAY IS A COMPLETE REPLACEMENT (v3 update semantics):
#   * include a stage's id to keep it,
#   * omit an id to create a new stage,
#   * omit a stage entirely and it is DELETED,
#   * you cannot remove all stages.
# A name-only rename therefore MUST echo the full read-back stages array
# byte-for-byte (every key, every id, order preserved) or the PUT would
# delete/replace stages. The PUT body is built ONLY from the live read-back —
# never from the contract's standard_stages (which carry no ids). A live
# pipeline with no readable stages REFUSES the plan (a body that could delete
# stages is never constructed, even in dry-run).
#
# FAIL-CLOSED SURFACES:
#   * the target pipeline must be byte-exact the expected name BEFORE any
#     write — a pipeline that is absent, or present under a different name,
#     STOPS (find-by-name cannot tell a renamed pipeline from an absent one,
#     so both refuse; renaming something that is not byte-exact who we think
#     it is is a write to the wrong record),
#   * the POST-PUT read-back must show the new name byte-exact AND the exact
#     same stage ids in the exact same order — any drift is exit 5 with a
#     delta, never a reported success,
#   * a PUT that returned success but cannot be read back is HELD (exit 3)
#     with the live state UNDETERMINED — never reported as renamed,
#   * a Convert and Flow validation refusal (400/409/422 — e.g. the new name
#     collides case-insensitively with another pipeline) is a STOP, never a
#     silent skip,
#   * old name == new name is an idempotent no-op PASS — nothing is written.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores) and the location id via
# the standard location labels (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID), overridable with
# --location-id. SET / NOT SET only on every operator surface; a value is
# NEVER printed. Location and pipeline ids are markers (last 4 chars) on any
# operator surface; the full ids ride only inside request bodies.
#
# BROWSER UA: every request carries the CAF_BROWSER_UA (W0.6 / GK-09
# discipline) so the Cloudflare edge fronting services.leadconnectorhq.com
# never 1010s the applier (the exact failure mode that 403s urllib's default
# UA before the request reaches Convert and Flow). The registry's CafClient
# pins Version 2021-07-28, so the v3 write + read-back ride this module's OWN
# v3 client, which reuses the registry's scope-vs-edge classification
# (reg._auth_denial_kind): a bare 401/403 whose body does NOT match the
# genuine scope-denial signature raises UpstreamBlockedError -> HELD, never a
# scope STOP.
#
# EXIT CODES (house convention 0/1/2/3/4/5):
#   0  PASS — dry-run plan pass, idempotent no-op, or applied + verified
#   1  unexpected error
#   2  STOP refusal — PIT/location label NOT SET, invalid names, the target
#      pipeline absent or not byte-exact the expected name, an unplannable
#      (stageless) pipeline, or a Convert and Flow validation refusal
#   3  HELD — Convert and Flow API unreachable / edge-blocked (retryable; the
#      scope is UNDETERMINED here, never proven absent), including an
#      applied-but-unreadable PUT
#   4  self-test FAILED (an offline assertion tripped; a tamper NEVER
#      masquerades as exit 1)
#   5  read-back mismatch after the PUT (name or stage-id drift)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO token and NO network):
#   rename_applier.py plan [--field-map PATH]            # offline plan
#   rename_applier.py apply --new-name NAME [--old-name NAME]
#                          [--pipeline-id ID] [--location-id ID]
#                          [--execute]                   # dry-run unless
#                                                         # --execute
#   rename_applier.py self-test                           # offline fixtures
#
# --execute is the ONLY flag that performs the PUT. Its absence makes the
# apply run a dry-run: live reads only, nothing written, applied:false in the
# report. apply (dry-run included) needs the PIT — a truthful plan requires
# the live read; an unread state is never fabricated.
#
# STDLIB ONLY (urllib + json via the registry and this module); calls NO
# model. Reuses anthology_registry (CafClient, resolve_pit, resolve_location,
# load_field_map, _stop, _mask_location, _auth_denial_kind and its exception
# classes). DOCTRINE: move in silence; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret value.
# =============================================================================
"""rename_applier.py — gated, verified pipeline-rename applier against the
Anthology Convert and Flow location (U03 tooling). Writes ONLY with
--execute; every other invocation is a read-only dry-run."""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"

# The rename write surface is Version: v3 ONLY (29-ghl-convert-and-flow
# references/opportunities.md: update-pipeline is documented under v3; the
# registry's CafClient pins 2021-07-28, so the write rides this module's own
# v3 client — same CAF_BROWSER_UA, same scope-vs-edge classification).
CAF_VERSION_V3 = "v3"

# The expected CURRENT name is NEVER hardcoded (SPEC M8): it comes from the
# committed contract config/field-map.json pipeline.standard_pipeline_name,
# the SAME source of truth provision-pipeline binds by. --old-name overrides.
_standard_pipeline_name = (
    (reg.load_field_map(FIELD_MAP_PATH).get("pipeline") or {}).get("standard_pipeline_name") or "")


def _mask_location(loc: str) -> str:
    """Non-reversible location marker (last 4 chars) for operator surfaces."""
    return reg._mask_location(loc)


def _mask_id(rid: str) -> str:
    """Non-reversible resource-id marker (last 4 chars) for operator surfaces.
    The full id rides inside request bodies only, never on a surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def _looks_real(value: str) -> bool:
    """Fail-closed id guard: a placeholder or a whitespace-laden value is not
    a real pipeline id and never reaches a request."""
    value = (value or "").strip()
    if not value:
        return False
    if value.lower() in ("replace-me", "<id>", "<pipeline-id>", "none", "null"):
        return False
    return not any(ch.isspace() for ch in value)


def _valid_new_name(value: str) -> bool:
    """A pipeline name may legitimately contain spaces (the standard name
    does) but must be non-empty and free of control characters."""
    value = (value or "").strip()
    if not value:
        return False
    return all(0x20 <= ord(ch) <= 0x7E or ord(ch) >= 0xA0 for ch in value)


class PipelineMissing(Exception):
    """A fail-closed refusal (STOP family): the rename target is absent, or
    its read-back is empty/unreadable."""


class PipelineNotFound(Exception):
    """The v3 read of a specific pipeline id returned HTTP 404 — the record
    does not exist. STOP family (never HELD: absence is a fact, not a
    transport condition)."""


class RenameRefused(Exception):
    """A fail-closed refusal (STOP family): the live state is unplannable —
    e.g. a pipeline with no readable stages, or a stage record without an id.
    A body that could delete stages is never constructed."""


# ---------------------------------------------------------------------------
# Version: v3 client — covers exactly the rename surface: GET-by-id (the
# read-back) and PUT-by-id (the write). Same browser UA and the SAME
# scope-vs-edge classification as the registry; a response body is never
# surfaced (it could echo a credential).
# ---------------------------------------------------------------------------
class _V3Client:
    """Minimal LeadConnector v3 client for the pipeline rename surface."""

    def __init__(self, token: str, timeout: int = 15):
        self._token = token
        self._timeout = timeout

    def _request(self, method: str, path: str, body=None):
        url = reg.CAF_API_BASE + path
        headers = {
            "Authorization": "Bearer %s" % self._token,
            "Version": CAF_VERSION_V3,
            "Accept": "application/json",
            # W0.6 / GK-09: the Cloudflare edge fronting services.leadconnectorhq.com
            # 403s urllib's default UA (CF 1010) before the request reaches Convert
            # and Flow. A browser UA is REQUIRED for the request to be scope-checked.
            "User-Agent": reg.CAF_BROWSER_UA,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code == 404:
                # Absence is a fact, not a transport condition: a missing
                # pipeline id on the read is a STOP, never a HELD.
                raise PipelineNotFound("pipeline id not found (HTTP 404)")
            if code in (401, 403):
                # A bare 401/403 is NOT proof of a scope problem: the Cloudflare
                # edge fronting services.leadconnectorhq.com returns 403 (CF 1010)
                # for a blocked request BEFORE it ever reaches the scope check.
                # Inspect the BODY and only call it a scope denial when it matches
                # the genuine W0.5 signature; otherwise it is an upstream/edge block.
                raw_body = b""
                try:
                    raw_body = exc.read()
                except Exception:  # noqa: BLE001 — body read failure = blocked
                    raw_body = b""
                if reg._auth_denial_kind(raw_body) == "scope":
                    raise reg.ScopeDenied(
                        "token not authorized for this scope (HTTP %s)" % code)
                raise reg.UpstreamBlockedError(
                    "HTTP %s did NOT match a Convert and Flow scope-denial "
                    "signature -- likely a Cloudflare/WAF edge block, NOT a "
                    "token-scope problem. The request already carries a proven "
                    "browser User-Agent (CAF_BROWSER_UA)." % code)
            if code in (400, 409, 422):
                # e.g. the new name collides (case-insensitively) with another
                # pipeline, or the body violates the update contract. Never
                # surface the body verbatim — the classification is enough.
                raise reg.CafValidation(
                    "Convert and Flow rejected the %s (HTTP %s)" % (method, code))
            raise reg.CafUnreachable(
                "Convert and Flow HTTP %s on %s" % (code, method))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise reg.CafUnreachable(
                "Convert and Flow transport error: %s" % type(exc).__name__)

    def get_pipeline(self, pipeline_id: str) -> dict:
        """GET /opportunities/pipelines/{id} — the read-back surface (proven
        live under both 2021-07-28 and v3; the module pins v3). Returns the
        pipeline record or raises PipelineNotFound / the registry's exception
        classes."""
        out = self._request(
            "GET", "/opportunities/pipelines/%s"
            % urllib.parse.quote(pipeline_id, safe=""))
        return out.get("pipeline") or out

    def update_pipeline(self, pipeline_id: str, body: dict) -> dict:
        """PUT /opportunities/pipelines/{id} — the ONLY write surface this
        module performs. `body` is the complete-replacement payload built by
        build_rename_body(); the response is never surfaced verbatim."""
        out = self._request(
            "PUT", "/opportunities/pipelines/%s"
            % urllib.parse.quote(pipeline_id, safe=""), body=body)
        return out.get("pipeline") or out


# ---------------------------------------------------------------------------
# Name law / plan primitives.
# ---------------------------------------------------------------------------
def find_pipeline_by_name(client, location_id: str, want: str) -> dict:
    """Byte-exact find-by-name (the house bind law). Returns the pipeline
    record or raises PipelineMissing — a rename may never target an absent
    pipeline, and a pipeline present under ANY other name is a different
    pipeline."""
    pipes = client.list_pipelines(location_id)
    found = next((p for p in pipes
                  if isinstance(p, dict) and (p.get("name") or "").strip() == want),
                 None)
    if found is None:
        names = sorted({p.get("name") for p in pipes
                        if isinstance(p, dict) and p.get("name")})
        raise PipelineMissing(
            "the pipeline %r is ABSENT from the location (found: %s). A rename "
            "cannot target an absent pipeline; find-by-name cannot tell a "
            "renamed pipeline from an absent one, so both refuse."
            % (want, ", ".join(names) or "(none)"))
    return dict(found)


def build_rename_body(pipeline: dict, new_name: str) -> dict:
    """The name-only PUT body. FAIL-CLOSED: the v3 update treats the stages
    array as a COMPLETE REPLACEMENT — every read-back stage record is echoed
    verbatim (every key, every id, order preserved), so the PUT changes the
    name and nothing else. A pipeline with no readable stages, or a stage
    record without an id, REFUSES the plan: a body that could delete stages
    is never constructed — not even for the dry-run report."""
    stages = pipeline.get("stages")
    if not isinstance(stages, list) or not stages:
        raise RenameRefused(
            "the live pipeline %r carries no readable stages — a name-only "
            "PUT replaces the whole stages array (complete-replacement "
            "semantics) and could delete stages; refusing to plan"
            % (pipeline.get("name") or "(unnamed)"))
    echoed = []
    for st in stages:
        if not isinstance(st, dict):
            raise RenameRefused(
                "a live stage record is not a JSON object — refusing to plan")
        sid = st.get("id")
        if not isinstance(sid, str) or not sid:
            raise RenameRefused(
                "a live stage record carries no id — the complete-replacement "
                "body could not keep it; refusing to plan")
        echoed.append(dict(st))  # every key preserved, order preserved
    return {"name": new_name, "stages": echoed}


def _stage_ids(pipeline: dict):
    return [st.get("id") for st in (pipeline.get("stages") or [])
            if isinstance(st, dict) and st.get("id")]


# ---------------------------------------------------------------------------
# The apply runner — dry-run unless --execute. Returns the exit code; ONE
# JSON object lands on stdout; human notes go to stderr.
# ---------------------------------------------------------------------------
def _report(*, ok: bool, applied: bool, dry_run: bool, current_name: str,
            new_name: str, stage_count: int, delta: list, loc_marker: str,
            pipe_marker: str, note: str = "") -> None:
    """Emit the ONE JSON object (machine surface, stdout) for an apply run."""
    sys.stdout.write(json.dumps({
        "contract": "anthology-engine-pipeline-rename",
        "schema_version": 1,
        "ok": ok,
        "applied": applied,
        "dry_run": dry_run,
        "location_marker": loc_marker,
        "pipeline_id_marker": pipe_marker,
        "current_name": current_name,
        "new_name": new_name,
        "stages": stage_count,
        "delta": delta,
        "note": note,
    }, indent=2, sort_keys=True) + "\n")


def run_apply(client, v3, location_id: str, pipeline_id: str, old_name: str,
              new_name: str, *, execute: bool = False, out=None) -> int:
    """Apply (or dry-run) the pipeline rename.

    - dry-run (execute False, the default): reads the live pipeline, proves
      the name law, prints exactly the PUT it would send; the write is NEVER
      invoked.
    - execute (True): same reads, then the PUT, then the fail-closed
      read-back verify.
    Returns the house exit code. `client` is a registry CafClient (the proven
    2021-07-28 read surface for the list); `v3` is the module's own v3 client
    for the by-id read and the write.
    """
    out = out or sys.stderr
    loc_marker = _mask_location(location_id)
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    pipe_marker = _mask_id(pipeline_id)

    # ---- guards, before ANY read -----------------------------------------
    if not _valid_new_name(new_name):
        reg._stop(out, "The new pipeline name is invalid.",
                  ["--new-name must be non-empty and free of control characters.",
                   "Nothing was written (dry-run unless --execute)."])
        return EX_STOP
    if not old_name:
        reg._stop(out, "The expected current pipeline name is EMPTY.",
                  ["field-map.json pipeline.standard_pipeline_name is empty and "
                   "--old-name was not given.",
                   "Restore the contract name and re-run."])
        return EX_STOP
    if pipeline_id and not _looks_real(pipeline_id):
        reg._stop(out, "--pipeline-id does not look like a real pipeline id.",
                  ["A placeholder or whitespace-laden id never reaches a request.",
                   "Nothing was written (dry-run unless --execute)."])
        return EX_STOP

    # ---- resolve the target pipeline (reads only) ------------------------
    try:
        if pipeline_id:
            pipeline = v3.get_pipeline(pipeline_id)
            if not isinstance(pipeline, dict) or not pipeline.get("id"):
                raise PipelineMissing(
                    "pipeline %s read back empty" % _mask_id(pipeline_id))
        else:
            pipeline = find_pipeline_by_name(client, location_id, old_name)
            pipeline_id = pipeline.get("id") or ""
            pipe_marker = _mask_id(pipeline_id)
    except PipelineMissing as exc:
        reg._stop(out, "The rename target is NOT present.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        _report(ok=False, applied=False, dry_run=not execute,
                current_name="", new_name=new_name, stage_count=0,
                delta=[{"item": "pipeline", "status": "FAIL",
                        "detail": "target absent", "expected": old_name,
                        "live": None}],
                loc_marker=loc_marker, pipe_marker=pipe_marker)
        return EX_STOP
    except PipelineNotFound as exc:
        reg._stop(out, "The rename target id does not exist.",
                  [str(exc), "Pipeline id marker: %s" % pipe_marker,
                   "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        return EX_STOP
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot READ pipelines on "
                       "this location.",
                  ["Location marker: %s" % loc_marker,
                   "Grant the client's OWN location-scoped token the "
                   "opportunities scope and re-run.", "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.CafUnreachable as exc:  # includes UpstreamBlockedError (edge/WAF)
        out.write("[rename-applier] HELD: %s (marker %s). "
                  "NOT a token-scope problem; retryable.\n" % (exc, loc_marker))
        return EX_HELD

    # ---- identity law: byte-exact who we think BEFORE any write ----------
    current = (pipeline.get("name") or "").strip()
    if current != old_name:
        reg._stop(out, "The rename target is NOT named %r (live name: %r)."
                       % (old_name, current),
                  ["A rename may only target the pipeline that is byte-exact "
                   "the expected name — renaming anything else is a write to "
                   "the wrong record.",
                   "Location marker: %s" % loc_marker, "Nothing was written."])
        _report(ok=False, applied=False, dry_run=not execute,
                current_name=current, new_name=new_name,
                stage_count=len(_stage_ids(pipeline)),
                delta=[{"item": "pipeline_name", "status": "FAIL",
                        "detail": "target not byte-exact the expected name",
                        "expected": old_name, "live": current}],
                loc_marker=loc_marker, pipe_marker=pipe_marker)
        return EX_STOP
    if current == new_name:
        # Idempotent no-op: the pipeline already carries the target name.
        out.write("[rename-applier] idempotent no-op (marker %s): the pipeline "
                  "is already named %r. Nothing to write.\n"
                  % (loc_marker, new_name))
        _report(ok=True, applied=False, dry_run=False,
                current_name=current, new_name=new_name,
                stage_count=len(_stage_ids(pipeline)), delta=[],
                loc_marker=loc_marker, pipe_marker=pipe_marker,
                note="already named — no write performed")
        return EX_OK

    # ---- build the plan (never a body that could delete stages) ----------
    try:
        body = build_rename_body(pipeline, new_name)
    except RenameRefused as exc:
        reg._stop(out, "Cannot plan the rename.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "Nothing was written."])
        return EX_STOP
    stage_count = len(body["stages"])

    if not execute:
        out.write("[rename-applier] DRY-RUN (no --execute, marker %s): would "
                  "PUT /opportunities/pipelines/%s with name %r and %d "
                  "stage(s) echoed byte-identical (ids preserved, no stage "
                  "added, removed, or reordered). No write performed.\n"
                  % (loc_marker, pipe_marker, new_name, stage_count))
        _report(ok=True, applied=False, dry_run=True,
                current_name=current, new_name=new_name,
                stage_count=stage_count, delta=[],
                loc_marker=loc_marker, pipe_marker=pipe_marker,
                note="dry-run — pass --execute to apply the PUT")
        return EX_OK

    # ---- the write (--execute only) --------------------------------------
    try:
        v3.update_pipeline(pipeline_id, body)
    except reg.ScopeDenied:
        reg._stop(out, "The Convert and Flow token cannot WRITE pipelines on "
                       "this location.",
                  ["Location marker: %s" % loc_marker,
                   "Grant the client's OWN location-scoped token the "
                   "opportunities.write scope and re-run.", "AF-AE-PIT-SCOPE."])
        _report(ok=False, applied=False, dry_run=False,
                current_name=current, new_name=new_name,
                stage_count=stage_count,
                delta=[{"item": "pipeline", "status": "FAIL",
                        "detail": "write scope denied", "expected": new_name,
                        "live": current}],
                loc_marker=loc_marker, pipe_marker=pipe_marker)
        return EX_STOP
    except reg.CafValidation as exc:
        reg._stop(out, "Convert and Flow REFUSED the pipeline update.",
                  [str(exc), "Location marker: %s" % loc_marker,
                   "The pipeline was NOT renamed. A 400/409/422 refusal is a "
                   "data contract problem (e.g. the new name collides "
                   "case-insensitively with another pipeline) — resolve it "
                   "and re-run.", "AF-AE-PIPELINE-RENAME-VALIDATION."])
        _report(ok=False, applied=False, dry_run=False,
                current_name=current, new_name=new_name,
                stage_count=stage_count,
                delta=[{"item": "pipeline", "status": "FAIL",
                        "detail": "Convert and Flow validation refusal",
                        "expected": new_name, "live": current}],
                loc_marker=loc_marker, pipe_marker=pipe_marker)
        return EX_STOP
    except reg.CafUnreachable as exc:  # includes UpstreamBlockedError
        out.write("[rename-applier] HELD: %s (marker %s). "
                  "The PUT was NOT confirmed.\n" % (exc, loc_marker))
        return EX_HELD

    # ---- read-back verify (fail-closed) ----------------------------------
    try:
        live = v3.get_pipeline(pipeline_id)
    except reg.CafUnreachable as exc:
        out.write("[rename-applier] HELD (marker %s): the PUT returned success "
                  "but the read-back FAILED (%s). The live name is "
                  "UNDETERMINED — never reported as renamed. Re-run to verify.\n"
                  % (loc_marker, exc))
        return EX_HELD
    except reg.ScopeDenied as exc:
        out.write("[rename-applier] HELD (marker %s): the PUT returned success "
                  "but the read-back was scope-denied (%s). The live name is "
                  "UNDETERMINED — never reported as renamed.\n"
                  % (loc_marker, exc))
        return EX_HELD

    live_name = (live.get("name") or "").strip()
    live_ids = _stage_ids(live)
    expected_ids = _stage_ids(body) if isinstance(body, dict) else []
    delta = []
    if live_name != new_name:
        delta.append({"item": "pipeline_name", "status": "FAIL",
                      "detail": "read-back name not byte-exact after the PUT",
                      "expected": new_name, "live": live_name})
    if live_ids != expected_ids:
        delta.append({"item": "pipeline_stages", "status": "FAIL",
                      "detail": "stage id list drifted after the PUT "
                                "(added/removed/reordered)",
                      "expected": len(expected_ids), "live": len(live_ids)})
    if delta:
        reg._stop(out, "The PUT succeeded but the read-back does NOT match.",
                  [json.dumps(delta, sort_keys=True),
                   "Location marker: %s" % loc_marker,
                   "The live state is NOT the verified rename — investigate "
                   "before any further rename."])
        _report(ok=False, applied=True, dry_run=False,
                current_name=live_name, new_name=new_name,
                stage_count=len(live_ids), delta=delta,
                loc_marker=loc_marker, pipe_marker=pipe_marker)
        return EX_MISMATCH

    out.write("[rename-applier] OK (marker %s): %r renamed to %r and "
              "read-back verified byte-exact; %d stage(s) preserved (ids and "
              "order unchanged).\n"
              % (loc_marker, old_name, new_name, len(live_ids)))
    _report(ok=True, applied=True, dry_run=False,
            current_name=live_name, new_name=new_name,
            stage_count=len(live_ids), delta=[],
            loc_marker=loc_marker, pipe_marker=pipe_marker,
            note="applied and verified")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network, no credentials) — proves the pure logic:
# golden state passes, every attack fixture is refused, the write gate is
# honored by the runner itself, and the PUT body is never built from anything
# but the live read-back.
# ---------------------------------------------------------------------------
class _FakeCaf:
    """Deterministic pipeline-listing stub (mirrors pipeline_check's seam):
    'pipelines' fixture, 'behavior' for scope/edge/transport."""

    def __init__(self, pipelines=None, behavior="ok"):
        self._pipelines = [dict(p) for p in (pipelines or [])]
        self._behavior = behavior
        self.calls = []

    def list_pipelines(self, location_id):
        self.calls.append(("list", location_id))
        if self._behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return [dict(p) for p in self._pipelines]


class _FakeV3:
    """Deterministic v3 client stub: get/update per pipeline id; behaviors for
    read-back drift, validation refusals, scope/edge/transport, and a put that
    succeeds while the read-back fails."""

    def __init__(self, pipeline=None, put_behavior="ok", get_behavior="ok",
                 readback=None):
        self._pipeline = dict(pipeline) if pipeline else None
        self._put_behavior = put_behavior
        self._get_behavior = get_behavior
        self._readback = dict(readback) if readback else None
        self.puts = []
        self.gets = []

    def get_pipeline(self, pipeline_id):
        self.gets.append(pipeline_id)
        if self._get_behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._get_behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._get_behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        if self._get_behavior == "missing":
            raise PipelineNotFound("pipeline id not found (HTTP 404)")
        if self._readback is not None:
            return dict(self._readback)
        return dict(self._pipeline) if self._pipeline else {}

    def update_pipeline(self, pipeline_id, body):
        self.puts.append((pipeline_id, body))
        if self._put_behavior == "scope":
            raise reg.ScopeDenied("token not authorized for this scope (HTTP 403)")
        if self._put_behavior == "validation":
            raise reg.CafValidation("Convert and Flow rejected the PUT (HTTP 422)")
        if self._put_behavior == "edge":
            raise reg.UpstreamBlockedError("HTTP 403 did NOT match a scope signature")
        if self._put_behavior == "transport":
            raise reg.CafUnreachable("transport failure (fixture)")
        return dict(body)


def _golden_pipeline(name="Anthology Engine") -> dict:
    return {"id": "pipe_ren", "name": name,
            "stages": [
                {"id": "stg_0", "name": "Intake", "position": 0},
                {"id": "stg_1", "name": "Avatar", "position": 1},
                {"id": "stg_2", "name": "Tone", "position": 2},
            ]}


def _run_apply(*, caf, v3, old_name="Anthology Engine", new_name="Anthology "
               "Engine 2", execute=False, pipeline_id=""):
    """Self-test helper: capture stdout/stderr and return (exit, report)."""
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = run_apply(caf, v3, "loc_tmpl", pipeline_id, old_name, new_name,
                       execute=execute, out=io.StringIO())
    report = None
    try:
        report = json.loads(buf.getvalue())
    except ValueError:
        report = None
    return rc, report


def _self_test_body(dev) -> None:
    global _V3Client  # test 15 patches the module global so the CLI surface
    # stays OFFLINE; restored in its finally block.
    want = _standard_pipeline_name
    assert want, "contract name must not be empty"
    assert want == "Anthology Engine", "standard_pipeline_name drifted from the U03 contract"

    # ---- golden DRY-RUN: the write gate is honored by the runner itself ----
    # 1. dry-run: PASS, applied False, and the PUT was NEVER invoked.
    caf = _FakeCaf(pipelines=[_golden_pipeline()])
    v3 = _FakeV3(pipeline=_golden_pipeline())
    rc, report = _run_apply(caf=caf, v3=v3, new_name="Anthology Engine 2")
    assert rc == EX_OK, "golden dry-run must exit 0, got %s" % rc
    assert report and report["ok"] is True, "golden dry-run must carry ok true"
    assert report["applied"] is False and report["dry_run"] is True, \
        "dry-run must report applied false / dry_run true"
    assert v3.puts == [], "dry-run must NEVER invoke the PUT (write gate)"
    assert caf.calls == [("list", "loc_tmpl")], \
        "unexpected read calls: %s" % (caf.calls,)

    # 2. dry-run by --pipeline-id: reads GET-by-id, still no PUT.
    v3b = _FakeV3(pipeline=_golden_pipeline())
    rc2, report2 = _run_apply(caf=_FakeCaf(), v3=v3b, pipeline_id="pipe_ren",
                              new_name="Anthology Engine 2")
    assert rc2 == EX_OK and report2 and report2["ok"] is True
    assert v3b.puts == [], "id-targeted dry-run must NEVER invoke the PUT"
    assert v3b.gets == ["pipe_ren"], "id-targeted dry-run must read by id once"

    # 3. golden EXECUTE: one PUT with the name changed and the stages echoed
    # byte-for-byte (ids preserved); read-back passes; exit 0.
    v3c = _FakeV3(pipeline=_golden_pipeline(),
                  readback=_golden_pipeline(name="Anthology Engine 2"))
    rc3, report3 = _run_apply(caf=caf, v3=v3c, new_name="Anthology Engine 2",
                              execute=True)
    assert rc3 == EX_OK, "golden execute must exit 0, got %s" % rc3
    assert report3 and report3["applied"] is True and report3["dry_run"] is False
    assert len(v3c.puts) == 1, "execute must PUT exactly once"
    pid, body = v3c.puts[0]
    assert pid == "pipe_ren", "PUT must target the resolved pipeline id"
    assert body["name"] == "Anthology Engine 2", \
        "PUT body must carry only the new name change"
    assert body["stages"] == _golden_pipeline()["stages"], \
        "PUT body must echo the read-back stages byte-for-byte (complete replacement)"

    # 4. idempotent no-op: already named -> PASS, no write.
    caf_d = _FakeCaf(pipelines=[_golden_pipeline(name="Anthology Engine 2")])
    v3d = _FakeV3(pipeline=_golden_pipeline(name="Anthology Engine 2"))
    rc4, report4 = _run_apply(caf=caf_d, v3=v3d, old_name="Anthology Engine 2",
                              new_name="Anthology Engine 2", execute=True)
    assert rc4 == EX_OK and report4 and report4["ok"] is True
    assert report4["applied"] is False
    assert v3d.puts == [], "idempotent no-op must never invoke the PUT"

    # ---- attack fixtures: every mutation REFUSED --------------------------
    # 5. pipeline ABSENT -> STOP (exit 2), no write.
    rc5, report5 = _run_apply(caf=_FakeCaf(pipelines=[]), v3=_FakeV3(),
                              new_name="Anthology Engine 2", execute=True)
    assert rc5 == EX_STOP, "absent target must STOP, got %s" % rc5
    assert report5 and report5["ok"] is False and report5["applied"] is False

    # 6. target named differently than expected -> STOP (write to the wrong
    # record must be impossible). Exercised through the --pipeline-id path:
    # the by-id read returns a record that is NOT byte-exact the expected
    # name, so the identity law refuses before any write.
    v3f = _FakeV3(pipeline=_golden_pipeline(name="Something Else"))
    rc6, report6 = _run_apply(caf=_FakeCaf(), v3=v3f, pipeline_id="pipe_ren",
                              new_name="Anthology Engine 2", execute=True)
    assert rc6 == EX_STOP, "name-mismatched target must STOP, got %s" % rc6
    assert report6 and report6["ok"] is False and report6["applied"] is False
    assert v3f.puts == [], "name-mismatched target must never be written"
    # 6b. ... and through the by-name path: a pipeline present under ANY other
    # name is treated as absent (find-by-name cannot tell renamed from
    # absent) -> STOP.
    rc6b, _ = _run_apply(caf=_FakeCaf(pipelines=[_golden_pipeline(name="Something Else")]),
                         v3=_FakeV3(), new_name="Anthology Engine 2", execute=True)
    assert rc6b == EX_STOP, "renamed-listed target must STOP, got %s" % rc6b

    # 7. empty stages read-back -> STOP; a body that could delete stages is
    # NEVER constructed — not even in dry-run. Exercised through the
    # --pipeline-id path (the by-id read returns the stageless record).
    stageless = dict(_golden_pipeline(), stages=[])
    rc7, report7 = _run_apply(caf=_FakeCaf(), v3=_FakeV3(pipeline=stageless),
                              pipeline_id="pipe_ren",
                              new_name="Anthology Engine 2", execute=True)
    assert rc7 == EX_STOP, "stageless target must STOP, got %s" % rc7
    assert report7 is None or report7.get("applied") is False
    rc7b, _ = _run_apply(caf=_FakeCaf(), v3=_FakeV3(pipeline=stageless),
                         pipeline_id="pipe_ren",
                         new_name="Anthology Engine 2")
    assert rc7b == EX_STOP, "stageless target must STOP in dry-run too"

    # 8. read-back name drift after a successful PUT -> exit 5 with a delta.
    v3g = _FakeV3(pipeline=_golden_pipeline(),
                  readback=_golden_pipeline(name="Anthology Engine 2 TYPO"))
    rc8, report8 = _run_apply(caf=caf, v3=v3g, new_name="Anthology Engine 2",
                              execute=True)
    assert rc8 == EX_MISMATCH, "read-back name drift must exit 5, got %s" % rc8
    assert report8 and report8["ok"] is False and report8["applied"] is True
    assert any("pipeline_name" in str(d.get("item")) for d in report8["delta"]), \
        "drift report must carry the name delta"

    # 9. read-back stage-id drift after a successful PUT -> exit 5.
    drifted = _golden_pipeline(name="Anthology Engine 2")
    drifted["stages"] = [dict(st) for st in drifted["stages"][:2]]
    rc9, report9 = _run_apply(caf=caf, v3=_FakeV3(pipeline=_golden_pipeline(),
                                                  readback=drifted),
                              new_name="Anthology Engine 2", execute=True)
    assert rc9 == EX_MISMATCH, "stage drift must exit 5, got %s" % rc9
    assert any("pipeline_stages" in str(d.get("item")) for d in report9["delta"])

    # 10. PUT succeeded but read-back unreachable -> HELD (exit 3), applied
    # state UNDETERMINED — never reported as renamed, never exit 0.
    v3h = _FakeV3(pipeline=_golden_pipeline(), get_behavior="transport")
    rc10, _ = _run_apply(caf=caf, v3=v3h, new_name="Anthology Engine 2",
                         execute=True)
    assert rc10 == EX_HELD, "applied-but-unreadable must be HELD, got %s" % rc10
    assert len(v3h.puts) == 1, "the PUT did happen — the HELD is about verify"

    # 11. Convert and Flow validation refusal on the PUT -> STOP (exit 2).
    v3i = _FakeV3(pipeline=_golden_pipeline(), put_behavior="validation")
    rc11, report11 = _run_apply(caf=caf, v3=v3i, new_name="Anthology Engine 2",
                                execute=True)
    assert rc11 == EX_STOP, "validation refusal must STOP, got %s" % rc11
    assert report11 and report11["applied"] is False

    # 12. scope denied / edge / transport on the READ -> STOP / HELD, never a
    # fabricated plan.
    for behavior, expect in (("scope", EX_STOP), ("edge", EX_HELD),
                             ("transport", EX_HELD)):
        rc12, _ = _run_apply(caf=_FakeCaf(behavior=behavior), v3=_FakeV3(),
                             new_name="Anthology Engine 2")
        assert rc12 == expect, "%s read must exit %s, got %s" % (behavior, expect, rc12)

    # 13. invalid new name -> STOP before any read/write.
    rc13, _ = _run_apply(caf=caf, v3=_FakeV3(), new_name="")
    assert rc13 == EX_STOP, "empty new name must STOP, got %s" % rc13
    rc13b, _ = _run_apply(caf=caf, v3=_FakeV3(), new_name="Bad\x00Name")
    assert rc13b == EX_STOP, "control-char new name must STOP, got %s" % rc13b

    # 14. placeholder pipeline id -> STOP, never a request.
    v3j = _FakeV3(pipeline=_golden_pipeline())
    rc14, _ = _run_apply(caf=caf, v3=v3j, pipeline_id="REPLACE-ME",
                         new_name="Anthology Engine 2", execute=True)
    assert rc14 == EX_STOP, "placeholder pipeline id must STOP, got %s" % rc14
    assert v3j.gets == [] and v3j.puts == [], \
        "placeholder id must never reach a request"

    # 15. CLI: apply WITHOUT --execute -> exit 0, dry_run true, applied false,
    # and the PUT is never invoked (the gate holds at the CLI boundary too).
    # The credential/client surface is monkeypatched so the self-test stays
    # OFFLINE — no real token resolution, no network, and the fake v3 client
    # records whether any PUT was attempted.
    import contextlib
    real_resolve_pit = reg.resolve_pit
    real_resolve_location = reg.resolve_location
    real_caf_cls = reg.CafClient
    real_v3_cls = _V3Client

    class _CliFakeCaf:
        def list_pipelines(self, location_id):
            return [dict(_golden_pipeline())]

    cli_v3 = _FakeV3(pipeline=_golden_pipeline())
    reg.resolve_pit = lambda: ("CONVERT_AND_FLOW_PIT", "pit-fake")
    reg.resolve_location = lambda override="": (
        ("(--location-id)", override) if override else ("GOHIGHLEVEL_LOCATION_ID", "loc_tmpl"))
    reg.CafClient = lambda token, timeout=15: _CliFakeCaf()
    _V3Client = lambda token, timeout=15: cli_v3  # noqa: F811 — module-global patch
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc15 = main(["apply", "--new-name", "Anthology Engine 2",
                         "--location-id", "loc_tmpl"])
    finally:
        reg.resolve_pit = real_resolve_pit
        reg.resolve_location = real_resolve_location
        reg.CafClient = real_caf_cls
        _V3Client = real_v3_cls
    assert rc15 == EX_OK, "CLI apply without --execute must exit 0, got %s" % rc15
    report15 = json.loads(buf.getvalue())
    assert report15["dry_run"] is True and report15["applied"] is False
    assert cli_v3.puts == [], "CLI dry-run must never invoke the PUT"

    dev.write("rename_applier self-test: OK (name law pinned to field-map "
              "pipeline.standard_pipeline_name %r; golden dry-run + golden "
              "execute + idempotent no-op PASS; 15 attack fixtures refused: "
              "absent / name-mismatch / stageless / read-back-name-drift / "
              "read-back-stage-drift / applied-unreadable-HELD / validation-"
              "refusal / scope-denied / edge-block / transport / empty-name / "
              "control-char-name / placeholder-id / CLI-write-gate; the PUT is "
              "never invoked without --execute)\n" % want)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[rename-applier] SELF-TEST FAILED "
                         "(U03 RENAME ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


# ---------------------------------------------------------------------------
# CLI — house shape: plan / apply / self-test subcommands; --execute is the
# ONLY write gate.
# ---------------------------------------------------------------------------
def _offline_plan(old_name: str) -> int:
    """Offline plan: the PUT surface and semantics with sources — no network,
    no credential needed."""
    print(json.dumps({
        "contract": "anthology-engine-pipeline-rename-plan",
        "schema_version": 1,
        "expected_current_name": old_name,
        "write_surface": "PUT /opportunities/pipelines/{pipelineId} "
                         "(Version: v3; documented live — HighLevel update-"
                         "pipeline; scopes opportunities.readonly / "
                         "opportunities.write)",
        "semantics": "the stages array is a COMPLETE REPLACEMENT — the PUT "
                     "body echoes the read-back stages byte-for-byte (every "
                     "id preserved) so a name-only rename touches nothing "
                     "else",
        "write_gate": "the PUT is performed ONLY with --execute; without it "
                      "the apply run is a read-only dry-run",
        "verify": "post-PUT read-back must be byte-exact the new name with "
                  "the same stage ids in the same order — any drift is "
                  "exit 5, an unreadable read-back is HELD (exit 3)",
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="rename_applier.py",
        description="Pipeline rename APPLIER against the Anthology Convert and "
                    "Flow location (U03): PUT /opportunities/pipelines/{id} "
                    "under Version: v3, applied ONLY with --execute. Without "
                    "--execute the run is a read-only dry-run that prints "
                    "exactly the PUT it would send — nothing is written, ever. "
                    "One JSON object on stdout; fail-closed; never prints a "
                    "secret (Skill 59).")
    ap.add_argument("--location-id", default="",
                    help="override the location id (default: the standard "
                         "location labels; never printed)")
    ap.add_argument("--pipeline-id", default="",
                    help="target pipeline by id (default: resolve the standard "
                         "pipeline BY NAME from field-map.json)")
    ap.add_argument("--old-name", default="",
                    help="expected CURRENT name (default: field-map.json "
                         "pipeline.standard_pipeline_name)")
    ap.add_argument("--new-name", default="",
                    help="the replacement name (required)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                         "standard name)")
    ap.add_argument("--execute", action="store_true",
                    help="REQUIRED for the write: perform the PUT. Without it "
                         "the apply run is a read-only dry-run")
    ap.add_argument("cmd", nargs="?", choices=["plan", "apply", "self-test"],
                    default="apply")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()

        old_name = (args.old_name.strip() or
                    (reg.load_field_map(Path(args.field_map).expanduser())
                     .get("pipeline") or {}).get("standard_pipeline_name") or "")
        if not old_name:
            reg._stop(sys.stderr, "The expected current pipeline name is EMPTY.",
                      [str(Path(args.field_map).expanduser()),
                       "pipeline.standard_pipeline_name is empty and --old-name "
                       "was not given — restore the contract name and re-run."])
            return EX_MISMATCH

        if args.cmd == "plan":
            return _offline_plan(old_name)

        # ---- apply (dry-run unless --execute) ----
        new_name = args.new_name.strip()
        if not new_name:
            reg._stop(sys.stderr, "--new-name is required for apply.",
                      ["Nothing was written (dry-run unless --execute)."])
            return EX_STOP

        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration "
                                  "token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the client's OWN pit- token under a standard label "
                       "and re-run.", "A truthful dry-run needs the live read."])
            return EX_STOP
        loc_label, location_id = reg.resolve_location(args.location_id)
        if not location_id:
            checked = ", ".join(reg.LOCATION_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow location id is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "Set the location id under a standard label (or pass "
                       "--location-id) and re-run."])
            return EX_STOP
        client = reg.CafClient(token)
        v3 = _V3Client(token)

        return run_apply(client, v3, location_id, args.pipeline_id.strip(),
                         old_name, new_name, execute=args.execute,
                         out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[rename-applier] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[rename-applier] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[rename-applier] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafValidation as exc:
        sys.stderr.write("[rename-applier] STOP: %s\n" % exc)
        return EX_STOP
    except (PipelineMissing, PipelineNotFound, RenameRefused) as exc:
        sys.stderr.write("[rename-applier] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[rename-applier] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
