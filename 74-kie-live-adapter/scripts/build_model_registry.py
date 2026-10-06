#!/usr/bin/env python3
"""Skill 74 - build references/kie-model-registry.json: the limits and price snapshot of EVERY KIE model.

Source order: (1) the live API through the adapter (catalog once, then one schema call per model, spaced
1.1 seconds by the adapter, key via shared-utils key_resolver); (2) when no key resolves, KIE's public docs
(llms.txt, then each market model page's OpenAPI block; needs PyYAML), prices recorded as
"unavailable-without-key". Python 3 standard library; PyYAML only if already importable.

The registry is a dated snapshot and the offline fallback for `validate`, `prompt-budget`, `price` and
`latest-family`. Run: python3 scripts/build_model_registry.py [--out PATH] [--source auto|live|docs] [--limit N]
Never prints a key. Writes only the output file (default: references/kie-model-registry.json).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kie_live_adapter as K  # noqa: E402

SCHEMA_VERSION = "1.0.0"
DEFAULT_OUT = os.path.join(HERE, "..", "references", "kie-model-registry.json")
DOCS_INDEX = "https://docs.kie.ai/llms.txt"
_KIND = {K.JOB_PATH: "createTask"}
_TASK_WORDS = [("text-to-image", "Text to Image"), ("image-to-image", "Image to Image"), ("text-to-video", "Text to Video"),
               ("image-to-video", "Image to Video"), ("video-to-video", "Video to Video"),
               ("text-to-speech", "Text to Speech"), ("-edit", "Image Editing")]


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def entry_from_schema(model_id, doc, meta):
    """One registry row from a model's OpenAPI document (live or docs). meta: provider/title/taskType/pricing."""
    paths = []
    for p, item in (doc.get("paths") or {}).items():
        for m in ("post", "put"):
            if isinstance((item or {}).get(m), dict):
                paths.append({"path": p, "method": m, "kind": _KIND.get(p, "sync")})
    path, method, body = K.pick_submit(doc)
    isch = ((body.get("properties") or {}).get("input") or {}) if path == K.JOB_PATH else body
    fields, required, branches = K.flatten_input(isch)
    tt = meta.get("taskType") or []
    pf = K.prompt_field_of(model_id, fields, tt)
    return {
        "schema": {"readable": True, "submit_path": path, "method": method, "kind": _KIND.get(path, "sync")},
        "schema_paths": paths,
        "callback_supported": path == K.JOB_PATH and "callBackUrl" in (body.get("properties") or {}),
        "required": required, "input_fields": fields, "branches": branches,
        "prompt_field": pf, "verbatim_fields": K.verbatim_fields(model_id, fields, tt),
    }


def pricing_block(raw, status):
    if status != "ok":
        return {"raw": None, "status": status, "credits_min": None, "credits_max": None, "unit": None,
                "credits_estimate": None}
    p = K.parse_pricing(raw)
    return {"raw": raw, "status": "ok" if p["all"] else "no-credit-figure", "credits_min": p["credits_min"],
            "credits_max": p["credits_max"], "unit": p["unit"], "credits_estimate": K.estimate_credits(p)}


def base_row(model_id, meta, pricing):
    return {"id": model_id, "provider": meta.get("provider"), "title": meta.get("title"),
            "taskType": meta.get("taskType") or [], "family": K.family_of(model_id),
            "version": K.version_of(model_id), "variant": K.variant_of(model_id), "pricing": pricing}


def build_live(ad, limit=None, ids=None, log=print):
    models, fetched, src = ad.catalog()
    rows, errs = [], 0
    for i, m in enumerate(models):
        mid = m.get("model")
        if (ids and mid not in ids) or (limit and len(rows) >= limit):
            continue
        row = base_row(mid, m, pricing_block(m.get("pricingDesc"), "ok"))
        try:
            oa, _, _ = ad.schema(mid)
            row.update(entry_from_schema(mid, oa, m))
        except K.KieError as e:
            errs += 1
            row.update(schema={"readable": False, "error": {"code": e.code, "msg": ad.redact(e.msg)[:200]}},
                       schema_paths=[], callback_supported=False, required=[], input_fields={}, branches=[],
                       prompt_field={"name": None, "maxLength": None, "verbatim": False, "max_source": None,
                                     "limits_listed": []}, verbatim_fields=[])
        rows.append(row)
        log("%d/%d %s %s" % (len(rows), len(models), mid, "ok" if row["schema"]["readable"] else "no-schema"))
    return rows, {"catalog_total": len(models), "catalog_fetched_at": iso(fetched)}


# ---------------------------------------------------------------- public docs
def _yaml():
    try:
        import yaml  # only if already importable
        return yaml
    except ImportError:
        return None


def docs_pages(index_text):
    """Market model page URLs from llms.txt: [(title, url)]. Chinese mirrors and non-market pages are skipped."""
    out = []
    for m in re.finditer(r"\[([^\]]+)\]\((https://docs\.kie\.ai/market/[^)\s]+\.md)\)", index_text):
        url = m.group(2)
        if "/cn/" not in url and not url.endswith(("quickstart.md", "get-task-detail.md")) and "/common/" not in url:
            out.append((m.group(1), url))
    return out


