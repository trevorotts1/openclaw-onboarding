"""preflight.py: dependency/auth checks before paid work (24.2 row 2). stdlib only.

NAMES only: resolves tools via shutil.which, disk via shutil.disk_usage.
Never executes tools, never submits generation, never logs credential values.
Successful exit never means paid submission occurred.
"""
import importlib
import os
import shutil

# ponytail: no network/catalog probe; add provider allowlist fetch when needed.


def check_tools(names):
    return {n: (shutil.which(n) is not None) for n in (names or [])}


def check_modules(names):
    out = {}
    for n in (names or []):
        try:
            importlib.import_module(n)
            out[n] = True
        except Exception:
            out[n] = False
    return out


def check_disk(path, min_free_bytes=0):
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "free": u.free,
                "ok": u.free >= (min_free_bytes or 0)}
    except Exception as e:
        return {"error": str(e)[:200], "ok": False}


def check_storage_writable(path):
    return os.path.isdir(path) and os.access(path, os.W_OK | os.X_OK)


def check_credentials(names, env=None):
    env = env if env is not None else os.environ
    return {n: bool(env.get(n)) for n in (names or [])}  # presence only, values never returned


def _inside(root, p):
    root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root, p)) if not os.path.isabs(p) else os.path.realpath(p)
    return target == root or target.startswith(root + os.sep), target


#: Version-2 delivery profiles (H8): five lengths x two shapes, named
#: ``drama-<shape>-<length>s`` -- the only profiles preflight allows by
#: default. The version-1 ``short-9x16-30s`` profile is retired.
PROFILE_LENGTHS_S = (60, 90, 180, 300, 600)
PROFILE_SHAPES = ("9x16", "16x9")
DEFAULT_PROFILES = tuple(
    "drama-%s-%ss" % (shape, secs)
    for secs in PROFILE_LENGTHS_S for shape in PROFILE_SHAPES
)


def check(payload):
    """payload keys: tools, modules, storage_dir, min_free_bytes, approved_root,
    references[], profile, allowed_profiles[], schema_version, allowed_schemas[],
    credentials[], env{}, auth{}, summary_digest. Returns outcome/reason/checks."""
    p = payload or {}
    checks = {}
    schemas = p.get("allowed_schemas") or ["blackceo.campaign/v1"]
    sv = p.get("schema_version") or "blackceo.campaign/v1"
    checks["schema_trusted"] = sv in schemas
    if not checks["schema_trusted"]:
        return {"outcome": "error", "reason_code": "schema-untrusted",
                "checks": checks, "next_action": f"Use a trusted schema: {schemas}."}
    allowed = p.get("allowed_profiles") or list(DEFAULT_PROFILES)
    checks["profile_known"] = (p.get("profile") or DEFAULT_PROFILES[0]) in allowed
    if not checks["profile_known"]:
        return {"outcome": "rejected", "reason_code": "delivery-profile-unknown",
                "checks": checks, "next_action": f"Choose a delivery profile in {allowed}."}
    root = p.get("approved_root") or p.get("storage_dir") or os.getcwd()
    bad, outside = [], []
    for r in (p.get("references") or []):
        ok, target = _inside(root, r)
        if not ok:
            outside.append(r)
        elif not (os.path.isfile(target) and os.path.getsize(target) > 0):
            bad.append(r)
    checks["references_ok"] = not bad
    checks["references_inside_approved_storage"] = not outside
    if outside:
        return {"outcome": "rejected", "reason_code": "reference-outside-approved-storage",
                "checks": checks, "missing": [], "outside": outside,
                "next_action": "Move references inside approved storage and retry."}
    if bad:
        return {"outcome": "error", "reason_code": "reference-missing-or-truncated",
                "checks": checks, "missing": bad,
                "next_action": "Restore missing/truncated references and retry."}
    tools = check_tools(p.get("tools"))
    checks["tools"] = tools
    if not all(tools.values()):
        return {"outcome": "error", "reason_code": "tool-unavailable",
                "checks": checks, "missing": sorted(k for k, v in tools.items() if not v),
                "next_action": "Install missing runtime tools and retry."}
    mods = check_modules(p.get("modules"))
    checks["modules"] = mods
    if not all(mods.values()):
        return {"outcome": "error", "reason_code": "module-unavailable",
                "checks": checks, "missing": sorted(k for k, v in mods.items() if not v),
                "next_action": "Install missing Python modules and retry."}
    sdir = p.get("storage_dir") or root
    checks["storage_writable"] = check_storage_writable(sdir)
    disk = check_disk(sdir, p.get("min_free_bytes") or 0)
    checks["disk"] = {k: disk[k] for k in ("total", "free", "ok") if k in disk}
    if not checks["storage_writable"]:
        return {"outcome": "error", "reason_code": "storage-not-writable",
                "checks": checks, "next_action": f"Make {sdir} writable and retry."}
    if not disk.get("ok"):
        return {"outcome": "error", "reason_code": "disk-limit",
                "checks": checks, "next_action": "Free disk space and retry."}
    creds = check_credentials(p.get("credentials"), p.get("env"))
    checks["credentials_present"] = creds
    if creds and not all(creds.values()):
        return {"outcome": "rejected", "reason_code": "credential-missing",
                "checks": checks, "missing": sorted(k for k, v in creds.items() if not v),
                "next_action": "Provide credentials (presence only; values never logged)."}
    auth = p.get("auth") or {}
    if not auth:
        return {"outcome": "rejected", "reason_code": "approval-missing",
                "checks": checks, "next_action": "Record authorization scope before paid work."}
    import time
    exp = auth.get("expires_unix")
    if isinstance(exp, (int, float)) and int(time.time()) > exp:
        return {"outcome": "rejected", "reason_code": "approval-expired",
                "checks": checks, "next_action": "Renew expired authorization."}
    scope = auth.get("scope")
    dgst = p.get("summary_digest")
    if scope not in ("campaign", dgst):
        return {"outcome": "rejected", "reason_code": "approval-out-of-scope",
                "checks": checks, "next_action": "Bind authorization to this campaign summary digest."}
    return {"outcome": "ok", "reason_code": "preflight-pass",
            "checks": checks, "next_action": "Proceed to claim eligible stage."}
