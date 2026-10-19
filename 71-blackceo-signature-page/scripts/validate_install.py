#!/usr/bin/env python3
"""Verify the installed page and the published page (fix plan Item 5).

Two modes, wired as validators in references/stage-contract.json:

  python3 scripts/validate_install.py <run_dir> install
      Gate evidence for ghl-install-test: the receipt's structured `install`
      block (target, journey checks, founder photo), the stage's evidence
      screenshots, and, for the vercel-embed route, the embedded-context
      layer required by the SOP Stages 12-14 (Amendment 6, Item 5 delta).

  python3 scripts/validate_install.py <run_dir> publish
      Gate evidence for publish-verify: fetches the receipt's `public_url`
      (plain HTTP GET, redirects followed, 30s timeout) and checks the LIVE
      bytes: status 200, final URL matches the recorded URL, no private
      framework labels (references/private-label-list.txt), no placeholder
      patterns (reused from validate_page.py, never duplicated here).
      Writes publish-verify/fetch-record.json on every run.

Verdicts: exit 0 PASS, exit 1 FAIL, exit 3 BLOCKED. A network-unreachable
public URL is BLOCKED with a named reason, never a pass and never a content
failure: the stage stays open and the receipt should record status
"blocked". The two verification layers compose as follows (Amendment 6,
Item 5 delta): the standalone fetch layer runs for every route; the
embedded-context layer (iframe sizing, popup visibility, scroll behavior
inside the actual GHL embed, executed through Item 32's browser machinery
and recorded in the install receipt's `embedded_checks`) is additionally
required when the route is vercel-embed, and publish-verify cannot close
on the fetch layer alone for that route.

SOP Stage 13 rules carried here by name: a shared form is submitted ONCE
with a designated test contact (install.form_submit_test.submissions_count
must be exactly 1 when a submission was performed), and sales are verified
in test mode only (install.sales_check.live_charge_made must be false).
"""
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
FETCH_TIMEOUT = 30
MAX_BODY_BYTES = 5 * 1024 * 1024

BUILD_MARKER_PATTERNS = [
    re.compile(r"<!--\s*skill71-build\s+run_id=(?P<run_id>[^\s>]+)\s+commit=(?P<commit>[0-9a-fA-F]{7,64})\s*-->"),
    re.compile(r"<meta\s+name=[\"']skill71-build[\"']\s+content=[\"']run_id=(?P<run_id>[^;\"']+);\s*commit=(?P<commit>[0-9a-fA-F]{7,64})[\"']", re.I),
]


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_receipt(run_dir, stage):
    return load_json(run_dir / "private" / "receipts" / f"{stage}.json")


def load_intake(run_dir):
    return load_json(run_dir / "intake.json") or {}


def brand_path_for(run_dir):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import brand_colors  # SPF019: the resolved palette, never a silent BlackCEO one
    return brand_colors.brand_path(run_dir)


def placeholder_patterns():
    """Reuse validate_page.py's PLACEHOLDER_PATTERNS by import (Item 5: do
    not duplicate the list). validate_page exits at import when Playwright
    is absent; in that case read the same list out of the module source so
    the patterns still come from validate_page.py and nowhere else."""
    sys.path.insert(0, str(SKILL_ROOT / "scripts"))
    try:
        import validate_page
        return list(validate_page.PLACEHOLDER_PATTERNS)
    except BaseException:
        pass
    src = (SKILL_ROOT / "scripts" / "validate_page.py").read_text(encoding="utf-8")
    m = re.search(r"PLACEHOLDER_PATTERNS\s*=\s*\[(.*?)\n\]", src, re.S)
    if not m:
        return []
    out = []
    for pat, name in re.findall(r"re\.compile\(r\"(.*?)\"(?:,\s*re\.I)?\)\s*,\s*\"(.*?)\"", m.group(1)):
        flags = re.I if f're.compile(r"{pat}", re.I)' in m.group(1) else 0
        out.append((re.compile(pat, flags), name))
    return out


def private_labels():
    labels = []
    p = SKILL_ROOT / "references" / "private-label-list.txt"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                labels.append(line)
    return labels


def is_true(v):
    return v is True


