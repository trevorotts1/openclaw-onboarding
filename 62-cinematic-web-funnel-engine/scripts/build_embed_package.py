#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_embed_package.py — Skill 62 (Cinematic and Web Funnel Engine), build
unit U18.

Spec Section 14.2 ("Whole-page GHL iframe mode") names the deliverable:

    iframe HTML; responsive wrapper CSS; postMessage child script for
    height updates and conversion events; parent script for dynamic height
    and event forwarding; approved-origin allowlist; Content Security
    Policy `frame-ancestors` configuration; fallback direct URL; test
    instructions for desktop and mobile GHL wrappers.

The child half of the postMessage protocol already ships with every
generated site as `templates/components/EmbedBridge.tsx` (built in U15,
which explicitly deferred "the full embed HTML package, allowed-origin
allowlist file, and parent-side script" to this unit). This module builds
the other half: it takes an already-deployed project (a
`deployment-receipt.json`, structure/deployment-receipt.schema.json, U6)
plus an operator/client-approved `embed-request.json`
(structure/embed-request.schema.json, this unit) and materializes
`templates/embed/` into a concrete, per-project GHL iframe embed package —
the literal HTML block a client pastes into a GHL Custom HTML/Code element,
plus the standalone CSS/JS/allowlist/CSP/test-instructions artifacts spec
14.2 lists individually.

This module is the PRODUCER and runs its own fail-closed checks inline
(spec 19.4 break-it cases this unit specifically covers: malicious/invalid
iframe origin, missing deployment receipt, deployment not ready, wildcard
ancestor origin, self-embed collision). A future phase-spine registration
unit may wire a dedicated `prove_embed.py` gate the same way `prove_site.py`
re-derives `build_site.py`'s claims from disk (that split is out of this
unit's file area) — until then, `embed-receipt.json`'s own `checks{}` +
`status` fields are independently re-derived from the materialized
`embed_dir` on disk before being trusted, exactly like every other
build/receipt pair in this skill.

Security posture (spec Section 20):
  - `sanitize_slug()` is an ALLOWLIST transform ([a-z0-9-] only) — the same
    pattern `build_site.py` uses, kept as a small local copy here rather
    than an import so this unit stays file-disjoint from U15/U16's area.
  - `validate_ancestor_origin()` / `validate_https_url()` reject wildcard
    ("*"), empty/"null", non-https, userinfo-bearing, and path/query-bearing
    origins by construction (spec 19.4 "hostile iframe origin").
  - every generated artifact is scanned for leftover `__CWFE_` template
    tokens and for secret-shaped strings before the receipt is allowed to
    report `status: "pass"`.
  - no secret value is ever read, embedded, or logged — the embed package
    is a static HTML/CSS/JS bundle with no provider credentials at all.

stdlib only for orchestration (ADR-5); no network calls.

Exit codes: 0 = embed-receipt.json written with status "pass"; 1 = a real
failure was captured (either a precondition failure raised before any
output was materialized, or output was materialized but a check failed —
both are written/reported, never silently swallowed); 2 = usage error (bad
CLI args) before any build was attempted.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_STRUCTURE_DIR = _SKILL_DIR / "structure"
_TEMPLATES_DIR = _SKILL_DIR / "templates" / "embed"
_FIXTURE_DIR = _SKILL_DIR / "tests" / "fixtures" / "embed-fixture"

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR / "lib"))
import json_schema_lite as jsl  # noqa: E402

EXIT_OK = 0
EXIT_BUILD_FAILED = 1
EXIT_USAGE = 2

SCHEMA_VERSION = "1.0.0"
DEFAULT_HEIGHT_PX = 800

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

# A bare-host pattern requiring at least one dot (i.e. a real domain, not a
# single label) — deliberately stricter than RFC 1123 in one direction: it
# refuses to treat a lone label like "localhost" as a valid ancestor/child
# origin, matching spec 20's least-privilege posture for production embed
# targets rather than accommodating local dev shortcuts.
_HOST_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)

