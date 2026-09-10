#!/usr/bin/env python3
"""Leg A delivery: selected delivery with synthetic clients + IDs (Mac+standalone).

Real commands only, stdlib only. No live delivery: runs `presentation export`
(synthetic run) into a delivery dir, records EXPORT-PROVENANCE.json hashes,
stage events from state.json, host/version/package hash, company/run IDs,
routed catalog IDs (resolved-not-called from installed model_catalog.json),
GHL provider surface (6/6 callables, zero network -- connected GHL/CC stay
NOT-VERIFIED, no creds, no live IDs).

Exit 0 when export rc 0 AND state readable AND catalog resolves AND GHL
surface 6/6 AND carriers match. Exit 1 else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PACKET = Path("/Users/blackceomacmini/Downloads/September eighth presentation department fixes")
BUILD = PACKET / "run/artifacts/pres-package/build-4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391"
WHEEL = BUILD / "pkg/dist/presentation_department-0.1.0-py3-none-any.whl"
SDIST = BUILD / "pkg/dist/presentation_department-0.1.0.tar.gz"
PLUGIN = BUILD / "presentation-department-skill-plugin-0.1.0.zip"
EXP_SHA = {
    "wheel_sha256": "d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206",
    "sdist_sha256": "2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4",
    "plugin_sha256": "9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487",
    "manifest_sha256": "cab872039b2dac96bc78300a2158487ee7093e84d55a71069285789ca369f5de",
    "staged_content_sha256": "4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--venv-python", required=True, type=Path)
    ap.add_argument("--venv-cli", required=True, type=Path)
    ap.add_argument("--run-dir", required=True, type=Path)
    ap.add_argument("--delivery-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    out: Path = args.out
    scratch: Path = args.scratch
    vpy: Path = args.venv_python
    cli: Path = args.venv_cli
    rundir: Path = args.run_dir
    ddir: Path = args.delivery_dir
    scratch.mkdir(parents=True, exist_ok=True)
    ddir.mkdir(parents=True, exist_ok=True)
    fails: list[str] = []
    rec: dict = {"leg": "A-delivery (Mac+standalone, synthetic clients)",
                 "generated_at": utcnow(), "synthetic": True,
                 "host": {"system": platform.system(), "release": platform.release(),
                          "machine": platform.machine(),
                          "python": platform.python_version()}}
    got = {"wheel_sha256": sha256_file(WHEEL), "sdist_sha256": sha256_file(SDIST),
           "plugin_sha256": sha256_file(PLUGIN)}
    rec["package_hash"] = {"expected": {k: EXP_SHA[k] for k in got},
                           "actual": got,
                           "all_match": all(got[k] == EXP_SHA[k] for k in got)}
    if not rec["package_hash"]["all_match"]:
        fails.append("package carriers mismatch")
    rec["package_version"] = "0.1.0"

    env = {"PATH": "/opt/homebrew/bin:/usr/bin:/bin",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "HOME": str(scratch / "home"), "TMPDIR": str(scratch)}
    e = subprocess.run([str(cli), "export", "--run-dir", str(rundir), "--out", str(ddir)],
                       capture_output=True, text=True, timeout=300, env=env)
    rec["export"] = {"rc": e.returncode,
                     "out_tail": ((e.stdout or "") + (e.stderr or ""))[-1000:]}
    if e.returncode != 0:
        fails.append("export rc != 0")
    try:
        prov = json.loads((ddir / "EXPORT-PROVENANCE.json").read_text(encoding="utf-8"))
        rec["export_provenance"] = {"job": prov.get("job"),
                                    "files": len(prov.get("files", {}))}
    except Exception as exc:  # noqa: BLE001
        fails.append(f"EXPORT-PROVENANCE.json unreadable: {exc}")
    try:
        st = json.loads((rundir / "state.json").read_text(encoding="utf-8"))
        rec["company_id"] = (st.get("intake") or {}).get("company_id")
        rec["presentation_id"] = (st.get("intake") or {}).get("presentation_id")
        rec["run_job_id"] = st.get("job_id")
        rec["run_dir"] = st.get("run_dir")
        rec["manifest"] = {"version": st.get("manifest_version"),
                           "sha256": st.get("manifest_sha256")}
        rec["stage_events"] = [{"at": x.get("at"), "kind": (x.get("kind") or "")[:70]}
                               for x in st.get("events", [])][:25]
        rec["event_count"] = len(st.get("events", []))
        rec["terminal"] = st.get("terminal")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"state.json unreadable: {exc}")

    c = subprocess.run(
        [str(vpy), "-c",
         "import json; d=json.load(open("
         f"{str(vpy.parent.parent / 'lib' / ('python%d.%d' % (sys.version_info[0], sys.version_info[1])) / 'site-packages' / 'presentation_department' / 'engine' / 'model_catalog.json')!r})); "
         "print(json.dumps({k: {'provider': v.get('provider'), 'model': v.get('model')} for k, v in sorted(d['aliases'].items())}))"],
        capture_output=True, text=True, timeout=60, env=env)
    # fallback: resolve catalog path directly
    if c.returncode != 0:
        c = subprocess.run(
            [str(vpy), "-c",
             "import json, glob; "
             "p=glob.glob(__import__('os').path.join(__import__('sys').prefix, 'lib', 'python*', 'site-packages', 'presentation_department', 'engine', 'model_catalog.json'))[0]; "
             "d=json.load(open(p)); "
             "print(json.dumps({k: {'provider': v.get('provider'), 'model': v.get('model')} for k, v in sorted(d['aliases'].items())}))"],
            capture_output=True, text=True, timeout=60, env=env)
    try:
        routed = json.loads((c.stdout or "").strip().splitlines()[-1])
        rec["routed_model_ids_resolved_not_called"] = routed
        rec["routed_note"] = "resolved from packaged model_catalog.json; zero live model calls"
    except Exception as exc:  # noqa: BLE001
        fails.append(f"catalog resolve failed: {exc} {(c.stderr or '')[-300:]}")

    g = subprocess.run(
        [str(vpy), "-c",
         "from presentation_department import presentation_compat as pc; pc.ensure(); "
         "from presentation_department.providers import ghl as G; "
         "fns=['resolve_location_pit','resolve_location_id','verify_png','upload_media','create_media_folder','list_media']; "
         "print(','.join(f for f in fns if callable(getattr(G, f, None))))"],
        capture_output=True, text=True, timeout=60, env=env)
    surface = (g.stdout or "").strip().splitlines()
    surface = surface[-1] if surface else ""
    rec["ghl_provider_surface"] = {"callable": surface.split(",") if surface else [],
                                   "count": len([x for x in surface.split(',') if x]),
                                   "network": "ZERO calls (no creds, no live location)"}
    if rec["ghl_provider_surface"]["count"] != 6:
        fails.append("GHL provider surface != 6/6")
    rec["provider_media_ids"] = "NONE minted (no live GHL media calls; connected delivery NOT-VERIFIED)"
    rec["connected_ghl_delivery"] = "NOT-VERIFIED (no scoped live location, no credentials)"
    rec["connected_cc_delivery"] = "NOT-VERIFIED (no scoped live Command Center)"
    rec["selected_delivery"] = {"channel": "local-export (synthetic clients only)",
                                "out": str(ddir)}
    rec["status"] = "DEPLOYED-RUN-PASS" if not fails else "FAIL"
    rec["failures"] = fails
    with tempfile.NamedTemporaryFile("w", dir=str(scratch), delete=False,
                                     suffix=".json") as fh:
        json.dump(rec, fh, indent=2)
        tmp = fh.name
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, out)
    print(json.dumps({"status": rec["status"], "failures": fails,
                      "job": rec.get("run_job_id")}, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
