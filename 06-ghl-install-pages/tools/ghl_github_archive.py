#!/usr/bin/env python3
"""ghl_github_archive.py — NON-BLOCKING GitHub archival for VERCEL_EMBED pages.

WHY THIS EXISTS
----------------
Operator standing rule: the source code behind ANY page this skill ships must
ALWAYS also live in a GitHub repo — never ONLY on a third-party host. The
VERCEL_EMBED path (``ghl_vercel.py``) previously violated that rule: it
base64-encoded the generated files and POSTed them straight to the Vercel
deployments API, with no GitHub step at all (see the retired "VERCEL_EMBED IS A
DIRECT API UPLOAD — NOT GitHub" line this unit removes from ``SKILL.md``).

This module closes that gap WITHOUT slowing the page down:

  1. The Vercel deploy (``ghl_vercel.deploy`` / ``make_public`` /
     ``assert_embeddable``) still runs first and still returns/completes on
     its own — the page goes live exactly as fast as before.
  2. ``stage_and_archive`` is called AFTER the Vercel pipeline succeeds. It:
       a. Copies the generated project files (``index.html``, ``vercel.json``,
          any assets) to a STABLE location under the run's evidence root
          (``<evidence_root>/vercel-github-archive/<marker>/src/``) — fast,
          local-disk-only, no network, negligible latency. This is what lets a
          later reconciliation pass retry the push even if the original
          (possibly ephemeral) ``project_dir`` is long gone.
       b. Writes a small ``task.json`` describing the archive job.
       c. Spawns a DETACHED subprocess (new session — survives the parent
          process exiting) that performs the actual GitHub API calls. The
          caller's call to ``stage_and_archive`` returns immediately; it does
          NOT wait for the subprocess. This mirrors the skill's existing
          "long runs fire detached; the agent resumes via the per-page
          ledger" doctrine (SKILL.md) — the same pattern, applied to archival.
  3. If ANYTHING in the archive path fails — no token, network error, GitHub
     API error, whatever — the page STAYS live. Nothing here can roll back or
     block the Vercel deploy. Failures are recorded as an honest F6-style
     receipt (``ghl_receipts``, object_type ``vercel_github_archive``) so a
     reconciliation sweep (``ghl_github_reconcile.py``) can find and retry (or
     flag) them later. "No receipt = not archived" — same discipline as every
     other Skill-6 object write.

REPO TARGETING — no client names, no cross-client collisions
--------------------------------------------------------------
The archive repo name is DERIVED deterministically from the caller-supplied
``project_name`` + ``marker`` (never a literal client name baked into this
file). The same (project_name, marker) pair always maps to the same repo, so
a re-deploy of the SAME page updates its OWN repo — it can never create a
second repo for the same page, and it never touches any OTHER repo. The repo
owner defaults to whoever the resolved GitHub token authenticates as
(``GET /user``); pass ``repo_owner=`` explicitly to target an org.

TOKEN SOURCE
------------
``GH_TOKEN`` -> ``GITHUB_TOKEN`` (same order as ``CREDENTIALS.md``'s "GitHub
Token" entry, Skill 10's setup output). If neither is set, archival is
recorded as a FAILED (not fatal) receipt with ``error`` explaining why — the
Vercel path is completely unaffected.

GLUE BOUNDARY
-------------
Like ``ghl_vercel.py``, this module performs real I/O (GitHub REST API +
local filesystem + subprocess spawn). Every network call is behind an
injectable ``requester``/``popen`` seam so tests run fully offline (mock-only,
same pattern as ``tests/test_ghl_vercel.py``) — no live GitHub call ever runs
in CI.

CLI (used internally by the detached subprocess; also runnable by hand)
-------------------------------------------------------------------------
    python3 ghl_github_archive.py --run-task <task.json>   # perform one archive job
    python3 ghl_github_archive.py --selftest                # no network, no subprocess
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_receipts  # noqa: E402  (F6 receipts store — reused, not reinvented)


# ── Constants ─────────────────────────────────────────────────────────────────

GITHUB_API_ORIGIN = "https://api.github.com"

# Same order CREDENTIALS.md documents for "GitHub Token" (Skill 10's output).
GITHUB_TOKEN_ENV_CANDIDATES = ("GH_TOKEN", "GITHUB_TOKEN")

HTTP_TIMEOUT_SECONDS = 30

# The F6 receipt object_type this module writes (reused ghl_receipts store).
ARCHIVE_RECEIPT_TYPE = "vercel_github_archive"
DEPLOY_RECEIPT_TYPE = "vercel_deploy"

# Directory (under a run's evidence root) where staged source + task files +
# the subprocess log live. Never under $TMPDIR — see ENV-MATRIX.md's
# adaptation contract item 4 (run evidence must survive a reboot / skill update).
ARCHIVE_SUBDIR = "vercel-github-archive"


# ── Errors ────────────────────────────────────────────────────────────────────

class GithubArchiveError(RuntimeError):
    """Raised internally by the archive worker. NEVER allowed to escape into
    the Vercel/GHL build path — every call site that can raise this is wrapped
    so the caller only ever sees a recorded receipt, never an exception."""


class GithubTokenError(GithubArchiveError):
    """No GH_TOKEN/GITHUB_TOKEN resolvable from the environment."""


# ── Token resolution ──────────────────────────────────────────────────────────

def resolve_github_token(env: dict | None = None) -> str:
    """Resolve the GitHub token from the environment (GH_TOKEN -> GITHUB_TOKEN).

    Raises ``GithubTokenError`` if neither is set. Callers in the non-blocking
    path MUST catch this and record it as a failed (not raised) receipt.
    """
    env = env if env is not None else os.environ
    for name in GITHUB_TOKEN_ENV_CANDIDATES:
        val = (env.get(name) or "").strip()
        if val:
            return val
    raise GithubTokenError(
        "No GitHub token found. Set one of: "
        + ", ".join(GITHUB_TOKEN_ENV_CANDIDATES)
        + " (CREDENTIALS.md 'GitHub Token' — Skill 10's own setup output)."
    )


# ── Naming ────────────────────────────────────────────────────────────────────

def slugify(value: str, *, max_len: int = 40) -> str:
    """Lowercase, alnum + hyphen only, collapsed, trimmed. Deterministic and
    collision-resistant enough for a repo-name component (paired with a marker
    suffix by ``default_repo_name``)."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return (value or "page")[:max_len]