def check_install(run_dir):
    """Return (failures, notes)."""
    failures, notes = [], []
    receipt = load_receipt(run_dir, "ghl-install-test")
    if not receipt:
        return [f"no receipt at private/receipts/ghl-install-test.json"], notes
    install = receipt.get("install")
    if not isinstance(install, dict):
        return ["ghl-install-test receipt carries no structured `install` block "
                "(fix plan Item 5); journey claims in prose are not evidence"], notes

    target = install.get("target") or {}
    kind = target.get("kind")
    if kind not in ("ghl", "vercel-embed"):
        failures.append(f"install.target.kind must be \"ghl\" or \"vercel-embed\", got {kind!r}")
    if not target.get("funnel_or_site_id"):
        failures.append("install.target.funnel_or_site_id is missing")
    if not target.get("page_id_or_url"):
        failures.append("install.target.page_id_or_url is missing")

    journey = install.get("journey_checks") or {}
    clicks = journey.get("cta_clicks")
    if not isinstance(clicks, list) or not clicks:
        failures.append("install.journey_checks.cta_clicks must list every CTA clicked "
                        "with its destination and result")
    else:
        for c in clicks:
            if not isinstance(c, dict) or not is_true(c.get("ok")):
                failures.append(f"CTA click check not ok: {c!r}")
            elif not c.get("destination"):
                failures.append(f"CTA click check for {c.get('label')!r} names no destination")

    fst = journey.get("form_submit_test") or {}
    if is_true(fst.get("performed")):
        if not is_true(fst.get("ok")):
            failures.append("install.journey_checks.form_submit_test was performed but is not ok")
        if not fst.get("test_contact_id"):
            failures.append("form submit test names no designated test contact "
                            "(SOP Stage 13: submit a shared form only ONCE, with a "
                            "designated test contact)")
        if fst.get("submissions_count") != 1:
            failures.append(f"form_submit_test.submissions_count must be exactly 1 "
                            f"(SOP Stage 13 once-only rule), got {fst.get('submissions_count')!r}")
    else:
        if not (isinstance(fst.get("not_applicable_reason"), str) and fst["not_applicable_reason"].strip()):
            failures.append("form_submit_test.performed is false and no "
                            "not_applicable_reason is named")
    for key in ("popup_open_close", "mobile_keyboard_scroll"):
        sub = journey.get(key) or {}
        if not is_true(sub.get("ok")):
            failures.append(f"install.journey_checks.{key}.ok is not true")

    sales = install.get("sales_check") or {}
    if sales.get("live_charge_made") is True:
        failures.append("install.sales_check.live_charge_made is true: sales are verified "
                        "in test mode only, never by an unauthorized live charge "
                        "(SOP Stage 13)")
    if kind is not None and sales.get("mode") not in ("test", "not_applicable"):
        failures.append("install.sales_check.mode must be \"test\" or \"not_applicable\"")

    # Evidence screenshots (also required artifacts in the contract).
    for rel in ("ghl-install-test/evidence/desktop.png", "ghl-install-test/evidence/mobile.png"):
        if not (run_dir / rel).is_file():
            failures.append(f"missing install evidence screenshot: {rel}")

    failures.extend(check_founder_photo(run_dir, install))
    failures.extend(check_embedded_layer(install, kind))
    return failures, notes


def check_founder_photo(run_dir, install):
    """The installed page's founder photo must hash to the brand file's
    recorded founder photo SHA-256 (the same bytes validate_page.py checks
    locally, verified again at the installed location)."""
    brand = load_json(brand_path_for(run_dir)) or {}
    known = []
    for entry in brand.get("founder_photos") or []:
        if isinstance(entry, str) and entry.startswith("sha256:"):
            known.append(entry.split(":", 1)[1].lower())
    fp = install.get("founder_photo")
    if not known:
        return []
    if not isinstance(fp, dict):
        return ["brand file records founder photo hashes but install.founder_photo "
                "is missing: the installed founder photo was not verified by hash"]
    if fp.get("not_applicable_reason"):
        return []
    source = fp.get("path") or fp.get("url")
    if not source:
        return ["install.founder_photo names neither a run-relative path nor a URL"]
    data = None
    p = run_dir / source
    if p.is_file():
        data = p.read_bytes()
    elif isinstance(source, str) and source.startswith(("http://", "https://")):
        try:
            req = urllib.request.Request(source, headers={"User-Agent": "skill71-validate-install"})
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                data = resp.read()
        except Exception as exc:
            return [f"founder photo could not be fetched from {source}: {exc}"]
    if data is None:
        return [f"install.founder_photo source {source!r} is not a file under the run dir"]
    digest = hashlib.sha256(data).hexdigest()
    declared = str(fp.get("sha256", "")).removeprefix("sha256:").lower()
    if declared and declared != digest:
        return [f"founder photo SHA-256 mismatch: install receipt declares "
                f"{declared[:12]}..., bytes on record hash to {digest[:12]}..."]
    if digest not in known:
        return [f"founder photo SHA-256 {digest[:12]}... is not one of the brand "
                f"file's recorded founder photo hashes"]
    return []