def openapi_from_md(md):
    y = _yaml()
    for block in re.findall(r"```yaml\n(.*?)```", md, re.S):
        if block.lstrip().startswith("openapi:"):
            return y.safe_load(block)
    return None


def build_docs(transport, limit=None, spacing=0.3, sleep=time.sleep, log=print):
    if _yaml() is None:
        raise K.KieError("no_yaml", "public-docs source needs PyYAML (already-installed only); install it or provide a key")
    st, raw = transport.request("GET", DOCS_INDEX, {}, None, 60)
    if st != 200:
        raise K.KieError("docs_unreachable", "docs index HTTP %s" % st)
    pages, rows, seen, skipped = docs_pages(raw.decode("utf-8", "replace")), [], set(), 0
    for title, url in pages:
        if limit and len(rows) >= limit:
            break
        sleep(spacing)
        st, raw = transport.request("GET", url, {}, None, 60)
        doc = openapi_from_md(raw.decode("utf-8", "replace")) if st == 200 else None
        try:
            _, _, body = K.pick_submit(K.resolve(doc, doc)) if doc else (None, None, None)
            mprop = (body or {}).get("properties", {}).get("model") or {}
            mid = (mprop.get("enum") or [mprop.get("default")])[0]
        except (K.KieError, AttributeError, TypeError, IndexError):
            mid = None
        if not mid or mid in seen or K.JOB_PATH not in (doc.get("paths") or {}):
            skipped += 1  # pages without a createTask model id (guides, callbacks, sync endpoints)
            continue
        seen.add(mid)
        tags = (((doc["paths"][K.JOB_PATH].get("post") or {}).get("tags")) or [""])[0].split("/")
        tt = [lbl for key, lbl in _TASK_WORDS if key in mid.lower()]
        meta = {"provider": tags[-1].strip() or None, "title": title, "taskType": tt}
        row = base_row(mid, meta, pricing_block(None, "unavailable-without-key"))
        row.update(entry_from_schema(mid, K.resolve(doc, doc), meta))
        row["schema"]["source_url"] = url
        rows.append(row)
        log("%d %s" % (len(rows), mid))
    return rows, {"catalog_total": len(rows), "docs_pages_skipped": skipped,
                  "coverage_note": "public docs cover createTask market models only (no synchronous chat models); "
                                   "provider is the docs section name; taskType is inferred from the id"}


def counts(rows):
    fam = {}
    for r in rows:
        fam[r["family"]] = fam.get(r["family"], 0) + 1
    return {"models": len(rows), "schema_readable": sum(r["schema"]["readable"] for r in rows),
            "schema_not_readable": sum(not r["schema"]["readable"] for r in rows),
            "kind_createTask": sum(r["schema"].get("kind") == "createTask" for r in rows),
            "kind_sync": sum(r["schema"].get("kind") == "sync" for r in rows),
            "with_prompt_field": sum(r["prompt_field"]["name"] is not None for r in rows),
            "prompt_max_known": sum(r["prompt_field"]["maxLength"] is not None for r in rows),
            "with_verbatim_fields": sum(bool(r["verbatim_fields"]) for r in rows),
            "price_parsed": sum(r["pricing"]["credits_max"] is not None for r in rows),
            "families": dict(sorted(fam.items()))}


def build(ad=None, source="auto", out=DEFAULT_OUT, limit=None, ids=None, now=time.time, log=print, transport=None):
    ad = ad or K.Adapter()
    src = source
    if source in ("auto", "live"):
        if ad.key:
            src = "live-api"
        elif source == "live":
            raise K.KieError("no_key", "KIE_API_KEY did not resolve; use --source docs")
        else:
            src = "public-docs"
    if src == "live-api":
        rows, extra = build_live(ad, limit, ids, log)
    else:
        rows, extra = build_docs(transport or ad.t, limit, log=log)
        src = "public-docs"
    rows.sort(key=lambda r: r["id"])
    reg = {"schema_version": SCHEMA_VERSION, "generated_at": iso(now()), "source": src, "adapter": K.ADAPTER,
           "price_note": "pricing.raw is KIE's pricingDesc prose; credits are parsed numbers (never USD)." if src == "live-api"
           else "prices unavailable-without-key", "counts": counts(rows), **extra, "models": rows}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=1)
        f.write("\n")
    os.replace(tmp, out)
    return reg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--source", choices=["auto", "live", "docs"], default="auto")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--models", help="comma-separated ids (partial rebuild for checks)")
    a = ap.parse_args(argv)
    try:
        reg = build(source=a.source, out=a.out, limit=a.limit, ids=set(a.models.split(",")) if a.models else None,
                    log=lambda *x: print(*x, file=sys.stderr))
    except K.KieError as e:
        print("registry build failed: %s: %s" % (e.code, e.msg), file=sys.stderr)
        return 1
    print(json.dumps({"source": reg["source"], "generated_at": reg["generated_at"], "counts": reg["counts"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
