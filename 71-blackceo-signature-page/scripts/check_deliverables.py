#!/usr/bin/env python3
"""Verify a run's deliverables/ folder against the fixed manifest contract
(fix plan Item 34; references/deliverables-manifest.md).

  python3 scripts/check_deliverables.py <run_dir> [--json]

Exit 0 only on a clean, complete folder:
- the fixed layout exists (page/, assets/, copy/, reports/, handoffs/,
  receipts/, manifest.json, provenance.json);
- every manifest entry is present, and every file on disk is listed in
  the manifest (an unlisted file fails by name);
- no forbidden material: browser profiles or session directories,
  temporary files, stray screenshots outside the stages' named evidence
  sets, dependency folders, VCS internals;
- no credential material: filenames or content carrying the Amendment 4
  credential names or private-key material fail outright. Only marker
  NAMES are ever printed, never matched values.
"""
import json
import re
import sys
from pathlib import Path

REQUIRED_DIRS = ("page", "assets", "copy", "reports", "handoffs", "receipts")
REQUIRED_FILES = ("manifest.json", "provenance.json",
                  "reports/REPORT.md", "reports/REPORT.json")

FORBIDDEN_DIR_NAMES = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "browser-profile", "browser-profiles", "chrome-profile", "user-data-dir",
    "default", "sessions", "session-storage", "local storage", "indexeddb",
}
FORBIDDEN_FILE_NAMES = {"cookies", "login data", "web data", ".ds_store"}
FORBIDDEN_SUFFIXES = (".tmp", ".temp", ".swp", ".swo", ".part", ".crdownload")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# Amendment 4 credential names. Values are never read into output; a match
# reports the marker name and the file only.
CREDENTIAL_NAME_MARKERS = (
    "GHL_PRIVATE_INTEGRATION_TOKEN", "PRIVATE_INTEGRATION_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN", "FIREBASE_REFRESH_TOKEN",
    "secrets.env",
)
CONTENT_MARKERS = (
    (re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"), "private key material"),
    (re.compile(r"(?i)\brefresh_token\b\s*[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
     "a refresh_token value"),
    (re.compile(r"(?i)\bprivate[_ ]integration[_ ]token\b\s*[\"']?\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
     "a private integration token value"),
    (re.compile(r"\bpit-[A-Za-z0-9_\-]{16,}"), "a GHL PIT-shaped value"),
)


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check(run_dir):
    failures = []
    root = run_dir / "deliverables"
    if not root.is_dir():
        return None, [f"deliverables/ folder is missing at {root}"]
    for d in REQUIRED_DIRS:
        if not (root / d).is_dir():
            failures.append(f"deliverables/{d}/ directory is missing")
    for f in REQUIRED_FILES:
        if not (root / f).is_file():
            failures.append(f"deliverables/{f} is missing")

    manifest = load_json(root / "manifest.json")
    listed = []
    if manifest is None:
        failures.append("deliverables/manifest.json is missing or unreadable")
    else:
        listed = manifest.get("files")
        if not isinstance(listed, list) or not listed:
            failures.append("deliverables/manifest.json lists no files")
            listed = []
    listed_set = set(listed)

    on_disk = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        parts = [part.lower() for part in p.relative_to(root).parts]
        if p.is_dir():
            if any(part in FORBIDDEN_DIR_NAMES for part in parts):
                failures.append(f"forbidden directory in deliverables: {rel}/ "
                                f"(browser profiles, session stores, dependency "
                                f"folders and VCS internals never ship)")
            continue
        on_disk.append(rel)
        name = p.name.lower()
        if name in FORBIDDEN_FILE_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
            failures.append(f"forbidden file in deliverables: {rel} "
                            f"(temporary files and browser session material "
                            f"never ship)")
        if p.suffix.lower() in IMAGE_SUFFIXES and len(p.relative_to(root).parts) == 1:
            failures.append(f"stray screenshot at the deliverables root: {rel} "
                            f"(evidence lives in the stages' named evidence "
                            f"sets, not loose in the delivery)")
        for marker in CREDENTIAL_NAME_MARKERS:
            if marker.lower() in name:
                failures.append(f"credential-named file in deliverables: {rel} "
                                f"(matches {marker}; credential material never ships)")
                break
        if rel not in listed_set:
            failures.append(f"unlisted file in deliverables: {rel} "
                            f"(the manifest indexes the folder exactly)")
    for entry in listed:
        if not (root / entry).is_file():
            failures.append(f"manifest entry missing on disk: deliverables/{entry}")
    failures.extend(check_provenance(root))
    failures.extend(scan_contents(root, on_disk))
    return {"files": len(on_disk), "listed": len(listed)}, failures


def check_provenance(root):
    failures = []
    prov = load_json(root / "provenance.json")
    if prov is None:
        return ["deliverables/provenance.json is missing or unreadable"]
    if not prov.get("run_id"):
        failures.append("provenance.json carries no run_id")
    github = prov.get("github") or {}
    for key in ("owner", "repo", "branch", "commit_sha"):
        if not github.get(key):
            failures.append(f"provenance.github.{key} is missing (identifiers "
                            f"only, never tokens)")
    vercel = prov.get("vercel")
    if not isinstance(vercel, dict):
        failures.append("provenance.vercel block is missing (null values are "
                        "allowed for a route with no Vercel deploy; the block "
                        "is not)")
    ghl = prov.get("ghl")
    if not isinstance(ghl, dict):
        failures.append("provenance.ghl block is missing (null values are "
                        "allowed for a route with no GHL target; the block "
                        "is not)")
    return failures


def scan_contents(root, on_disk):
    failures = []
    for rel in on_disk:
        p = root / rel
        try:
            if p.stat().st_size > 2 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for marker in CREDENTIAL_NAME_MARKERS:
            if marker == "secrets.env":
                continue
            if re.search(re.escape(marker) + r"\s*[\"']?\s*[:=]\s*[\"'][^\"'\s]{8,}", text):
                failures.append(f"deliverables/{rel} contains material assigned "
                                f"to the credential name {marker}; values never ship")
                break
        for pat, label in CONTENT_MARKERS:
            if pat.search(text):
                failures.append(f"deliverables/{rel} contains {label}; credential "
                                f"material never ships")
                break
    return failures


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if len(argv) != 1:
        print("usage: check_deliverables.py <run_dir> [--json]")
        return 2
    run_dir = Path(argv[0]).resolve()
    summary, failures = check(run_dir)
    if as_json:
        print(json.dumps({"ok": not failures, "summary": summary,
                          "failures": failures}, indent=2))
    elif failures:
        print("FAIL")
        for line in failures:
            print(f"- {line}")
    else:
        print(f"PASS: deliverables complete ({summary['files']} files, "
              f"manifest verified)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