def check_embedded_layer(install, kind):
    """Amendment 6, Item 5 delta: the vercel-embed route additionally
    requires the embedded-context layer (SOP Stage 12-14 checks executed in
    the actual GHL embed, via Item 32's browser machinery)."""
    if kind != "vercel-embed":
        return []
    emb = install.get("embedded_checks")
    if not isinstance(emb, dict):
        return ["vercel-embed route requires install.embedded_checks (iframe sizing, "
                "popup visibility, scroll behavior in the embedded GHL context; "
                "SOP Stages 12-14): a standalone fetch cannot evidence the "
                "embedded experience"]
    failures = []
    for key in ("iframe_sizing", "popup_visibility", "scroll_behavior"):
        sub = emb.get(key) or {}
        if not is_true(sub.get("ok")):
            failures.append(f"install.embedded_checks.{key}.ok is not true")
    if emb.get("performed_in") != "ghl_embed":
        failures.append("install.embedded_checks.performed_in must be \"ghl_embed\" "
                        "(the checks run in the embedded context, not standalone)")
    return failures


def normalize_url(url):
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def extract_build_marker(html):
    for pat in BUILD_MARKER_PATTERNS:
        m = pat.search(html)
        if m:
            return {"run_id": m.group("run_id"), "commit_sha": m.group("commit").lower()}
    return None