def default_repo_name(project_name: str, marker: str) -> str:
    """Deterministic repo name for one page: same (project_name, marker) pair
    ALWAYS resolves to the SAME repo name, so a re-deploy updates its own repo
    and never creates a second one / collides with an unrelated repo."""
    return f"zhc-page-{slugify(project_name)}-{slugify(marker, max_len=16)}"


# ── Staging (local disk only — no network, negligible latency) ───────────────

def _archive_root(evidence_root: str, marker: str) -> str:
    safe_marker = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in marker)[:80]
    return os.path.join(evidence_root, ARCHIVE_SUBDIR, safe_marker)


def stage_source(project_dir: str, evidence_root: str, marker: str) -> str:
    """Copy every file in ``project_dir`` to a STABLE path under the evidence
    root so a later reconciliation retry never depends on the (possibly
    ephemeral / tmp) ``project_dir`` still existing. Pure local file I/O.

    Returns the staged source directory path.
    """
    root = _archive_root(evidence_root, marker)
    src_dir = os.path.join(root, "src")
    os.makedirs(src_dir, exist_ok=True)
    for fn in sorted(os.listdir(project_dir)):
        if fn.startswith("."):
            continue
        s = os.path.join(project_dir, fn)
        if os.path.isfile(s):
            shutil.copy2(s, os.path.join(src_dir, fn))
    return src_dir


def write_task_file(evidence_root: str, marker: str, task: dict) -> str:
    """Atomic write of the archive task descriptor (write-then-rename, same
    durability discipline as ``ghl_receipts.write_receipt``)."""
    root = _archive_root(evidence_root, marker)
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, "task.json")
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(task, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, path)
    return path