_NESTED_SCROLL_PATTERN = re.compile(r"height\s*:\s*100vh", re.IGNORECASE)
_LEFTOVER_TOKEN_PATTERN = re.compile(r"__CWFE_[A-Z_]+__")

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"pit-[A-Za-z0-9\-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}"),
    re.compile(
        r"""["']?(api|secret|access|client)[_-]?(key|token)["']?\s*[:=]\s*["'][A-Za-z0-9\-_]{16,}["']""",
        re.IGNORECASE,
    ),
]

TEXT_OUTPUT_SUFFIXES = {".html", ".css", ".js", ".md", ".json"}


class EmbedBuildError(Exception):
    """Raised for any precondition failure or captured build failure. Both
    are reported to the caller; neither is silently swallowed."""


# ---------------------------------------------------------------------------
# Slug sanitization (spec 20 "sanitize all generated paths and slugs")
# ---------------------------------------------------------------------------
def sanitize_slug(raw: str) -> str:
    """Allowlist transform: keep only [a-z0-9-], collapse repeats, trim
    leading/trailing hyphens, cap length. A path-traversal payload cannot
    survive this by construction — every character outside [a-z0-9] is
    discarded, never reinterpreted."""
    lowered = (raw or "").strip().lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    truncated = collapsed[:63].strip("-")
    if not truncated or not _SLUG_PATTERN.match(truncated):
        raise EmbedBuildError(
            f"project slug sanitizes to an empty/invalid value from input {raw!r} — refusing to build"
        )
    return truncated


# ---------------------------------------------------------------------------
# Origin / URL validation (spec 20 "validate iframe origins"; 19.4 "hostile
# iframe origin")
# ---------------------------------------------------------------------------
def validate_ancestor_origin(raw: str) -> str:
    """Validates one entry of embed-request.json's allowed_ancestor_origins.
    Must be a bare https origin: scheme + host [+ port], no userinfo, no
    path/query/fragment, never '*' or empty/null. Returns the normalized
    "https://host[:port]" form."""
    candidate = (raw or "").strip()
    if candidate in ("", "*", "null", "None", "none"):
        raise EmbedBuildError(
            f"allowed ancestor origin must be a specific https origin, got {raw!r} — "
            "wildcard/empty/null origins are refused (spec 20 'validate iframe origins')"
        )
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme != "https":
        raise EmbedBuildError(f"allowed ancestor origin must use https, got {raw!r}")
    if "@" in parsed.netloc:
        raise EmbedBuildError(f"allowed ancestor origin must not contain userinfo, got {raw!r}")
    if not parsed.hostname:
        raise EmbedBuildError(f"allowed ancestor origin has no host, got {raw!r}")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise EmbedBuildError(
            f"allowed ancestor origin must be a bare origin with no path/query/fragment, got {raw!r}"
        )
    if not _HOST_PATTERN.match(parsed.hostname.lower()):
        raise EmbedBuildError(f"allowed ancestor origin has an invalid host, got {raw!r}")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname.lower()}{port}"


def validate_https_url(raw: str, *, field_name: str) -> str:
    """Looser than validate_ancestor_origin() — a path is allowed (these are
    direct/deployment URLs, not bare origins) — but scheme/host are still
    strictly checked."""
    candidate = (raw or "").strip()
    if not candidate:
        raise EmbedBuildError(f"{field_name} is required and must be a non-empty https URL")
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme != "https":
        raise EmbedBuildError(f"{field_name} must be https, got {raw!r}")
    if "@" in parsed.netloc:
        raise EmbedBuildError(f"{field_name} must not contain userinfo, got {raw!r}")
    if not parsed.hostname or not _HOST_PATTERN.match(parsed.hostname.lower()):
        raise EmbedBuildError(f"{field_name} has an invalid host, got {raw!r}")
    return candidate