def check_publish(run_dir):
    """Return (verdict, lines) where verdict is pass/fail/blocked."""
    receipt = load_receipt(run_dir, "publish-verify")
    if not receipt:
        return "fail", ["no receipt at private/receipts/publish-verify.json"]
    public_url = receipt.get("public_url")
    if not isinstance(public_url, str) or not public_url.startswith(("http://", "https://")):
        return "fail", ["publish-verify receipt carries no usable `public_url`"]

    record = {
        "url": public_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": [],
    }
    lines = []
    try:
        req = urllib.request.Request(public_url, headers={"User-Agent": "skill71-validate-install"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            status = resp.getcode()
            final_url = resp.geturl()
            body = resp.read(MAX_BODY_BYTES + 1)[:MAX_BODY_BYTES]
    except Exception as exc:
        # Network-unavailable: BLOCKED with a named reason, never a silent
        # pass (Item 5) and never recorded as a content failure.
        record.update({"verdict": "blocked", "status": None, "final_url": None,
                       "bytes": 0, "reason": f"network unreachable: {exc}"})
        write_fetch_record(run_dir, record)
        return "blocked", [f"public URL {public_url} could not be fetched "
                            f"({exc}); the stage stays open"]
    html = body.decode("utf-8", "replace")
    record.update({"status": status, "final_url": final_url, "bytes": len(body)})

    if status != 200:
        lines.append(f"public URL returned HTTP {status}, expected 200")
        record["checks"].append("status_200: fail")
    else:
        record["checks"].append("status_200: pass")
    if normalize_url(final_url) != normalize_url(public_url):
        lines.append(f"final URL after redirects ({final_url}) does not match the "
                     f"recorded public_url ({public_url})")
        record["checks"].append("final_url_match: fail")
    else:
        record["checks"].append("final_url_match: pass")

    for label in private_labels():
        if label.lower() in html.lower():
            lines.append(f"fetched page contains private framework label: {label!r}")
    record["checks"].append("private_labels: scanned")
    for pat, name in placeholder_patterns():
        m = pat.search(html)
        if m:
            lines.append(f"fetched page contains placeholder ({name}): {m.group(0)!r}")
    record["checks"].append("placeholders: scanned")

    marker = extract_build_marker(html)
    record["build_marker"] = marker
    record["checks"].append("build_marker: " + ("found" if marker else "absent"))

    lines.extend(check_provenance_composition(run_dir, receipt, public_url, final_url, marker))
    record["verdict"] = "fail" if lines else "pass"
    write_fetch_record(run_dir, record)
    return record["verdict"], lines


def check_provenance_composition(run_dir, receipt, public_url, final_url, marker):
    """Item 34's three bindings, verified at publish time: the embed URL in
    Item 32's step binding equals the deploy receipt's verified URL (both
    recorded in deliverables/provenance.json); the publish fetch hits that
    exact URL; and the fetched page's build marker (run ID + commit SHA)
    matches provenance. Required when the route is vercel-embed or a
    provenance record exists."""
    install_receipt = load_receipt(run_dir, "ghl-install-test") or {}
    kind = ((install_receipt.get("install") or {}).get("target") or {}).get("kind")
    prov_path = run_dir / "deliverables" / "provenance.json"
    prov = load_json(prov_path)
    if prov is None:
        if kind == "vercel-embed":
            return ["vercel-embed route requires deliverables/provenance.json "
                    "(Item 34) so the embed, deploy, and fetch records can be "
                    "verified against each other"]
        return []
    lines = []
    vercel_url = ((prov.get("vercel") or {}).get("url"))
    if vercel_url:
        if normalize_url(vercel_url) != normalize_url(public_url):
            lines.append(f"provenance vercel.url ({vercel_url}) does not match the "
                         f"publish-verify public_url ({public_url})")
        if normalize_url(vercel_url) != normalize_url(final_url):
            lines.append(f"provenance vercel.url ({vercel_url}) does not match the "
                         f"fetched final URL ({final_url})")
        fc = load_json(run_dir / "ghl-install-test" / "funnel-completion.json") or {}
        for step in fc.get("steps") or []:
            binding = step.get("binding") or {}
            if binding.get("kind") == "external_embed":
                embed_url = binding.get("embed_url")
                if embed_url and normalize_url(embed_url) != normalize_url(vercel_url):
                    lines.append(f"funnel step {step.get('name')!r} embeds {embed_url} "
                                 f"but provenance deployment URL is {vercel_url}")
    commit = ((prov.get("github") or {}).get("commit_sha") or "")
    if marker:
        if commit and marker["commit_sha"] != str(commit).lower():
            lines.append(f"fetched page build marker commit {marker['commit_sha'][:12]}... "
                         f"does not match provenance github.commit_sha "
                         f"{str(commit)[:12]}...")
        if prov.get("run_id") and marker["run_id"] != prov["run_id"]:
            lines.append(f"fetched page build marker run_id {marker['run_id']!r} does "
                         f"not match provenance run_id {prov['run_id']!r}")
    elif kind == "vercel-embed":
        lines.append("fetched page carries no skill71 build marker "
                     "(<!-- skill71-build run_id=... commit=... -->): provenance "
                     "cannot be verified against the live bytes")
    return lines


def write_fetch_record(run_dir, record):
    out_dir = run_dir / "publish-verify"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fetch-record.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[1] not in ("install", "publish"):
        print("usage: validate_install.py <run_dir> install|publish")
        return 2
    run_dir = Path(argv[0]).resolve()
    if not run_dir.exists():
        print(f"FAIL: run_dir does not exist: {run_dir}")
        return 2
    if argv[1] == "install":
        failures, _ = check_install(run_dir)
        if failures:
            print("FAIL")
            for line in failures:
                print(f"- {line}")
            return 1
        print("PASS: install receipt, journey checks, founder photo hash, "
              "evidence, and embedded layer (where required) verified")
        return 0
    verdict, lines = check_publish(run_dir)
    if verdict == "pass":
        print("PASS: public URL fetched live; status, final URL, private-label "
              "and placeholder scans, and provenance bindings verified "
              "(publish-verify/fetch-record.json written)")
        return 0
    if verdict == "blocked":
        print("BLOCKED")
        for line in lines:
            print(f"- {line}")
        print("- publish-verify/fetch-record.json records verdict \"blocked\"; "
              "record the receipt status as \"blocked\" and leave the stage open")
        return 3
    print("FAIL")
    for line in lines:
        print(f"- {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
