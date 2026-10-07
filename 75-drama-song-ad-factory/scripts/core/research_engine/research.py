"""research.py: research stage runner producing research/brief outputs.

Directive 21 (research/market.md, audience.md, competitors.md, evidence.json),
17.9 (factual claims link to evidence), 11.1/11.2 (specific sub-avatar),
24.4 (stable JSON envelope + exit codes). Stdlib only.

Input brief: {"offer", "audience", "action"/"cta", "claims": [...],
  "sources": [...]}. Every claim needs a citation URL + retrieval date or it
lands UNAVAILABLE in evidence.json. Claims without source never pass.
Sub-avatar brief is JSON: avatar, emotional_wound, desired_transformation.
Outputs render to a run dir: research/{market,audience,competitors}.md +
evidence.json, brief/sub_avatar.json.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

SCHEMA_VERSION = "blackceo.research/v1"
TOOL_VERSION = "1.0.0"
EXIT = {"ok": 0, "waiting": 2, "parked": 3, "rejected": 4, "error": 1}

RESEARCH_FILES = ("market.md", "audience.md", "competitors.md", "evidence.json")

# ponytail: field set fixed by contract; extend only on directive change.


class ResearchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _today():
    return datetime.date.today().isoformat()


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def validate_sources(sources):
    """Sources: [{id?, url, retrieved}]. URL required, retrieved defaults today."""
    errors, seen, norm = [], set(), []
    if not isinstance(sources, list) or not sources:
        raise ResearchError("SOURCES_MISSING", "sources must be a non-empty list")
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            errors.append("source %d: not an object" % i)
            continue
        url = s.get("url")
        if not _nonempty(url):
            errors.append("source %d: url required" % i)
            continue
        url = url.strip()
        if url in seen:
            errors.append("source %d: duplicate url %r" % (i, url))
            continue
        seen.add(url)
        rec = {"id": s.get("id") if _nonempty(s.get("id")) else "src-%d" % (i + 1),
               "url": url, "retrieved": s.get("retrieved") or _today()}
        norm.append(rec)
    return norm, errors


def validate_claims(claims, source_ids):
    """Claims: [{id?, text, source}]. Every claim carries a source id or
    it goes UNAVAILABLE in evidence.json."""
    if not isinstance(claims, list) or not claims:
        raise ResearchError("CLAIMS_MISSING", "claims must be a non-empty list")
    ok, unavailable, seen = [], [], set()
    for i, c in enumerate(claims):
        cid = c.get("id") if isinstance(c, dict) and _nonempty(c.get("id")) else "claim-%d" % (i + 1)
        if cid in seen:
            unavailable.append({"id": cid, "text": c.get("text") if isinstance(c, dict) else None,
                                "status": "UNAVAILABLE", "reason": "duplicate-claim-id"})
            continue
        seen.add(cid)
        text = c.get("text") if isinstance(c, dict) else None
        src = c.get("source") if isinstance(c, dict) else None
        if not _nonempty(text):
            unavailable.append({"id": cid, "text": text, "status": "UNAVAILABLE",
                                "reason": "claim-text-missing"})
        elif not _nonempty(src) or src.strip() not in source_ids:
            unavailable.append({"id": cid, "text": text.strip() if _nonempty(text) else text,
                                "status": "UNAVAILABLE", "reason": "claim-without-source"})
        else:
            ok.append({"id": cid, "text": text.strip(), "source": src.strip(), "status": "PASS"})
    return ok, unavailable


def validate_sub_avatar(sub):
    """Sub-avatar brief: avatar + emotional_wound + desired_transformation."""
    errors = []
    if not isinstance(sub, dict):
        return ["sub_avatar must be an object"]
    for f in ("avatar", "emotional_wound", "desired_transformation"):
        if not _nonempty(sub.get(f)):
            errors.append("sub_avatar.%s required (non-empty)" % f)
    allowed = {"avatar", "emotional_wound", "desired_transformation", "notes"}
    for k in sub:
        if k not in allowed:
            errors.append("sub_avatar.%s unknown field" % k)
    return errors


def evaluate(brief, today=None):
    """Validate brief, classify claims, gate sub-avatar completeness.

    Returns outcome/reason_code/evidence bundle. No filesystem writes.
    """
    brief = brief or {}
    errors = []
    for f in ("offer", "audience"):
        if not _nonempty(brief.get(f)):
            errors.append("%s required (non-empty)" % f)
    if not _nonempty(brief.get("action")) and not _nonempty(brief.get("cta")):
        errors.append("action/cta required (non-empty)")
    if errors:
        return {"outcome": "waiting", "reason_code": "missing-essentials",
                "errors": errors, "next_action": "Supply offer, audience, action/cta."}
    try:
        sources, src_errors = validate_sources(brief.get("sources"))
    except ResearchError as e:
        return {"outcome": "rejected", "reason_code": e.code, "errors": [str(e)],
                "next_action": "Supply at least one source with url."}
    try:
        passed, unavailable = validate_claims(brief.get("claims"), {s["id"] for s in sources})
    except ResearchError as e:
        return {"outcome": "rejected", "reason_code": e.code, "errors": [str(e)],
                "next_action": "Supply at least one claim."}
    sub_errors = validate_sub_avatar(brief.get("sub_avatar"))
    evidence = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
                "claims": passed + unavailable,
                "unavailable": [c["id"] for c in unavailable],
                "sources": sources, "generated": today or _today()}
    if src_errors:
        return {"outcome": "rejected", "reason_code": "source-invalid",
                "errors": src_errors, "evidence": evidence,
                "next_action": "Fix the listed source errors and re-run."}
    if sub_errors:
        return {"outcome": "rejected", "reason_code": "sub-avatar-incomplete",
                "errors": sub_errors, "evidence": evidence,
                "next_action": "Complete the sub-avatar brief (avatar, emotional_wound, desired_transformation)."}
    if unavailable:
        return {"outcome": "parked", "reason_code": "claims-without-source",
                "errors": ["%s: %s" % (c["id"], c["reason"]) for c in unavailable],
                "evidence": evidence,
                "next_action": "Cite a source for each listed claim or drop it."}
    return {"outcome": "ok", "reason_code": "research-complete", "errors": [],
            "evidence": evidence, "next_action": "Render outputs, then proceed to creative."}


def _md(title, offer, lines):
    body = ["# %s" % title, "", "Offer: %s" % offer.strip(), ""]
    body += ["- %s" % l for l in lines] if lines else ["- TBD (no claims filed under this heading)."]
    return "\n".join(body) + "\n"


def render(brief, evidence, outdir):
    """Write research/{market,audience,competitors}.md + evidence.json and
    brief/sub_avatar.json. Returns written paths."""
    out = Path(outdir)
    (out / "research").mkdir(parents=True, exist_ok=True)
    (out / "brief").mkdir(parents=True, exist_ok=True)
    offer = brief.get("offer", "").strip()
    by_src = {s["id"]: s for s in evidence["sources"]}
    claim_lines = ["%s [%s](%s) (retrieved %s)" % (
        c["text"], c.get("source", "?"),
        by_src.get(c.get("source"), {}).get("url", "?"),
        by_src.get(c.get("source"), {}).get("retrieved", "?"))
        for c in evidence["claims"]]
    aud = [brief.get("audience", "").strip(), "CTA: %s" % (
        brief.get("action") or brief.get("cta") or "").strip()]
    comp = ["Competitor scan filed against %d source(s)." % len(evidence["sources"])]
    files = {"research/market.md": _md("Market", offer, claim_lines),
             "research/audience.md": _md("Audience", offer, aud),
             "research/competitors.md": _md("Competitors", offer, comp),
             "research/evidence.json": json.dumps(evidence, indent=2, sort_keys=True) + "\n",
             "brief/sub_avatar.json": json.dumps(
                 {"schema_version": SCHEMA_VERSION, **brief.get("sub_avatar", {})},
                 indent=2, sort_keys=True) + "\n"}
    written = []
    for rel, text in files.items():
        (out / rel).write_text(text, encoding="utf-8")
        written.append(rel)
    manifest = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
                "files": written,
                "digest": _sha("".join(files[r] for r in sorted(files)))}
    (out / "research" / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written


def envelope(command, run_id, outcome, reason_code, next_action,
             data=None, evidence_refs=None, state_version=None):
    return {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
            "command": command, "run_id": run_id, "outcome": outcome,
            "reason_code": reason_code, "next_action": next_action,
            "evidence": evidence_refs or [], "data": data or {},
            "state_version": state_version or {"expected": None, "current": run_id}}


def run_stage(brief, outdir, run_id="research-1"):
    """Evaluate + render. Returns (envelope, exit_code)."""
    r = evaluate(brief)
    if r["outcome"] != "ok":
        return (envelope("research", run_id, r["outcome"], r["reason_code"],
                         r["next_action"], data={"errors": r["errors"]}), EXIT[r["outcome"]])
    try:
        written = render(brief, r["evidence"], outdir)
    except (OSError, ValueError) as e:
        return (envelope("research", run_id, "error", "render-failed", str(e)[:200]),
                EXIT["error"])
    return (envelope("research", run_id, "ok", "research-complete", r["next_action"],
                     data={"files": written}, evidence_refs=written), EXIT["ok"])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="research.py",
                                 description="Research stage runner (directive 21).")
    ap.add_argument("--brief", default=None, help="Brief JSON file.")
    ap.add_argument("--outdir", default=None, help="Run dir for research/ + brief/.")
    ap.add_argument("--run-id", default="research-1")
    a = ap.parse_args(argv)
    if not a.brief or not a.outdir:
        ap.error("--brief and --outdir are required")
    try:
        with open(a.brief, encoding="utf-8") as f:
            brief = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        env = envelope("research", a.run_id, "error", "brief-unreadable", str(e)[:200])
        json.dump(env, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return EXIT["error"]
    env, code = run_stage(brief, a.outdir, a.run_id)
    json.dump(env, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
