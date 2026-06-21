#!/usr/bin/env python3
"""ghl_builder.py — Engine-agnostic orchestration helpers for the GoHighLevel
browser-driven Funnel / Website / Page builder (Skill 06 overhaul).

THIS IS THE GLUE, NOT THE CLICKER. The actual UI navigation is performed by the
AGENT at runtime using agent-browser (PRIMARY) or Playwright (FALLBACK), driven
by live snapshots and the gate registry (gates.json, D8). This module owns the
deterministic, mechanical parts so they are never improvised:

  * the page MANIFEST (A0.4) — the ordered build plan + resume key
  * the per-page LEDGER (D10/D12) — /tmp/<run-id>/<funnel>/<step>.json
  * the ZHC naming prefix enforcement (guardrail 2)
  * the hard sub-account match gate helper (A2.3)
  * the runtime-gate contract loader (gates.json) — captured vs runtime
  * the "never publish without approval" guard (A13.1)
  * marker-string verification of a fetched URL (A12.2 / A13.3 / C3)

It runs on Haiku-class mechanical work (ledger writes, manifest assembly, file
reads, URL/string verification) — NEVER the live UI loop. agent-browser/
Playwright commands are emitted as plans for the agent to execute; this module
does not itself drive the browser (keeps it testable + side-effect-free except
the ledger files it owns).

Ledger states (furthest-reached per page): created | code-saved | page-saved |
previewed | published | FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

LEDGER_STATES = ["created", "code-saved", "page-saved", "previewed", "published"]
ZHC_PREFIX_RE = re.compile(r"^\s*zhc\b", re.IGNORECASE)


# ── ZHC naming (guardrail 2 — carries standing build approval per Skill 44) ──

def ensure_zhc_prefix(name: str) -> str:
    """Return `name` guaranteed to start with the `zhc` provenance prefix.
    The prefix is MANDATORY on every funnel / website / step the builder
    creates — it carries the standing build approval recorded in Skill 44's
    safety_gate. Refuses to silently drop it."""
    name = (name or "").strip()
    if not name:
        return "zhc untitled"
    if ZHC_PREFIX_RE.match(name):
        return name
    return f"zhc {name}"


# ── Manifest (A0.4) ──────────────────────────────────────────────────────────

def build_manifest(funnel_name: str, surface: str, pages: list[dict]) -> dict:
    """Assemble the build manifest. `surface` is 'funnel' or 'website'.
    Each page: {name, path, payload_path, mode}. mode in {direct, iframe}.
    Validates payloads exist and are non-empty (A0.2)."""
    if surface not in ("funnel", "website"):
        raise ValueError("surface must be 'funnel' or 'website'")
    out_pages = []
    for i, p in enumerate(pages, 1):
        path = (p.get("path") or "").strip().lower()
        path = re.sub(r"[^a-z0-9-]+", "-", path).strip("-") or f"step-{i}"
        mode = p.get("mode", "direct")
        if mode not in ("direct", "iframe"):
            raise ValueError(f"page {i}: mode must be direct|iframe")
        payload_path = p.get("payload_path", "")
        if mode == "direct":
            if not payload_path or not os.path.isfile(payload_path):
                raise ValueError(f"page {i} ({p.get('name')}): payload_path missing/not a file: {payload_path}")
            if os.path.getsize(payload_path) == 0:
                raise ValueError(f"page {i} ({p.get('name')}): payload is empty")
        out_pages.append({
            "order": i,
            "name": p.get("name") or f"Step {i}",
            "path": path,
            "payload_path": payload_path,
            "mode": mode,
            "iframe_src": p.get("iframe_src", ""),
        })
    return {
        "funnel_name": ensure_zhc_prefix(funnel_name),
        "surface": surface,
        "pages": out_pages,
        "created_at": int(time.time()),
    }


# ── Ledger (D10 / D12 resume) ─────────────────────────────────────────────────

def _ledger_path(run_id: str, funnel: str, step: str) -> str:
    safe_funnel = re.sub(r"[^A-Za-z0-9_-]+", "_", funnel)
    safe_step = re.sub(r"[^A-Za-z0-9_-]+", "_", step)
    return os.path.join("/tmp", run_id, safe_funnel, f"{safe_step}.json")


def ledger_write(run_id: str, funnel: str, step: str, state: str, extra: dict | None = None) -> str:
    """Record a page's furthest-reached state. Idempotent: only advances; never
    rewinds a page that already reached a later state (unless state==FAILED)."""
    if state != "FAILED" and state not in LEDGER_STATES:
        raise ValueError(f"unknown ledger state: {state}")
    path = _ledger_path(run_id, funnel, step)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prev = {}
    if os.path.isfile(path):
        try:
            prev = json.load(open(path))
        except Exception:
            prev = {}
    prev_state = prev.get("state")
    # Do not rewind a good state with an earlier good state.
    if prev_state in LEDGER_STATES and state in LEDGER_STATES \
            and LEDGER_STATES.index(state) < LEDGER_STATES.index(prev_state):
        state = prev_state
    rec = {"funnel": funnel, "step": step, "state": state,
           "updated_at": int(time.time()), **(extra or {})}
    if prev:
        rec = {**prev, **rec}
    with open(path, "w") as f:
        json.dump(rec, f, indent=2)
    return path


def ledger_read(run_id: str, funnel: str, step: str) -> dict:
    path = _ledger_path(run_id, funnel, step)
    if not os.path.isfile(path):
        return {"state": None}
    try:
        return json.load(open(path))
    except Exception:
        return {"state": None}


def resume_point(run_id: str, manifest: dict) -> list[dict]:
    """Return, per page, the next ledger state to attempt — the resume plan
    (D12). A page already at `published` is done; one at `previewed` resumes at
    publish-if-approved; a FAILED page resumes from its recorded last-good.
    NEVER re-create a step that already exists (state >= created)."""
    plan = []
    funnel = manifest["funnel_name"]
    for pg in manifest["pages"]:
        led = ledger_read(run_id, funnel, pg["name"])
        st = led.get("state")
        if st == "published":
            nxt = "DONE"
        elif st in LEDGER_STATES:
            idx = LEDGER_STATES.index(st)
            nxt = LEDGER_STATES[idx + 1] if idx + 1 < len(LEDGER_STATES) else "DONE"
        elif st == "FAILED":
            nxt = led.get("last_good", "created")
        else:
            nxt = "created"
        plan.append({
            "name": pg["name"], "path": pg["path"], "mode": pg["mode"],
            "current_state": st, "resume_at": nxt,
            "skip_create": st is not None and st != "FAILED",
        })
    return plan


# ── Sub-account hard gate (A2.3) ──────────────────────────────────────────────

def subaccount_matches(current_label: str, target: str) -> bool:
    """Case-insensitive contains. Caller MUST refuse to proceed on False
    (NO-COMINGLING — never default to another client's sub-account)."""
    if not current_label or not target:
        return False
    return target.strip().lower() in current_label.strip().lower()


# ── Publish guard (A13.1 / guardrail 4) ───────────────────────────────────────

def may_publish(approval: str | None) -> bool:
    """Return True ONLY on an explicit affirmative LIVE answer. Default = draft.
    Any absent/ambiguous/negative answer => False."""
    if not approval:
        return False
    a = approval.strip().lower()
    return a in ("live", "publish", "yes", "approved", "go", "go ahead", "true")


# ── Marker-string verification (A12.2 / A13.3 / C3) ───────────────────────────

def verify_url(url: str, marker: str, timeout: int = 20) -> dict:
    """Fetch `url`; pass iff HTTP 200 AND `marker` appears in the body. Used for
    preview/published/embed verification — never report a page 'good' on
    no-error alone (edge #15)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ghl-builder-verify/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.getcode()
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "marker_found": False, "url": url}
    except Exception as e:
        return {"ok": False, "http": None, "marker_found": False, "url": url, "error": str(e)}
    found = bool(marker) and marker in body
    return {"ok": code == 200 and found, "http": code, "marker_found": found, "url": url}


# ── Gate registry loader (D8 contract) ────────────────────────────────────────

def load_gates(gates_path: str | None = None) -> dict:
    gates_path = gates_path or os.path.join(os.path.dirname(__file__), "gates.json")
    return json.load(open(gates_path))


def runtime_gates(gates_path: str | None = None) -> list[dict]:
    """Return only the gates that MUST be captured at runtime (status=runtime).
    These are the snapshot-gates — the agent snapshots the live DOM and picks
    the @ref. NO invented CSS is ever shipped as fact for these."""
    g = load_gates(gates_path)
    return [x for x in g["gates"] if x.get("status") == "runtime"]


def captured_gates(gates_path: str | None = None) -> list[dict]:
    g = load_gates(gates_path)
    return [x for x in g["gates"] if x.get("status") == "captured"]


# ── CLI (mechanical helpers the agent shells out to) ─────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="GoHighLevel builder mechanical helpers")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("zhc"); p.add_argument("name")
    p = sub.add_parser("verify"); p.add_argument("url"); p.add_argument("marker")
    p = sub.add_parser("ledger-write")
    for a in ("run_id", "funnel", "step", "state"):
        p.add_argument(a)
    p.add_argument("--last-good", default=None)
    p = sub.add_parser("resume"); p.add_argument("run_id"); p.add_argument("manifest_path")
    p = sub.add_parser("gates"); p.add_argument("--runtime", action="store_true"); p.add_argument("--captured", action="store_true")
    p = sub.add_parser("may-publish"); p.add_argument("approval", nargs="?", default="")
    p = sub.add_parser("subaccount"); p.add_argument("current"); p.add_argument("target")

    args = ap.parse_args()

    if args.cmd == "zhc":
        print(ensure_zhc_prefix(args.name)); return 0
    if args.cmd == "verify":
        res = verify_url(args.url, args.marker)
        print(json.dumps(res)); return 0 if res["ok"] else 1
    if args.cmd == "ledger-write":
        extra = {"last_good": args.last_good} if args.last_good else None
        print(ledger_write(args.run_id, args.funnel, args.step, args.state, extra)); return 0
    if args.cmd == "resume":
        manifest = json.load(open(args.manifest_path))
        print(json.dumps(resume_point(args.run_id, manifest), indent=2)); return 0
    if args.cmd == "gates":
        if args.runtime: print(json.dumps(runtime_gates(), indent=2))
        elif args.captured: print(json.dumps(captured_gates(), indent=2))
        else: print(json.dumps(load_gates(), indent=2))
        return 0
    if args.cmd == "may-publish":
        ok = may_publish(args.approval); print("PUBLISH" if ok else "DRAFT"); return 0 if ok else 1
    if args.cmd == "subaccount":
        ok = subaccount_matches(args.current, args.target)
        print("MATCH" if ok else "MISMATCH"); return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