def read_task_file(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ── GitHub REST helpers (real I/O — injectable ``requester`` for tests) ──────

def _http_request(method: str, url: str, body: dict | None, *, token: str) -> tuple[int, dict]:
    """Real HTTP call to api.github.com. Returns (status, parsed_json_or_raw).
    NOT called in tests — a ``requester`` callable is injected instead (same
    seam style as ``ghl_vercel._http_request``)."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ZHC-Skill6-GithubArchive/1.0",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, (json.loads(raw) if raw else {})
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"_raw": raw}
    except urllib.error.URLError as exc:
        raise GithubArchiveError(f"URL error calling {url}: {exc.reason}") from exc


Requester = Callable[[str, str, Optional[dict], str], tuple]


def resolve_authenticated_owner(token: str, *, requester: Requester | None = None) -> str:
    """GET /user -> login. Used as the default repo owner when the caller
    does not pass ``repo_owner`` explicitly."""
    _req = requester if requester is not None else _http_request
    status, resp = _req("GET", f"{GITHUB_API_ORIGIN}/user", None, token)
    if status != 200 or not isinstance(resp, dict) or not resp.get("login"):
        raise GithubArchiveError(f"GET /user failed (status={status}): {resp}")
    return resp["login"]


def ensure_repo(owner: str, name: str, token: str, *,
                 private: bool = True,
                 description: str = "",
                 requester: Requester | None = None) -> tuple[dict, bool]:
    """Ensure repo ``owner/name`` exists. Returns ``(repo_json, created)``.

    NEVER deletes or force-overwrites anything — a 200 on GET means the repo
    already exists and is reused as-is (idempotent); only a 404 triggers a
    create. This function only ever creates/uses the ONE deterministically
    named repo for this page (see ``default_repo_name``) — it can never touch
    an unrelated repo.
    """
    _req = requester if requester is not None else _http_request
    status, resp = _req("GET", f"{GITHUB_API_ORIGIN}/repos/{owner}/{name}", None, token)
    if status == 200:
        return resp, False
    if status != 404:
        raise GithubArchiveError(f"GET /repos/{owner}/{name} failed (status={status}): {resp}")

    # 404 -> create under the authenticated user. (Org targets are out of
    # scope for v1 — repo_owner is expected to be the token's own account;
    # see module docstring.)
    status, resp = _req(
        "POST", f"{GITHUB_API_ORIGIN}/user/repos",
        {"name": name, "private": private, "description": description,
         "auto_init": False},
        token,
    )
    if status not in (200, 201):
        raise GithubArchiveError(f"POST /user/repos ({name}) failed (status={status}): {resp}")
    return resp, True


def put_file(owner: str, repo: str, path: str, content_bytes: bytes, message: str,
             token: str, *, branch: str = "main",
             requester: Requester | None = None) -> dict:
    """Create-or-update one file via the GitHub Contents API (idempotent:
    reads the existing sha first so an update never collides)."""
    _req = requester if requester is not None else _http_request
    contents_url = f"{GITHUB_API_ORIGIN}/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}"

    sha = None
    status, resp = _req("GET", f"{contents_url}?ref={urllib.parse.quote(branch)}", None, token)
    if status == 200 and isinstance(resp, dict):
        sha = resp.get("sha")
    elif status not in (404,):
        raise GithubArchiveError(f"GET contents/{path} failed (status={status}): {resp}")

    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    status, resp = _req("PUT", contents_url, body, token)
    if status not in (200, 201):
        raise GithubArchiveError(f"PUT contents/{path} failed (status={status}): {resp}")
    return resp


def archive_files(owner: str, repo: str, src_dir: str, *, marker: str,
                   deployment_url: str, token: str,
                   requester: Requester | None = None) -> dict:
    """Push every file in ``src_dir`` to ``owner/repo`` plus an
    ``ARCHIVE-MANIFEST.json`` recording the marker + deployment url + time —
    the receipt that proves THIS repo content corresponds to THIS deployment.
    """
    pushed: list[str] = []
    for fn in sorted(os.listdir(src_dir)):
        p = os.path.join(src_dir, fn)
        if not os.path.isfile(p):
            continue
        with open(p, "rb") as fh:
            raw = fh.read()
        put_file(owner, repo, fn, raw,
                 f"Archive VERCEL_EMBED source ({fn}) — marker {marker}",
                 token, requester=requester)
        pushed.append(fn)

    manifest = {
        "marker": marker,
        "deployment_url": deployment_url,
        "archived_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": pushed,
    }
    put_file(owner, repo, "ARCHIVE-MANIFEST.json",
             json.dumps(manifest, indent=2).encode("utf-8"),
             f"Update archive manifest — marker {marker}",
             token, requester=requester)

    return {"repo": f"{owner}/{repo}", "files": pushed + ["ARCHIVE-MANIFEST.json"]}


# ── The one archive job (used by the detached subprocess AND reconcile retry) ─

def run_archive_task(task: dict, *, requester: Requester | None = None,
                      env: dict | None = None) -> dict:
    """Perform ONE archive job end to end and write its F6 receipt. NEVER
    raises past this function — every failure path returns/records a
    ``failed`` receipt instead. Safe to call either from the detached
    subprocess's ``--run-task`` entrypoint or synchronously from a
    reconciliation retry.

    ``task`` fields: marker, src_dir, evidence_root, deployment_url,
    project_name, repo_owner (optional).
    """
    marker = task["marker"]
    evidence_root = task["evidence_root"]
    src_dir = task["src_dir"]
    deployment_url = task.get("deployment_url", "")
    project_name = task.get("project_name", "zhc-ghl-page")
    forced_owner = task.get("repo_owner") or None
    repo_name = task.get("repo_name") or default_repo_name(project_name, marker)

    try:
        token = resolve_github_token(env)
        owner = forced_owner or resolve_authenticated_owner(token, requester=requester)
        repo_json, created = ensure_repo(
            owner, repo_name, token,
            description=f"Archived source for VERCEL_EMBED page (marker {marker})",
            requester=requester,
        )
        result = archive_files(owner, repo_name, src_dir, marker=marker,
                                deployment_url=deployment_url, token=token,
                                requester=requester)
        receipt = ghl_receipts.make_receipt(
            ARCHIVE_RECEIPT_TYPE, marker,
            "created" if created else "reused",
            response_id=repo_json.get("full_name", f"{owner}/{repo_name}"),
            request_shape={"repo": f"{owner}/{repo_name}", "files": result["files"]},
            verify={"ok": True, "repo_url": repo_json.get("html_url"),
                    "files": result["files"]},
            disclosures=[repo_json.get("html_url", "")],
        )
    except Exception as exc:  # noqa: BLE001 — fail-soft is the whole point
        receipt = ghl_receipts.make_receipt(
            ARCHIVE_RECEIPT_TYPE, marker, "failed",
            request_shape={"repo_name": repo_name, "project_name": project_name},
            error=str(exc),
        )

    path = ghl_receipts.write_receipt(evidence_root, receipt)
    return {"receipt_path": path, "receipt": receipt}


# ── Non-blocking entry point (called from ghl_vercel.run_pipeline) ───────────

Popen = Callable[..., Any]


def archive_async(project, deployment, marker: str, evidence_root: str, *,
                   project_name: str = "zhc-ghl-page",
                   repo_owner: str | None = None,
                   repo_name: str | None = None,
                   env: dict | None = None,
                   python_executable: str | None = None,
                   popen: Popen | None = None) -> dict:
    """Stage the generated page's source + fire a DETACHED subprocess to push
    it to GitHub. Returns immediately — never waits on the subprocess, never
    raises. This is the ONLY function ``ghl_vercel.run_pipeline`` calls.

    Returns a status dict:
      {"status": "spawned", ...}   — staging done, subprocess launched
      {"status": "skipped", "reason": ...}  — no evidence_root (nothing to do)
    A missing GitHub token is NOT treated as "skipped": it still gets an
    honest ``failed`` F6 receipt (written synchronously here) so it is
    visible to reconciliation ("no receipt = not archived" must never apply
    to "we didn't even try because there's no token" — that's a config gap,
    not a build event, and it should show up as a flag).
    """
    if not evidence_root:
        return {"status": "skipped", "reason": "no evidence_root supplied"}

    env = env if env is not None else os.environ

    # Cheap, synchronous, no-network pre-check: if there is plainly no token,
    # record the honest failure now instead of spawning a subprocess that
    # would immediately fail anyway.
    try:
        resolve_github_token(env)
    except GithubTokenError as exc:
        receipt = ghl_receipts.make_receipt(
            ARCHIVE_RECEIPT_TYPE, marker, "failed",
            request_shape={"project_name": project_name},
            error=str(exc),
        )
        ghl_receipts.write_receipt(evidence_root, receipt)
        return {"status": "failed", "reason": str(exc)}

    try:
        src_dir = stage_source(project.project_dir, evidence_root, marker)
        task = {
            "marker": marker,
            "src_dir": src_dir,
            "evidence_root": evidence_root,
            "deployment_url": getattr(deployment, "url", ""),
            "project_name": project_name,
            "repo_owner": repo_owner,
            "repo_name": repo_name,
        }
        task_path = write_task_file(evidence_root, marker, task)
    except Exception as exc:  # noqa: BLE001 — staging must never block/raise outward
        receipt = ghl_receipts.make_receipt(
            ARCHIVE_RECEIPT_TYPE, marker, "failed",
            request_shape={"project_name": project_name},
            error=f"staging failed: {exc}",
        )
        ghl_receipts.write_receipt(evidence_root, receipt)
        return {"status": "failed", "reason": f"staging failed: {exc}"}

    root = _archive_root(evidence_root, marker)
    log_path = os.path.join(root, "archive.log")
    py = python_executable or sys.executable
    cmd = [py, os.path.abspath(__file__), "--run-task", task_path]

    _popen = popen if popen is not None else _real_popen
    try:
        _popen(cmd, log_path)
    except Exception as exc:  # noqa: BLE001 — spawn failure must not block either
        receipt = ghl_receipts.make_receipt(
            ARCHIVE_RECEIPT_TYPE, marker, "failed",
            request_shape={"project_name": project_name},
            error=f"failed to spawn detached archive subprocess: {exc}",
        )
        ghl_receipts.write_receipt(evidence_root, receipt)
        return {"status": "failed", "reason": f"spawn failed: {exc}"}

    return {"status": "spawned", "task_path": task_path, "log_path": log_path}


def _real_popen(cmd: list[str], log_path: str) -> None:
    """Spawn ``cmd`` fully detached: new session (so it survives the parent
    exiting / is not in the parent's process group), stdout/stderr to a log
    file (so a failure is debuggable without blocking anything), stdin
    closed. Never waited-on by the caller."""
    import subprocess
    log_fh = open(log_path, "ab")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_fh,
        "stderr": log_fh,
        "close_fds": True,
    }
    if hasattr(os, "setsid"):
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _selftest() -> int:
    """No network, no subprocess, no live GitHub. Exercises: slugify/
    default_repo_name determinism, stage_source, run_archive_task with an
    injected requester (success + failure paths), and archive_async's
    skip/no-token/spawn seams via an injected popen."""
    import tempfile

    errors: list[str] = []

    # 1. default_repo_name is deterministic and collision-safe across markers.
    n1 = default_repo_name("zhc-acme-landing", "MARKER-1")
    n2 = default_repo_name("zhc-acme-landing", "MARKER-1")
    n3 = default_repo_name("zhc-acme-landing", "MARKER-2")
    if n1 != n2:
        errors.append("default_repo_name not deterministic")
    if n1 == n3:
        errors.append("default_repo_name must differ across markers")

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = os.path.join(tmp, "proj")
        os.makedirs(project_dir)
        with open(os.path.join(project_dir, "index.html"), "w") as fh:
            fh.write("<html>hi SELFTEST-MARKER</html>")
        with open(os.path.join(project_dir, "vercel.json"), "w") as fh:
            fh.write("{}")

        evidence_root = os.path.join(tmp, "evidence")

        # 2. stage_source copies files to a stable path.
        src_dir = stage_source(project_dir, evidence_root, "SELFTEST-MARKER")
        if not os.path.isfile(os.path.join(src_dir, "index.html")):
            errors.append("stage_source did not copy index.html")

        # 3. run_archive_task — success path (mock requester, repo does not exist).
        calls: list[tuple] = []

        def fake_requester_create(method, url, body, token):
            calls.append((method, url))
            if method == "GET" and url.endswith("/user"):
                return 200, {"login": "fake-owner"}
            if method == "GET" and "/repos/" in url and "/contents/" not in url:
                return 404, {"message": "Not Found"}
            if method == "POST" and url.endswith("/user/repos"):
                return 201, {"full_name": "fake-owner/zhc-page-x",
                              "html_url": "https://github.com/fake-owner/zhc-page-x"}
            if method == "GET" and "/contents/" in url:
                return 404, {"message": "Not Found"}
            if method == "PUT" and "/contents/" in url:
                return 201, {"content": {"sha": "abc123"}}
            raise AssertionError(f"unexpected call: {method} {url}")

        task = {
            "marker": "SELFTEST-MARKER",
            "src_dir": src_dir,
            "evidence_root": evidence_root,
            "deployment_url": "https://example.vercel.app",
            "project_name": "zhc-acme-landing",
        }
        result = run_archive_task(task, requester=fake_requester_create,
                                   env={"GH_TOKEN": "fake-token-value"})
        if result["receipt"]["action"] not in ("created", "reused"):
            errors.append(f"run_archive_task success path did not record created/reused: {result}")
        if not result["receipt"]["verify"].get("ok"):
            errors.append("success receipt should have verify.ok True")

        # 4. reduce_receipts sees it.
        summ = ghl_receipts.reduce_receipts(evidence_root)
        if "vercel_github_archive:SELFTEST-MARKER" not in summ["created"] and \
           "vercel_github_archive:SELFTEST-MARKER" not in summ["reused"]:
            errors.append(f"archive receipt not visible via reduce_receipts: {summ}")

        # 5. run_archive_task — failure path (requester raises).
        def fake_requester_fail(method, url, body, token):
            raise RuntimeError("simulated network failure")

        task2 = dict(task, marker="SELFTEST-MARKER-FAIL")
        result2 = run_archive_task(task2, requester=fake_requester_fail,
                                    env={"GH_TOKEN": "fake-token-value"})
        if result2["receipt"]["action"] != "failed":
            errors.append(f"run_archive_task failure path should record 'failed': {result2}")
        if not result2["receipt"]["error"]:
            errors.append("failed receipt must carry an error message")

        # 6. archive_async — no evidence_root => skipped, no exception.
        import types
        fake_project = types.SimpleNamespace(project_dir=project_dir)
        fake_deployment = types.SimpleNamespace(url="https://example.vercel.app")

        r_skip = archive_async(fake_project, fake_deployment, "M-SKIP", "", env={"GH_TOKEN": "x"})
        if r_skip["status"] != "skipped":
            errors.append(f"archive_async with no evidence_root should skip: {r_skip}")

        # 7. archive_async — no token => recorded as failed receipt, no exception.
        evidence_root_2 = os.path.join(tmp, "evidence2")
        r_notoken = archive_async(fake_project, fake_deployment, "M-NOTOKEN", evidence_root_2, env={})
        if r_notoken["status"] != "failed":
            errors.append(f"archive_async with no token should report failed (not raise): {r_notoken}")
        summ2 = ghl_receipts.reduce_receipts(evidence_root_2)
        if "vercel_github_archive:M-NOTOKEN" not in summ2["failed"]:
            errors.append("missing-token attempt must still leave an honest failed receipt")

        # 8. archive_async — happy path spawns via injected popen (no real subprocess).
        spawned: list[list[str]] = []

        def fake_popen(cmd, log_path):
            spawned.append(cmd)

        evidence_root_3 = os.path.join(tmp, "evidence3")
        r_spawn = archive_async(fake_project, fake_deployment, "M-SPAWN", evidence_root_3,
                                 env={"GH_TOKEN": "x"}, popen=fake_popen)
        if r_spawn["status"] != "spawned":
            errors.append(f"archive_async happy path should report spawned: {r_spawn}")
        if not spawned:
            errors.append("archive_async did not call the injected popen")
        if spawned and "--run-task" not in spawned[0]:
            errors.append(f"spawned command missing --run-task: {spawned[0] if spawned else None}")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_github_archive verified (no network, no real subprocess)")
    return 0


def main(argv: Optional[list] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="ghl_github_archive",
        description="Non-blocking GitHub archival for Skill 06 VERCEL_EMBED pages.",
    )
    p.add_argument("--run-task", metavar="TASK_JSON",
                   help="Perform one archive job described by TASK_JSON and write its receipt.")
    p.add_argument("--selftest", action="store_true",
                   help="Run the no-network, no-subprocess self-test and exit.")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.run_task:
        task = read_task_file(args.run_task)
        result = run_archive_task(task)
        print(json.dumps(result["receipt"], indent=2))
        return 0 if result["receipt"]["action"] != "failed" else 1
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
