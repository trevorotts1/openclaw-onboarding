#!/usr/bin/env python3
"""Fixture capture / refresh path for S75-W04-U2 capability work.

This is the supported refresh path for every cache fixture used by
capability_control: each captured fixture carries source revision, fetched
time and this refresh path (spec 7.5). Re-run to refresh:

    python3 -I tools/capture_fixtures.py --out fixtures/

Redaction rules (operator standing rule): never emit credential values.
Projections keep key NAMES and counts only; every fixture is metadata.
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UNIT_ROOT = os.path.dirname(HERE)

HOST_BASE = os.environ.get("S75_HOST_BASE", "http://127.0.0.1:20128")
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
ROUTER_DB = os.path.expanduser("~/.9router/db/data.sqlite")
MODEL_CACHE = os.path.expanduser("~/.9router/model-catalog.json")
NINE_SETTINGS = os.path.expanduser("~/.claude-nine/settings.json")

SECRET_MARKERS = ("key", "token", "secret", "password", "auth", "credential")
REFRESH_PATH = "python3 -I tools/capture_fixtures.py --out fixtures/"


def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(source, revision=None, path=None):
    return {
        "source": source,
        "source_revision": revision,
        "fetched_at": now_iso(),
        "refresh_path": REFRESH_PATH,
        "source_sha256": sha256_file(path) if path and os.path.exists(path) else None,
    }


def is_secret_key(name):
    low = str(name).lower()
    return any(m in low for m in SECRET_MARKERS)


def redact_value(key, value):
    return "<redacted>" if is_secret_key(key) else value


def get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"user-agent": "s75-w04-u2-fixture-capture"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")), dict(resp.headers)


def safe_settings_projection(path):
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    env = doc.get("env", {}) or {}
    return {
        "schema": doc.get("$schema"),
        "model": doc.get("model"),
        "model_aliases_env": {
            k: v for k, v in env.items() if k.startswith("ANTHROPIC_DEFAULT_") or k == "ANTHROPIC_BASE_URL"
        },
        "model_settings": doc.get("modelSettings", {}),
        "model_overrides": doc.get("modelOverrides", {}),
        "teammate_default_model": doc.get("teammateDefaultModel"),
        "model_picker_options": [
            {"model": o.get("model"), "label": o.get("label")} for o in (doc.get("modelPicker", {}) or {}).get("options", [])
        ],
    }


def router_db_projection(db_path):
    con = sqlite3.connect(db_path)
    try:
        kv = {}
        for scope in ("customModels", "disabledModels", "modelAliases"):
            rows = con.execute("SELECT key FROM kv WHERE scope=?", (scope,)).fetchall()
            kv[scope] = sorted(r[0] for r in rows)
        combos = [
            {"name": name, "models": json.loads(models)}
            for name, kind, models in con.execute("SELECT name, kind, models FROM combos ORDER BY name")
        ]
        settings_row = con.execute("SELECT data FROM settings").fetchone()
        settings = json.loads(settings_row[0]) if settings_row else {}
        provider_thinking = {
            k: redact_value(k, v if isinstance(v, dict) and "mode" in v else {"keys": sorted(v.keys()) if isinstance(v, dict) else type(v).__name__})
            for k, v in (settings.get("providerThinking") or {}).items()
        }
        return {
            "kv": kv,
            "combos": combos,
            "settings_keys": sorted(settings.keys()),
            "provider_thinking": provider_thinking,
            "combo_strategy": settings.get("comboStrategy"),
            "provider_strategy_keys": sorted((settings.get("providerStrategies") or {}).keys()),
            "quota_visibility_keys": sorted((settings.get("quotaVisibility") or {}).keys()),
        }
    finally:
        con.close()


def crontab_lines():
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
        return [ln for ln in out.stdout.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    except Exception as exc:  # pragma: no cover - capture-time only
        return ["<unavailable: %s>" % exc]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(UNIT_ROOT, "fixtures"))
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    written = []

    def write(name, doc):
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
            fh.write("\n")
        written.append(name)

    # 1. Authoritative provider catalog (OpenRouter public catalog API).
    try:
        cat, headers = get_json(OPENROUTER_MODELS)
        keep = {}
        for m in cat.get("data", []):
            if m.get("id") in (
                "xiaomi/mimo-v2.6-pro",
                "xiaomi/mimo-v2.6-flash",
                "z-ai/glm-5.3",
                "z-ai/glm-5.3-flash",
            ):
                keep[m["id"]] = {
                    "id": m.get("id"),
                    "supported_parameters": m.get("supported_parameters"),
                    "architecture": m.get("architecture", {}).get("output_modalities"),
                    "context_length": m.get("context_length"),
                }
        write(
            "provider-catalog.openrouter.json",
            {
                "provenance": provenance(
                    OPENROUTER_MODELS,
                    revision=headers.get("etag") or headers.get("date"),
                ),
                "models": keep,
            },
        )
    except Exception as exc:
        write("provider-catalog.openrouter.json", {"provenance": provenance(OPENROUTER_MODELS), "error": str(exc), "models": {}})

    # 2. Installed host catalog (the router's /v1/models) — capability flags.
    try:
        host, headers = get_json(HOST_BASE + "/v1/models")
        write(
            "host-catalog.9router.json",
            {
                "provenance": provenance(HOST_BASE + "/v1/models", revision=headers.get("etag") or headers.get("date")),
                "models": host.get("data", []),
            },
        )
    except Exception as exc:
        write("host-catalog.9router.json", {"provenance": provenance(HOST_BASE + "/v1/models"), "error": str(exc), "models": []})

    # 3. Router DB surfaces (allowlists, provider entries, combos, settings keys).
    write("router-surfaces.db.json", {"provenance": provenance(ROUTER_DB, path=ROUTER_DB), **router_db_projection(ROUTER_DB)})

    # 4. Session/UI model-catalog cache (version surface).
    with open(MODEL_CACHE, "r", encoding="utf-8") as fh:
        cache = json.load(fh)
    write(
        "session-cache.model-catalog.json",
        {
            "provenance": provenance(MODEL_CACHE, path=MODEL_CACHE),
            "cache_meta": {
                "v": cache.get("v"),
                "etag": cache.get("etag"),
                "syncedAt": cache.get("syncedAt"),
                "model_count": len(cache.get("models", {})),
                "provider_count": len(cache.get("providers", {})),
            },
        },
    )

    # 5. Host settings aliases (claude-nine) — role/alias bindings, redacted.
    write("host-settings.claude-nine.json", {"provenance": provenance(NINE_SETTINGS, path=NINE_SETTINGS), **safe_settings_projection(NINE_SETTINGS)})

    # 6. Scheduler jobs (crontab).
    write("scheduler-jobs.crontab.json", {"provenance": provenance("crontab -l"), "jobs": crontab_lines()})

    print("wrote %d fixtures to %s" % (len(written), out))
    for name in written:
        print(" -", name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