def derive_origin(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


# ---------------------------------------------------------------------------
# Upstream artifact loading
# ---------------------------------------------------------------------------
def load_deployment_receipt(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "deployment-receipt.json"
    if not path.is_file():
        raise EmbedBuildError(
            f"deployment-receipt.json not found at {path} — a deployment must exist before an embed package can wrap it"
        )
    receipt = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((_STRUCTURE_DIR / "deployment-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        raise EmbedBuildError("deployment-receipt.json failed schema validation: " + "; ".join(errors))
    if receipt["status"] != "ready":
        raise EmbedBuildError(
            f"deployment-receipt.json status is {receipt['status']!r}, not 'ready' — refusing to embed a non-ready deployment"
        )
    validate_https_url(receipt.get("url") or "", field_name="deployment-receipt.json url")
    return receipt


def load_embed_request(run_dir: Path) -> Dict[str, Any]:
    path = run_dir / "embed-request.json"
    if not path.is_file():
        raise EmbedBuildError(f"embed-request.json not found at {path}")
    request = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((_STRUCTURE_DIR / "embed-request.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(request, schema)
    if errors:
        raise EmbedBuildError("embed-request.json failed schema validation: " + "; ".join(errors))
    return request


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------
def _render(template_name: str, tokens: Dict[str, str]) -> str:
    path = _TEMPLATES_DIR / template_name
    if not path.is_file():
        raise EmbedBuildError(f"embed template missing: {path}")
    text = path.read_text(encoding="utf-8")
    for token, value in tokens.items():
        text = text.replace(token, value)
    return text


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.suffix or ".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


# ---------------------------------------------------------------------------
# Static checks (spec 17.5-flavored gate, applied to the embed package)
# ---------------------------------------------------------------------------
def _read_text_outputs(embed_dir: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for path in sorted(embed_dir.rglob("*")):
        if path.is_file() and path.suffix in TEXT_OUTPUT_SUFFIXES:
            out[str(path.relative_to(embed_dir))] = path.read_text(encoding="utf-8")
    return out


def check_no_nested_scroll_trap(texts: Dict[str, str]) -> Tuple[bool, List[str]]:
    hits = [name for name, text in texts.items() if _NESTED_SCROLL_PATTERN.search(text)]
    return (len(hits) == 0, hits)


def check_has_iframe_title(texts: Dict[str, str], iframe_title: str) -> bool:
    host = texts.get("host-snippet.html", "")
    needle = f'title="{iframe_title}"'
    return bool(iframe_title) and needle in host


def check_has_fallback_link(texts: Dict[str, str], fallback_url: str) -> bool:
    host = texts.get("host-snippet.html", "")
    needle = f'href="{fallback_url}"'
    return bool(fallback_url) and needle in host


def check_no_leftover_placeholders(texts: Dict[str, str]) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    for name, text in texts.items():
        found = _LEFTOVER_TOKEN_PATTERN.findall(text)
        if found:
            hits.append(f"{name}: {sorted(set(found))}")
    return (len(hits) == 0, hits)


def check_no_hardcoded_secrets(texts: Dict[str, str]) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    for name, text in texts.items():
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{name}: matched {pattern.pattern}")
    return (len(hits) == 0, hits)


def check_valid_json_outputs(embed_dir: Path) -> Tuple[bool, List[str]]:
    bad: List[str] = []
    for name in ("allowed-origins.json", "csp-headers.json"):
        path = embed_dir / name
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            bad.append(f"{name}: {exc}")
    return (len(bad) == 0, bad)


def check_no_wildcard_or_invalid_origin(embed_dir: Path) -> Tuple[bool, List[str]]:
    """Re-reads the WRITTEN allowed-origins.json from disk (not the
    in-memory list) and re-validates every entry — the same
    never-trust-your-own-bookkeeping posture every prove_*.py in this skill
    already applies to its producer."""
    path = embed_dir / "allowed-origins.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (False, [f"allowed-origins.json unreadable: {exc}"])
    origins = data.get("allowed_ancestor_origins", [])
    bad: List[str] = []
    for origin in origins:
        try:
            validate_ancestor_origin(origin)
        except EmbedBuildError as exc:
            bad.append(str(exc))
    if not origins:
        bad.append("allowed-origins.json has no entries")
    return (len(bad) == 0, bad)


def check_child_origin_matches_deployment(run_dir: Path, child_origin: str) -> bool:
    """Re-reads deployment-receipt.json fresh from disk and re-derives the
    origin, instead of trusting the value already computed earlier in this
    same process."""
    path = run_dir / "deployment-receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    return derive_origin(receipt["url"]) == child_origin


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------
@dataclass
class EmbedResult:
    receipt: Dict[str, Any]
    embed_dir: Path


def build_embed_package(
    run_dir: Path,
    *,
    embed_dir: Optional[Path] = None,
    project_slug_override: Optional[str] = None,
) -> EmbedResult:
    deployment = load_deployment_receipt(run_dir)
    request = load_embed_request(run_dir)

    slug = sanitize_slug(project_slug_override or request.get("project_slug") or deployment["project_id"])

    allowed_ancestors = [validate_ancestor_origin(o) for o in request["allowed_ancestor_origins"]]
    # dedupe while preserving order (schema already requires uniqueItems on
    # the raw input, but normalization — e.g. differing port defaults —
    # could theoretically collapse two distinct raw entries to one origin)
    seen: List[str] = []
    for origin in allowed_ancestors:
        if origin not in seen:
            seen.append(origin)
    allowed_ancestors = seen

    hosted_url = deployment["url"]
    child_origin = derive_origin(hosted_url)
    if child_origin in allowed_ancestors:
        raise EmbedBuildError(
            f"allowed_ancestor_origins contains the hosted app's own origin ({child_origin}) — "
            "a page cannot legitimately list itself as its own parent"
        )

    fallback_url = validate_https_url(request["fallback_url"], field_name="embed-request.json fallback_url")
    iframe_title = request["iframe_title"]
    default_height_px = int(request.get("default_height_px") or DEFAULT_HEIGHT_PX)
    generated_at = _now()

    # HTML-escape BEFORE injecting into any attribute/text position. Both
    # values are client/operator-supplied free text (embed-request.json is
    # not a locked/sacred-copy artifact like content-manifest.json), so an
    # unescaped `"` could break out of the title="..."/href="..." wrapper
    # and smuggle a live attribute — the same quote-breakout class U15's QC
    # pass found and fixed in build_site.py's sanitize_copy_fragment().
    # The escaped forms are used everywhere these values are rendered
    # (including TEST-INSTRUCTIONS.md, where escaping a normal URL/title is
    # a no-op) so the fail-closed checks below can compare against the same
    # exact strings that were written to disk.
    escaped_iframe_title = html.escape(iframe_title, quote=True)
    escaped_fallback_url = html.escape(fallback_url, quote=True)

    resolved_embed_dir = embed_dir if embed_dir is not None else (run_dir / "embed")
    if resolved_embed_dir.exists():
        for child in resolved_embed_dir.iterdir():
            if child.is_file():
                child.unlink()
    resolved_embed_dir.mkdir(parents=True, exist_ok=True)

    base_tokens = {
        "__CWFE_IFRAME_SRC__": hosted_url,
        "__CWFE_IFRAME_TITLE__": escaped_iframe_title,
        "__CWFE_FALLBACK_URL__": escaped_fallback_url,
        "__CWFE_DEFAULT_HEIGHT_PX__": str(default_height_px),
        "__CWFE_CHILD_ORIGIN__": child_origin,
        "__CWFE_ALLOWED_ORIGINS_JSON__": json.dumps(allowed_ancestors),
        "__CWFE_PROJECT_SLUG__": slug,
        "__CWFE_GENERATED_AT__": generated_at,
    }

    wrapper_css = _render("wrapper.css.tmpl", base_tokens)
    parent_bridge_js = _render("parent-bridge.js.tmpl", base_tokens)
    iframe_fragment = _render("iframe-fragment.html.tmpl", base_tokens)
    fallback_fragment = _render("fallback-fragment.html.tmpl", base_tokens)
    test_instructions = _render("TEST-INSTRUCTIONS.md.tmpl", base_tokens)

    host_tokens = dict(base_tokens)
    host_tokens.update(
        {
            "__CWFE_INLINE_WRAPPER_CSS__": wrapper_css,
            "__CWFE_INLINE_PARENT_BRIDGE_JS__": parent_bridge_js,
            "__CWFE_INLINE_IFRAME_FRAGMENT__": iframe_fragment,
            "__CWFE_INLINE_FALLBACK_FRAGMENT__": fallback_fragment,
        }
    )
    host_snippet = _render("host-snippet.html.tmpl", host_tokens)

    _atomic_write_text(resolved_embed_dir / "wrapper.css", wrapper_css)
    _atomic_write_text(resolved_embed_dir / "parent-bridge.js", parent_bridge_js)
    _atomic_write_text(resolved_embed_dir / "iframe-fragment.html", iframe_fragment)
    _atomic_write_text(resolved_embed_dir / "fallback-fragment.html", fallback_fragment)
    _atomic_write_text(resolved_embed_dir / "host-snippet.html", host_snippet)
    _atomic_write_text(resolved_embed_dir / "TEST-INSTRUCTIONS.md", test_instructions)

    allowed_origins_doc = {
        "schema_version": SCHEMA_VERSION,
        "project_id": deployment["project_id"],
        "allowed_ancestor_origins": allowed_ancestors,
    }
    _atomic_write_json(resolved_embed_dir / "allowed-origins.json", allowed_origins_doc)

    csp_value = "frame-ancestors 'self' " + " ".join(allowed_ancestors) + ";"
    csp_doc = {
        "schema_version": SCHEMA_VERSION,
        "note": (
            "Merge this `headers` entry into the CHILD (hosted) app's own vercel.json — "
            "GHL cannot set this header; only the Vercel-hosted deployment's own response "
            "controls who may iframe it (spec 14.2)."
        ),
        "content_security_policy": csp_value,
        "vercel_json_fragment": {
            "headers": [
                {
                    "source": "/(.*)",
                    "headers": [{"key": "Content-Security-Policy", "value": csp_value}],
                }
            ]
        },
    }
    _atomic_write_json(resolved_embed_dir / "csp-headers.json", csp_doc)

    texts = _read_text_outputs(resolved_embed_dir)
    no_scroll_trap, scroll_trap_hits = check_no_nested_scroll_trap(texts)
    has_title = check_has_iframe_title(texts, escaped_iframe_title)
    has_fallback = check_has_fallback_link(texts, escaped_fallback_url)
    no_leftovers, leftover_hits = check_no_leftover_placeholders(texts)
    no_secrets, secret_hits = check_no_hardcoded_secrets(texts)
    valid_json, invalid_json_hits = check_valid_json_outputs(resolved_embed_dir)
    valid_origins, invalid_origin_hits = check_no_wildcard_or_invalid_origin(resolved_embed_dir)
    origin_matches = check_child_origin_matches_deployment(run_dir, child_origin)

    overall_ok = (
        no_scroll_trap
        and has_title
        and has_fallback
        and no_leftovers
        and no_secrets
        and valid_json
        and valid_origins
        and origin_matches
    )

    files: List[Dict[str, Any]] = []
    for path in sorted(resolved_embed_dir.rglob("*")):
        if path.is_file():
            data = path.read_bytes()
            files.append(
                {
                    "path": str(path.relative_to(resolved_embed_dir)),
                    "sha256": _sha256_bytes(data),
                    "bytes": len(data),
                }
            )

    receipt: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": deployment["project_id"],
        "project_slug": slug,
        "embed_dir": str(resolved_embed_dir),
        "hosted_url": hosted_url,
        "environment": deployment["environment"],
        "commit_sha": deployment["commit_sha"],
        "child_origin": child_origin,
        "allowed_ancestor_origins": allowed_ancestors,
        "files": files,
        "checks": {
            "no_nested_scroll_trap": no_scroll_trap,
            "has_iframe_title": has_title,
            "has_fallback_link": has_fallback,
            "no_leftover_placeholders": no_leftovers,
            "no_wildcard_or_invalid_origin": valid_origins,
            "no_hardcoded_secrets": no_secrets,
            "valid_json_outputs": valid_json,
            "child_origin_matches_deployment": origin_matches,
        },
        "status": "pass" if overall_ok else "failed",
        "created_at": generated_at,
    }

    schema = json.loads((_STRUCTURE_DIR / "embed-receipt.schema.json").read_text(encoding="utf-8"))
    errors = jsl.validate(receipt, schema)
    if errors:
        raise EmbedBuildError("generated embed-receipt.json failed its own schema: " + "; ".join(errors))

    _atomic_write_json(run_dir / "embed-receipt.json", receipt)

    if not overall_ok:
        details = []
        if not no_scroll_trap:
            details.append(f"height:100vh nested-scroll-trap pattern found in: {scroll_trap_hits}")
        if not has_title:
            details.append("host-snippet.html missing accessible iframe title")
        if not has_fallback:
            details.append("host-snippet.html missing fallback link")
        if not no_leftovers:
            details.append(f"leftover template tokens: {leftover_hits}")
        if not no_secrets:
            details.append(f"secret-shaped strings found: {secret_hits}")
        if not valid_json:
            details.append(f"invalid JSON outputs: {invalid_json_hits}")
        if not valid_origins:
            details.append(f"invalid ancestor origins on disk: {invalid_origin_hits}")
        if not origin_matches:
            details.append("child_origin does not match deployment-receipt.json on re-read")
        raise EmbedBuildError("embed package build failed: " + "; ".join(details))

    return EmbedResult(receipt=receipt, embed_dir=resolved_embed_dir)


def _self_test() -> bool:
    sys.path.insert(0, str(_FIXTURE_DIR))
    import make_embed_fixture as make_fixture  # noqa: E402  (fixture-local module; aliased to
    # avoid colliding in sys.modules with tests/fixtures/site-fixture/make_fixture.py — both are
    # loaded into the SAME process during `unittest discover`, and Python caches imports by
    # top-level module name, so two files literally named make_fixture.py would silently shadow
    # each other depending on import order)

    with tempfile.TemporaryDirectory(prefix="cwfe-build-embed-selftest-") as tmp:
        run_dir = Path(tmp) / "run"
        make_fixture.write_fixture_run_dir(run_dir)
        try:
            result = build_embed_package(run_dir)
        except EmbedBuildError as exc:
            print(f"RESULT: FAIL — {exc}")
            return False
        ok = (
            result.receipt["status"] == "pass"
            and (result.embed_dir / "host-snippet.html").is_file()
            and (result.embed_dir / "parent-bridge.js").is_file()
            and (result.embed_dir / "allowed-origins.json").is_file()
            and (result.embed_dir / "csp-headers.json").is_file()
            and (result.embed_dir / "TEST-INSTRUCTIONS.md").is_file()
        )
        print(json.dumps(result.receipt, indent=2, sort_keys=True))
        print("RESULT:", "PASS" if ok else "FAIL")
        return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, help="Project run_dir containing deployment-receipt.json + embed-request.json")
    parser.add_argument("--out", type=Path, default=None, help="Target embed directory (default: <run-dir>/embed)")
    parser.add_argument("--project-slug", default=None, help="Override the sanitized project slug")
    parser.add_argument("--fixture", action="store_true", help="Populate --run-dir with the deterministic U18 fixture before building")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        ok = _self_test()
        return EXIT_OK if ok else EXIT_BUILD_FAILED

    if not args.run_dir:
        parser.error("--run-dir is required (or use --self-test)")
        return EXIT_USAGE

    if args.fixture:
        sys.path.insert(0, str(_FIXTURE_DIR))
        import make_embed_fixture as make_fixture  # noqa: E402

        make_fixture.write_fixture_run_dir(args.run_dir)

    try:
        result = build_embed_package(
            args.run_dir,
            embed_dir=args.out,
            project_slug_override=args.project_slug,
        )
    except EmbedBuildError as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        return EXIT_BUILD_FAILED

    print(json.dumps(result.receipt, indent=2, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
