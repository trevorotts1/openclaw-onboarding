#!/usr/bin/env python3
"""Skill 74 - KIE live adapter. Python 3 standard library only.

Implements the contract KIE documents in its official kie-models skill
(catalog, schema, upload, createTask, recordInfo, download-url, credits).
Backend is "native-live": this file is our own code. The vendor package is
never a runtime dependency.

Hard rules: never picks or rewrites a model; never auto-routes to a newly
discovered model; never retries createTask after a network error (that could
double charge); never prints the key.

Do NOT copy this file into a Presentations deck run directory
(canonical_render_guard.py blocks non-canonical scripts that mention the API).
"""
import argparse
import base64
import hashlib
import json
import math
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ADAPTER = "74-kie-live-adapter"
API = "https://api.kie.ai"
UPLOAD = "https://kieai.redpandaai.co"
CATALOG_TTL = 6 * 3600
SCHEMA_TTL = 24 * 3600
B64_LIMIT = 10 * 1024 * 1024
MAX_UPLOAD = 512 * 1024 * 1024  # ponytail: hard ceiling; raise only with a vendor-confirmed larger limit
JOB_PATH = "/api/v1/jobs/createTask"
UPLOAD_MIMES = ("image/", "video/", "audio/", "application/pdf")


class KieError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


# ---------------------------------------------------------------- transport
class UrllibTransport:
    """request(method, url, headers, body, timeout) -> (http_status, bytes)."""

    def request(self, method, url, headers=None, body=None, timeout=60):
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise KieError("network", "network error: %s" % getattr(e, "reason", e))


# ------------------------------------------------------------ schema helpers
def deref(doc, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise KieError("bad_ref", "unsupported $ref: %r" % (ref,))
    node = doc
    for seg in ref[2:].split("/"):
        # percent-decode, then JSON-pointer unescape; never trim (keys may end in a space)
        seg = urllib.parse.unquote(seg).replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or seg not in node:
            raise KieError("bad_ref", "unresolvable $ref: %s" % ref)
        node = node[seg]
    return node


def resolve(doc, node, seen=()):
    if isinstance(node, list):
        return [resolve(doc, x, seen) for x in node]
    if not isinstance(node, dict):
        return node
    if isinstance(node.get("$ref"), str):
        ref = node["$ref"]
        if ref in seen:
            return {}  # ponytail: recursive schemas collapse to {} (accept anything) at the cycle
        out = resolve(doc, deref(doc, ref), seen + (ref,))
        extra = {k: v for k, v in node.items() if k != "$ref"}
        if extra and isinstance(out, dict):
            out = dict(out, **resolve(doc, extra, seen))
        return out
    return {k: resolve(doc, v, seen) for k, v in node.items()}


def pick_submit(doc):
    """Return (path, method, resolved request-body schema) declared by the schema."""
    paths = doc.get("paths") or {}
    order = sorted(paths, key=lambda p: p != JOB_PATH)  # job path first, else first declared
    for p in order:
        item = resolve(doc, paths[p])
        for m in ("post", "put"):
            op = item.get(m) if isinstance(item, dict) else None
            if isinstance(op, dict):
                body = ((op.get("requestBody") or {}).get("content") or {})
                js = body.get("application/json") or next(iter(body.values()), {})
                return p, m, js.get("schema") or {}
    raise KieError("schema_no_paths", "schema declares no submit path")


def _type_ok(t, v):
    if t == "string":
        return isinstance(v, str)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "array":
        return isinstance(v, list)
    if t == "object":
        return isinstance(v, dict)
    if t == "null":
        return v is None
    return True


def check(s, v, p="input"):
    """Minimal OpenAPI/JSON-schema subset. Returns a list of error strings."""
    errs = []
    if not isinstance(s, dict):
        return errs
    for b in s.get("allOf") or []:
        errs += check(b, v, p)
    for kw in ("oneOf", "anyOf"):
        if kw in s:
            res = [check(b, v, p) for b in s[kw]]
            ok = [i for i, r in enumerate(res) if not r]
            if not ok:
                errs.append("%s: matches none of %d %s branches (%s)" % (
                    p, len(res), kw, " | ".join("branch %d: %s" % (i, "; ".join(r[:2])) for i, r in enumerate(res))))
            elif kw == "oneOf" and isinstance(v, dict):
                allp = set()
                for b in s[kw]:
                    allp |= set((b.get("properties") or {}) if isinstance(b, dict) else {})
                if not any(set(v) & allp <= set((s[kw][i].get("properties") or {})) for i in ok):
                    errs.append("%s: mixes fields across oneOf branches" % p)
    t = s.get("type")
    types = t if isinstance(t, list) else ([t] if t else [])
    if v is None and (s.get("nullable") or "null" in types):
        return errs
    if types and not any(_type_ok(x, v) for x in types):
        errs.append("%s: expected %s, got %s" % (p, "/".join(types), type(v).__name__))
        return errs
    if "enum" in s and v not in s["enum"]:
        errs.append("%s: %r not in enum %s" % (p, v, s["enum"]))
    if isinstance(v, str):
        if "minLength" in s and len(v) < s["minLength"]:
            errs.append("%s: shorter than minLength %s" % (p, s["minLength"]))
        if "maxLength" in s and len(v) > s["maxLength"]:
            errs.append("%s: longer than maxLength %s" % (p, s["maxLength"]))
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in s and v < s["minimum"]:
            errs.append("%s: below minimum %s" % (p, s["minimum"]))
        if "maximum" in s and v > s["maximum"]:
            errs.append("%s: above maximum %s" % (p, s["maximum"]))
    if isinstance(v, dict):
        props = s.get("properties") or {}
        for r in s.get("required") or []:
            if r not in v:
                errs.append("%s: missing required field %r" % (p, r))
        for k, sub in props.items():
            if k in v:
                errs += check(sub, v[k], "%s.%s" % (p, k))
        if s.get("additionalProperties") is False:
            for k in v:
                if k not in props:
                    errs.append("%s: unexpected field %r" % (p, k))
    if isinstance(v, list) and isinstance(s.get("items"), dict):
        for i, x in enumerate(v):
            errs += check(s["items"], x, "%s[%d]" % (p, i))
    return errs


def modality_of(task_types):
    """Output modality from catalog taskType strings such as 'Text to Image'."""
    # ponytail: vocabulary inferred from KIE's examples ('Text to Video'); unknown labels map to 'other'
    for tt in task_types or []:
        out = str(tt).lower().split(" to ")[-1]
        if "image" in out:
            return "image"
        if "video" in out:
            return "video"
        if any(w in out for w in ("music", "audio", "speech", "sound", "song", "voice", "lyrics")):
            return "audio"
    return "other"


def extract_results(resp):
    """-> (urls, result_object). Handles resultUrls and Suno response.data[].audio_url."""
    urls, obj = [], None
    if not isinstance(resp, dict):
        return urls, obj
    ru = resp.get("resultUrls")
    if isinstance(ru, list):
        urls += [u for u in ru if isinstance(u, str)]
    d = resp.get("data")
    if isinstance(d, list):
        urls += [x["audio_url"] for x in d if isinstance(x, dict) and isinstance(x.get("audio_url"), str)]
    if "resultObject" in resp:
        obj = resp["resultObject"]
    return urls, obj


# ------------------------------------------------- registry / limits helpers
FLOOR_PCT, TARGET_PCT, PREFLIGHT_MULT = 80, 95, 1.30
# Owner order 2026-10-05: prompts use 95-100% of a model's max, never below 80%.
KNOWN_DEFAULTS = {"gpt-image": "gpt-image-2-5-sunburst-text-to-image"}  # last-resort default (N43 today)
DEFAULT_CAPS = {"gpt-image": ["Text to Image", "Image to Image"]}
LATEST_TTL = CATALOG_TTL
REGISTRY_STALE_DAYS = 30

_FAMILY_RULES = [  # ordered; first match wins. ponytail: new vendors fall to the generic first-word rule below
    (r"^(gpt-image|4o-image)", "gpt-image"), (r"^bytedance/(v\d|seedance)", "seedance"),
    (r"^(bytedance/)?seedream", "seedream"), (r"^(ai-music-api|suno)", "suno"), (r"^veo", "veo"),
    (r"^google/imagen", "imagen"), (r"^(google/)?nano-banana", "nano-banana"),
    (r"^google/gemini-.*tts", "gemini-tts"), (r"^(google/)?gemini-omni", "gemini-omni"),
    (r"^gemini", "gemini"), (r"^gpt-\d", "gpt-chat"), (r"^claude", "claude"),
    (r"^grok-imagine", "grok-imagine"), (r"^grok", "grok"), (r"^qwen", "qwen"), (r"^kling", "kling"),
    (r"^wan/", "wan"), (r"^(hailuo|minimax)", "hailuo"), (r"^happyhorse", "happyhorse"),
    (r"^pixverse", "pixverse"), (r"^ideogram", "ideogram"), (r"^flux", "flux"), (r"^z-image", "z-image"),
    (r"^elevenlabs", "elevenlabs"), (r"^topaz", "topaz"), (r"^recraft", "recraft"), (r"^runway", "runway"),
    (r"^omnihuman", "omnihuman"), (r"^kimi", "kimi"), (r"^deepseek", "deepseek"),
]
_STOP = {"text", "to", "image", "video", "edit", "editing", "i2i", "t2i", "v2v", "api", "images"}
_VERSION_RE = re.compile(r"(?:^|[/_-]|(?<=[a-z]))v?(\d+(?:[._-]\d+)*)(?=$|[/_-])")


def family_of(model_id):
    mid = (model_id or "").lower()
    for pat, fam in _FAMILY_RULES:
        if re.match(pat, mid):
            return fam
    m = re.match(r"[a-z]+", mid.split("/")[0])
    return m.group(0) if m else "other"


def version_of(model_id):
    """Numeric generation encoded in the id ('2-5' -> [2, 5]), else None."""
    m = _VERSION_RE.search((model_id or "").lower())
    return [int(x) for x in re.split(r"[._-]", m.group(1))] if m else None


def variant_of(model_id):
    """Variant word(s) left after dropping family, version and task words ('sunburst'), else None."""
    mid = (model_id or "").lower()
    fam = family_of(mid)
    m = _VERSION_RE.search(mid)
    rest = mid[:m.start()] + "/" + mid[m.end():] if m else mid
    drop = _STOP | set(re.split(r"[^a-z0-9]+", fam))
    head, _, tail = rest.partition("/")
    if tail and not re.search(r"\d", head) and not set(re.split(r"[^a-z0-9]+", head)) <= drop:
        rest = tail  # provider namespace ('google/', 'bytedance/'), not a variant
    toks = [t for t in re.split(r"[^a-z0-9]+", rest) if t and not t.isdigit() and t not in drop]
    return "-".join(toks) or None


def _vkey(v):
    v = list(v or [])
    while v and v[-1] == 0:
        v.pop()
    return tuple(v)


def parse_pricing(raw):
    """Prose pricingDesc -> {credits_min, credits_max, unit, all}. Numbers are credits only (never USD)."""
    text = raw if isinstance(raw, str) else ""
    nums = [float(x.replace(",", "")) for x in
            re.findall(r"(?i)(\d[\d,]*(?:\.\d+)?)\s*(?:kie\s+)?credits?\b", text)]
    low = text.lower()
    unit = ("per-1m-tokens" if re.search(r"tokens?\b|/\s*1?\s*m\b|per\s+m\b", low) else
            "per-second" if re.search(r"per\s+(?:video\s+)?second|\bper\s+sec\b|1[\s-]second", low) else "per-job")
    return {"credits_min": min(nums) if nums else None, "credits_max": max(nums) if nums else None,
            "unit": unit, "all": nums}


def estimate_credits(parsed, units=1):
    """Conservative (highest listed tier) estimate; per-second and per-1M-token prices scale by units."""
    top = parsed.get("credits_max")
    if top is None:
        return None
    return round(top * (units if parsed.get("unit") != "per-job" else 1), 4)


def preflight_amount(credits):
    """price x 1.30, rounded up to 0.01 credit."""
    return None if credits is None else math.ceil(round(credits * PREFLIGHT_MULT * 100, 6)) / 100.0


def budget(max_chars):
    """Prompt budget from a model max. Integer math: no float rounding surprises."""
    m = int(max_chars)
    return {"max": m, "floor": -(-m * FLOOR_PCT // 100), "target_min": -(-m * TARGET_PCT // 100), "target_max": m}


_LIMIT_RE = re.compile(
    r"(?i)(?:maximum|max\.?|up to|limit(?:ed to)?|exceed|not more than)\b[^0-9.\n]{0,30}?(\d[\d,]*)\s*(?:characters?|chars)\b"
    r"|\b0\s*-\s*(\d[\d,]*)\s*characters")


def described_limits(desc):
    """Character limits stated in a field description ('Maximum 20,000 characters'). Lower confidence than maxLength."""
    out = []
    for m in _LIMIT_RE.finditer(desc if isinstance(desc, str) else ""):
        out.append(int((m.group(1) or m.group(2)).replace(",", "")))
    return out


def _finfo(sub):
    keys = ("type", "format", "minLength", "maxLength", "enum", "minimum", "maximum", "default", "minItems",
            "maxItems", "nullable")
    d = {k: sub[k] for k in keys if k in sub}
    if "maxLength" not in d:
        lims = described_limits(sub.get("description"))
        if lims:  # several distinct figures (per-version tables): record all, pick the most common, flag it
            top = max(set(lims), key=lambda v: (lims.count(v), -v))
            d["maxLength_described"] = top
            if len(set(lims)) > 1:
                d["described_limits"] = sorted(set(lims))
    if isinstance(sub.get("items"), dict):
        d["items"] = _finfo(sub["items"])
    if isinstance(sub.get("properties"), dict):
        d["properties"] = {k: _finfo(v) for k, v in sub["properties"].items() if isinstance(v, dict)}
        if sub.get("required"):
            d["required"] = list(sub["required"])
    for kw in ("oneOf", "anyOf"):
        if isinstance(sub.get(kw), list):
            d[kw] = [_finfo(b) for b in sub[kw] if isinstance(b, dict)]
    return d


def flatten_input(s):
    """Resolved input schema -> (fields{name: info}, required[], branches[{required, fields}]).
    allOf is merged; oneOf/anyOf branches are kept whole (each carries its own limits)."""
    fields, req, branches = {}, set(s.get("required") or []) if isinstance(s, dict) else set(), []
    if not isinstance(s, dict):
        return fields, [], branches
    for k, sub in (s.get("properties") or {}).items():
        if isinstance(sub, dict):
            fields[k] = _finfo(sub)
    for b in s.get("allOf") or []:
        f, r, br = flatten_input(b)
        fields.update(f), req.update(r), branches.extend(br)
    for kw in ("oneOf", "anyOf"):
        for b in s.get(kw) or []:
            f, r, _ = flatten_input(b)
            branches.append({"required": sorted(r), "fields": f})
            for k, v in f.items():
                fields.setdefault(k, v)  # first-seen; the branch keeps its own copy
    return fields, sorted(req), branches


_VERBATIM_ALWAYS = {"lyrics", "lyric", "dialogue", "dialogue_turns", "script", "speech_text"}
_SPEECH_RE = re.compile(r"(?:tts|text-to-speech|dialogue)")


def verbatim_fields(model_id, fields, task_types=()):
    """Fields spoken or sung exactly (TTS text, lyrics). Suno: with a style field, prompt is the lyrics."""
    mid = (model_id or "").lower()
    speech = bool(_SPEECH_RE.search(mid)) or any("speech" in str(t).lower() for t in task_types or [])
    out = [k for k in fields if k.lower() in _VERBATIM_ALWAYS or (speech and k.lower() == "text")]
    if family_of(mid) == "suno" and "prompt" in fields and "style" in fields:
        out.append("prompt")
    return sorted(set(out))


def _field_max(info):
    """-> (max, how, listed): schema maxLength, else per-turn text maxLength of an array of turns, else the described figure."""
    if "maxLength" in info:
        return info["maxLength"], "schema", []
    turn = ((info.get("items") or {}).get("properties") or {}).get("text") or {}
    if "maxLength" in turn:
        return turn["maxLength"], "schema-per-turn", []
    if "maxLength_described" in info:
        return info["maxLength_described"], "description", info.get("described_limits") or []
    return None, None, []


def prompt_field_of(model_id, fields, task_types=()):
    """-> {name, maxLength, verbatim, max_source, limits_listed}. The descriptive prompt field wins; a
    verbatim field is returned (verbatim=True, no floor) only when the model has no descriptive one."""
    verb = verbatim_fields(model_id, fields, task_types)
    pick = None
    if family_of(model_id) == "suno" and "style" in fields:
        pick = "style"
    else:
        pick = next((n for n in ("prompt", "text_prompt", "description", "content", "instruction")
                     if n in fields and n not in verb), None)
    v = False
    if pick is None and verb:
        pick, v = verb[0], True
    if pick is None:
        return {"name": None, "maxLength": None, "verbatim": False, "max_source": None, "limits_listed": []}
    mx, how, listed = _field_max(fields[pick])
    return {"name": pick, "maxLength": mx, "verbatim": v, "max_source": how, "limits_listed": listed}


def registry_input_schema(entry):
    """Rebuild a checkable schema from a registry entry (used when the live schema is unreachable)."""
    s = {"type": "object", "required": list(entry.get("required") or []),
         "properties": dict(entry.get("input_fields") or {})}
    if entry.get("branches"):
        s["oneOf"] = [{"type": "object", "required": b.get("required") or [], "properties": b.get("fields") or {}}
                      for b in entry["branches"]]
    return s


def policy_limit(model_id, here=None):
    """Policy-owner prompt limit from sibling skills 66/67/68. -> (max|None, owner|None, owner_confirmed)."""
    here = here or os.path.dirname(os.path.abspath(__file__))
    roots = [os.path.join(here, "..", ".."), os.environ.get("OPENCLAW_SKILLS_DIR") or "",
             os.path.join(os.path.expanduser("~"), ".openclaw", "skills"), "/data/.openclaw/skills"]
    if os.environ.get("KIE_POLICY_ROOT") is not None:  # test hook: look only here (empty = no policy owners)
        roots = [os.environ["KIE_POLICY_ROOT"]]
    for owner, alt in (("66-kie-image", "kie-image"), ("67-kie-video", "kie-video"), ("68-kie-audio", "kie-audio")):
        for r in roots:
            for name in (owner, alt):
                p = os.path.join(r, name, "models.json")
                if not (r and os.path.isfile(p)):
                    continue
                try:
                    with open(p) as f:
                        d = json.load(f)
                except (OSError, ValueError):
                    continue
                for e in d.get("models") or d.get("entries") or []:
                    if e.get("canonical_model_id") != model_id:
                        continue
                    if isinstance(e.get("owner_observed_cap_chars"), int):  # N43: owner-confirmed beats stale docs
                        return e["owner_observed_cap_chars"], owner, True
                    if isinstance(e.get("vendor_hard_cap_chars"), int):
                        return e["vendor_hard_cap_chars"], owner, False
                    caps = e.get("caps") or {}
                    for k in ("text_max_chars", "per_turn_text_max_chars", "combined_text_max_chars", "prompt_max_chars"):
                        if isinstance(caps.get(k), int):
                            return caps[k], owner, False
                    return None, None, False
                break
    return None, None, False


# ------------------------------------------------------------------ adapter
def _repo_resolver():
    """Locate shared-utils/key_resolver.py (repo checkout or installed skills tree)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (os.path.join(here, "..", "..", "shared-utils"),
              os.path.join(os.environ.get("OPENCLAW_SKILLS_DIR", ""), "shared-utils"),
              os.path.join(os.path.expanduser("~"), ".openclaw", "skills", "shared-utils")):
        if os.path.isfile(os.path.join(d, "key_resolver.py")):
            sys.path.insert(0, os.path.abspath(d))
            try:
                from key_resolver import resolve_key
                return resolve_key
            except Exception:  # ponytail: any resolver failure falls back to env-only
                return None
    return None


class Adapter:
    def __init__(self, env=None, transport=None, sleep=time.sleep, now=time.time, resolver=None):
        live = env is None
        self.env = dict(os.environ if live else env)
        self.t = transport or UrllibTransport()
        self.sleep, self.now = sleep, now
        self.warnings = []
        home = self.env.get("HOME") or os.path.expanduser("~")
        # Key: the live environment first, then the repo's shared resolver (secret_names.json canon,
        # placeholder rejection). Aliases are never restated here. Injected env dicts (tests) skip it.
        self.key = self.env.get("KIE_API_KEY", "")
        if not self.key:
            res = resolver if resolver else (_repo_resolver() if live else None)
            self.key = (res("kie") if res else None) or ""
        # Mode precedence: env, then $OC_CONFIG/kie-live-adapter-mode.conf (one word, same store
        # convention as decision-engine-mode.conf; read-only here), then shadow.
        m = self.env.get("KIE_LIVE_ADAPTER_MODE", "").strip().lower()
        if not m:
            oc = self.env.get("OC_CONFIG") or os.path.join(home, ".openclaw")
            oc = os.path.dirname(oc) if oc.endswith(".json") else oc
            try:
                with open(os.path.join(oc, "kie-live-adapter-mode.conf")) as f:
                    m = (f.readline().strip().lower())
            except OSError:
                m = ""
        m = m or "shadow"
        if m not in ("off", "shadow", "active"):
            self.warnings.append("unknown adapter mode %r; using shadow" % m)
            m = "shadow"
        self.mode = m
        self.cache = self.env.get("KIE_LIVE_CACHE_DIR") or os.path.join(home, ".openclaw", "cache", "kie-live-adapter")
        self.rdir = self.env.get("KIE_LIVE_RECEIPT_DIR") or os.path.join(self.cache, "receipts")
        self.spacing = float(self.env.get("KIE_LIVE_MIN_SPACING", "1.1"))
        self.poll0 = float(self.env.get("KIE_LIVE_POLL_INITIAL", "3"))
        self.api = self._base("KIE_LIVE_API_BASE", API)
        self.upl = self._base("KIE_LIVE_UPLOAD_BASE", UPLOAD)
        self._reg = None

    def _base(self, name, default):
        v = self.env.get(name)
        if not v:
            return default
        host = urllib.parse.urlparse(v).hostname
        if host not in ("127.0.0.1", "localhost"):  # test hook only: never send the key to another host
            raise KieError("bad_base", "%s may only point at localhost" % name)
        return v.rstrip("/")

    # -- redaction / results
    def redact(self, s):
        s = s if isinstance(s, str) else str(s)
        if self.key:
            s = s.replace(self.key, "[REDACTED]")
        return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", s)

    def result(self, **kw):
        r = {"provider": "kie", "adapter": ADAPTER, "adapter_mode": self.mode, "backend": "native-live",
             "model_id": None, "capability": None, "schema_source": None, "schema_fetched_at": None,
             "task_id": None, "state": "success", "result_urls": [], "saved_paths": [],
             "credits_consumed": None, "warnings": [], "fallback_used": False, "raw_family": "other",
             "error": None, "data": {}}
        r.update(kw)
        r["warnings"] = list(self.warnings) + list(r["warnings"])
        return r

    def fail(self, e, **kw):
        return self.result(state="fail", error={"code": e.code, "msg": self.redact(e.msg)}, **kw)

    # -- cache files
    def _cpath(self, *p):
        return os.path.join(self.cache, *p)

    def _read(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _write(self, path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.%s.tmp" % (path, uuid.uuid4().hex[:8])
        with open(tmp, "w") as f:
            json.dump(obj, f)
        os.replace(tmp, path)

    def receipt(self, event, **fields):
        rec = dict(fields, ts=int(self.now()), event=event)
        day = time.strftime("%Y%m%d", time.gmtime(self.now()))
        os.makedirs(self.rdir, exist_ok=True)
        with open(os.path.join(self.rdir, day + ".jsonl"), "a") as f:
            f.write(self.redact(json.dumps(rec, sort_keys=True)) + "\n")

    def _drift(self, kind, name, digest):
        """Compare against the last digest seen; returns True/False/None(first sight)."""
        sp = self._cpath("state.json")
        st = self._read(sp) or {}
        old = st.get(kind, {}).get(name)
        st.setdefault(kind, {})[name] = digest
        self._write(sp, st)
        return None if old is None else old != digest

    # -- HTTP
    def call(self, method, url, body=None, headers=None, discovery=False, retry=True, timeout=60):
        if not self.key:
            raise KieError("no_key", "KIE_API_KEY is not set")
        h = {"Authorization": "Bearer " + self.key}  # Bearer only; a header named apikey gets 401
        h.update(headers or {})
        data = None
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                data = bytes(body)
            else:
                data = json.dumps(body).encode()
                h.setdefault("Content-Type", "application/json")
        for attempt in range(3):
            if discovery:
                self._pace()
            status, raw = self.t.request(method, url, h, data, timeout)
            try:
                j = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                raise KieError("bad_response", "HTTP %s with non-JSON body" % status)
            code = j.get("code", status) if isinstance(j, dict) else status
            if code == 429 and retry and attempt < 2:  # rejected requests never enter the queue, safe to retry
                self.sleep(1.2 * (attempt + 1))
                continue
            if code != 200:  # HTTP 200 can carry 401/402/404/422/429/433/455
                raise KieError(code, self.redact(str(j.get("msg") if isinstance(j, dict) else raw[:200])))
            return j
        raise KieError(429, "rate limited")

    def _pace(self):
        p = self._cpath("last_discovery")
        try:
            with open(p) as f:
                last = float(f.read())
        except (OSError, ValueError):
            last = 0.0
        wait = last + self.spacing - self.now()
        if wait > 0:
            self.sleep(wait)
        os.makedirs(self.cache, exist_ok=True)
        with open(p, "w") as f:
            f.write(repr(self.now()))

    # -- discovery
    def catalog(self):
        p = self._cpath("catalog.json")
        c = self._read(p)
        if c and self.now() - c.get("fetched_at", 0) < CATALOG_TTL:
            return c["models"], c["fetched_at"], "cache"
        j = self.call("GET", self.api + "/api/v1/models", discovery=True)
        models = ((j.get("data") or {}).get("models")) or []
        fetched = self.now()
        self._write(p, {"fetched_at": fetched, "models": models})
        return models, fetched, "live"

    def cmd_discover(self, modality="any", query=None, provider=None, task_type=None, limit=50):
        models, fetched, src = self.catalog()
        out = []
        for m in models:  # one unfiltered fetch, filter locally (shared 1 req/s budget)
            tt = m.get("taskType") or []
            if modality != "any" and modality_of(tt) != modality:
                continue
            if provider and (m.get("provider") or "").lower() != provider.lower():
                continue
            if task_type and not any(task_type.lower() == str(x).lower() for x in tt):
                continue
            if query:
                hay = " ".join(str(m.get(k) or "") for k in ("model", "title", "provider", "description")).lower()
                if query.lower() not in hay:
                    continue
            out.append({k: m.get(k) for k in ("model", "title", "provider", "taskType", "pricingDesc")})
        digest = hashlib.sha256(json.dumps(sorted(x.get("model", "") for x in models)).encode()).hexdigest()
        drift = self._drift("catalog", "all", digest)
        self.receipt("catalog", total=len(models), digest=digest, drift=drift, source=src)
        w = ["catalog model list changed since last receipt"] if drift else []
        return self.result(capability=modality, schema_source="catalog:" + src, schema_fetched_at=fetched,
                           warnings=w, data={"total": len(models), "matched": len(out), "models": out[:limit]})

    def schema(self, model):
        safe = hashlib.sha256(model.encode()).hexdigest()[:24]
        p = self._cpath("schema", safe + ".json")
        c = self._read(p)
        if c and self.now() - c.get("fetched_at", 0) < SCHEMA_TTL:
            return c["openapi"], c["fetched_at"], "cache"
        # slash in the model name is NOT encoded (vendor rule 4)
        j = self.call("GET", "%s/api/v1/models/%s/schema" % (self.api, urllib.parse.quote(model, safe="/")), discovery=True)
        oa = (j.get("data") or {}).get("openapi")
        if not oa:
            raise KieError("schema_not_synced", "schema not synced for %s (openapi is null); not inventing a call path" % model)
        fetched = self.now()
        self._write(p, {"fetched_at": fetched, "openapi": oa})
        return oa, fetched, "live"

    def _capability(self, model):
        c = self._read(self._cpath("catalog.json")) or {}
        for m in c.get("models", []):
            if m.get("model") == model:
                return ", ".join(m.get("taskType") or []) or None
        return None

    def _family(self, path):
        return "market" if path == JOB_PATH else "sync" if path else "other"

    def _load(self, model):
        oa, fetched, src = self.schema(model)
        path, method, body = pick_submit(oa)
        digest = hashlib.sha256(json.dumps(oa, sort_keys=True).encode()).hexdigest()
        drift = self._drift("schema", model, digest)
        base = dict(model_id=model, capability=self._capability(model), schema_source="schema:" + src,
                    schema_fetched_at=fetched, raw_family=self._family(path))
        return oa, path, method, body, digest, drift, base

    def input_schema(self, path, body):
        if path == JOB_PATH:
            return ((body.get("properties") or {}).get("input")) or {}
        return body

    def cmd_schema(self, model):
        try:
            oa, path, method, body, digest, drift, base = self._load(model)
        except KieError as e:
            return self.fail(e, model_id=model)
        self.receipt("schema", model=model, digest=digest, drift=drift, path=path)
        w = ["schema changed since last receipt"] if drift else []
        return self.result(warnings=w, data={"path": path, "method": method, "digest": digest,
                                             "input_schema": self.input_schema(path, body)}, **base)

    def validate(self, model, payload):
        oa, path, method, body, digest, drift, base = self._load(model)
        if path != JOB_PATH and isinstance(payload, dict):
            payload = dict(payload, **{"model": payload.get("model", model)})  # sync bodies carry model inside
        errs = check(self.input_schema(path, body), payload, "input" if path == JOB_PATH else "body")
        self.receipt("validate", model=model, digest=digest, drift=drift, errors=errs)
        return errs, path, method, digest, drift, base

    # -- registry snapshot (references/kie-model-registry.json; generated by scripts/build_model_registry.py)
    def registry(self):
        if self._reg is None:
            p = self.env.get("KIE_LIVE_REGISTRY") or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "references", "kie-model-registry.json")
            d = self._read(p) or {}
            self._reg = (d, {m.get("id"): m for m in d.get("models", []) if isinstance(m, dict)})
        return self._reg

    def reg_entry(self, model):
        return self.registry()[1].get(model)

    def _reg_note(self):
        d = self.registry()[0]
        gen = d.get("generated_at")
        w = ["using registry snapshot generated_at=%s source=%s" % (gen, d.get("source"))]
        try:
            age = (self.now() - time.mktime(time.strptime(gen[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
            if age > REGISTRY_STALE_DAYS:
                w.append("registry snapshot is %d days old; rebuild with scripts/build_model_registry.py" % age)
        except (TypeError, ValueError):
            pass
        return w

    def _validate_registry(self, model, payload, live_err):
        ent = self.reg_entry(model)
        if not ent or not (ent.get("input_fields") or ent.get("branches")):
            return self.fail(live_err, model_id=model)
        kind = ((ent.get("schema_paths") or [{}])[0]).get("kind")
        if kind == "sync" and isinstance(payload, dict):
            payload = dict(payload, **{"model": payload.get("model", model)})
        errs = check(registry_input_schema(ent), payload, "body" if kind == "sync" else "input")
        self.receipt("validate", model=model, source="registry", errors=errs)
        w = ["live schema unavailable (%s: %s); validated against the registry snapshot" % (
            live_err.code, self.redact(live_err.msg))] + self._reg_note()
        base = dict(model_id=model, capability=", ".join(ent.get("taskType") or []) or None,
                    schema_source="registry", raw_family="sync" if kind == "sync" else "market")
        d = {"valid": not errs, "errors": errs, "source": "registry"}
        if errs:
            return self.result(state="fail", error={"code": "validation_failed", "msg": "; ".join(errs)[:500]},
                               warnings=w, data=d, **base)
        return self.result(state="validated", warnings=w, data=d, **base)

    def cmd_validate(self, model, payload):
        try:
            errs, path, method, digest, drift, base = self.validate(model, payload)
        except KieError as e:
            return self._validate_registry(model, payload, e)
        d = {"valid": not errs, "errors": errs, "path": path, "method": method}
        w = ["schema changed since last receipt"] if drift else []
        if errs:
            return self.result(state="fail", error={"code": "validation_failed", "msg": "; ".join(errs)[:500]},
                               warnings=w, data=d, **base)
        return self.result(state="validated", warnings=w, data=d, **base)

    # -- submit
    def _cb_check(self, req):
        cb = req.get("callBackUrl") if isinstance(req, dict) else None
        if cb is not None and (not isinstance(cb, str) or urllib.parse.urlparse(cb).scheme not in ("http", "https")):
            raise KieError("bad_request", "callBackUrl must be an http(s) URL (Skill 46 relay)")
        return cb

    def _record_cb(self, r, cb):
        if cb:  # callBackUrl passthrough (Skill 46): sent on createTask only; sync endpoints have no callback
            r["data"]["callback_url"] = cb
            r["data"]["callback_sent"] = bool(r.get("task_id")) and r.get("raw_family") == "market"
            if r.get("raw_family") == "sync":
                r["warnings"].append("callBackUrl is not supported on synchronous endpoints; not sent")
        return r

    def cmd_submit(self, req, dry_run=False):
        try:
            cb = self._cb_check(req)
        except KieError as e:
            return self.fail(e)
        return self._record_cb(self._submit(req, dry_run), cb)

    def _submit(self, req, dry_run=False):
        model, inp = req.get("model"), req.get("input")
        if not isinstance(model, str) or not model or not isinstance(inp, dict):
            return self.fail(KieError("bad_request", "request needs string 'model' and object 'input'"))
        if not dry_run and self.mode == "off":
            return self.result(state="skipped", model_id=model, fallback_used=False,
                               warnings=["adapter off: use static path"])
        try:
            errs, path, method, digest, drift, base = self.validate(model, inp)
        except KieError as e:
            if not dry_run and self.mode == "shadow":  # diagnostics only; never block the static path
                return self.result(state="skipped", model_id=model, fallback_used=True,
                                   warnings=["shadow: dispatch via existing static path",
                                             "shadow validation unavailable: %s" % self.redact(e.msg)])
            return self.fail(e, model_id=model)
        if errs:
            return self.result(state="fail", error={"code": "validation_failed", "msg": "; ".join(errs)[:500]},
                               data={"valid": False, "errors": errs, "path": path}, **base)
        if dry_run:
            return self.result(state="validated", data={"valid": True, "errors": [], "dry_run": True,
                                                        "path": path, "method": method}, **base)
        if self.mode == "shadow":
            return self.result(state="skipped", fallback_used=True,
                               warnings=["shadow: dispatch via existing static path"],
                               data={"valid": True, "path": path}, **base)
        try:
            return self._dispatch(req, model, inp, path, method, base)
        except KieError as e:
            return self.fail(e, **base)

    def _dispatch(self, req, model, inp, path, method, base):
        if path == JOB_PATH:
            body = {"model": model, "input": inp}
            if req.get("callBackUrl"):
                body["callBackUrl"] = req["callBackUrl"]
            # createTask: retried only on body code 429 (never queued); a network error is NOT retried (double-charge risk)
            j = self.call("POST", self.api + path, body)
            tid = (j.get("data") or {}).get("taskId")
            if not tid:
                raise KieError("bad_response", "createTask returned no taskId")
            return self.result(state="queued", task_id=tid, **base)
        body = dict(inp)  # sync path: schema-declared path and body; model added only if absent
        body.setdefault("model", model)
        j = self.call("POST", self.api + path, body, timeout=300)
        return self.result(state="success", data={"response": j.get("data", j)},
                           warnings=["sync endpoint: result is in data.response; no task to poll"], **base)

    # -- polling
    def _info(self, task_id):
        j = self.call("GET", "%s/api/v1/jobs/recordInfo?taskId=%s" % (self.api, urllib.parse.quote(task_id)))
        return j.get("data") or {}

    def _norm(self, d, task_id):
        st = d.get("state")
        resp = d.get("response")
        if not isinstance(resp, dict) and isinstance(d.get("resultJson"), str):
            try:
                resp = json.loads(d["resultJson"])
            except ValueError:
                resp = None
        urls, obj = extract_results(resp)
        state = {"success": "success", "fail": "fail", "generating": "running"}.get(st, "queued")
        kw = dict(task_id=task_id, state=state, result_urls=urls, raw_family="market",
                  model_id=d.get("model"), credits_consumed=d.get("creditsConsumed"),
                  data={"result_object": obj, "state_raw": st, "cost_time": d.get("costTime")})
        if state == "fail":
            kw["error"] = {"code": d.get("failCode"), "msg": self.redact(str(d.get("failMsg")))}
        if state == "success" and not urls and obj is None:
            kw["warnings"] = ["success but no recognized result URLs; inspect data"]
        return kw

    def cmd_wait(self, task_id, timeout=300, initial=0.0):
        deadline = self.now() + timeout
        delay, bad = self.poll0, 0
        if initial:
            self.sleep(initial)
        while True:
            try:
                kw = self._norm(self._info(task_id), task_id)
                bad = 0
            except KieError as e:
                bad += 1
                if e.code not in ("network", 429) or bad > 3:
                    return self.fail(e, task_id=task_id)
                kw = None
            if kw and kw["state"] in ("success", "fail"):
                return self.result(**kw)
            if self.now() + delay >= deadline:
                kw = kw or {"task_id": task_id, "state": "running"}
                kw["error"] = {"code": "timeout", "msg": "deadline %ss reached; task may still finish, call wait again" % timeout}
                return self.result(**kw)
            self.sleep(delay)
            delay = min(delay * 1.5, 15.0)  # ponytail: simple geometric backoff, capped at 15s

    # -- download
    def _download(self, url, dest_dir, task_id, i):
        if urllib.parse.urlparse(url).scheme != "https" and self.api == API:  # http only when the localhost test base is set
            raise KieError("bad_url", "refusing non-https result URL")
        status, raw = self.t.request("GET", url, {}, None, 120)  # no Authorization: result hosts are not the API
        if status in (403, 404, 410):  # expired: refresh once through download-url
            j = self.call("POST", self.api + "/api/v1/common/download-url", {"url": url})
            fresh = j.get("data")
            if not isinstance(fresh, str):
                raise KieError("bad_response", "download-url returned no link")
            status, raw = self.t.request("GET", fresh, {}, None, 120)
        if status != 200 or not raw:
            raise KieError("download_failed", "download failed with HTTP %s" % status)
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1]
        ext = ext if re.fullmatch(r"\.[A-Za-z0-9]{1,5}", ext or "") else ".bin"
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, "%s_%d%s" % (re.sub(r"[^A-Za-z0-9_-]", "", task_id)[:40], i, ext))
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            f.write(raw)  # ponytail: whole file in memory; stream to disk if clips exceed a few hundred MB
        os.replace(tmp, dest)
        return os.path.realpath(dest)

    def cmd_save(self, task_id, save_dir, info=None):
        try:
            kw = self._norm(self._info(task_id), task_id) if info is None else info
            if kw["state"] != "success":
                return self.result(**dict(kw, warnings=["task not successful; nothing to save"]))
            kw["saved_paths"] = [self._download(u, save_dir, task_id, i) for i, u in enumerate(kw["result_urls"])]
            return self.result(**kw)
        except KieError as e:
            return self.fail(e, task_id=task_id)

    def cmd_run(self, req, save_dir, timeout=None):
        try:
            cb = self._cb_check(req)
        except KieError as e:
            return self.fail(e)
        r = self._record_cb(self._run(req, save_dir, timeout), cb)
        return r

    def _run(self, req, save_dir, timeout=None):
        r = self._submit(req)
        if r["state"] != "queued":
            return r
        t = req.get("timeout") or timeout or 300
        w = self.cmd_wait(r["task_id"], t, initial=self.poll0)
        w["capability"], w["schema_source"], w["schema_fetched_at"] = r["capability"], r["schema_source"], r["schema_fetched_at"]
        w["model_id"] = r["model_id"]
        if w["state"] != "success":
            return w
        kw = {k: w[k] for k in ("task_id", "state", "result_urls", "credits_consumed", "raw_family", "model_id",
                                "capability", "schema_source", "schema_fetched_at", "data", "warnings")}
        kw["warnings"] = [x for x in kw["warnings"] if x not in self.warnings]
        return self.cmd_save(w["task_id"], save_dir, info=kw)

    # -- upload
    def cmd_upload(self, file=None, url=None, upload_path="openclaw/uploads"):
        up = (upload_path or "").strip("/")
        if not up:
            return self.fail(KieError("bad_request", "uploadPath required"))
        try:
            if url:
                if urllib.parse.urlparse(url).scheme not in ("http", "https"):
                    raise KieError("bad_request", "--url must be http(s)")
                j = self.call("POST", self.upl + "/api/file-url-upload", {"fileUrl": url, "uploadPath": up}, timeout=60)
                method = "url"
            else:
                real = os.path.realpath(file or "")
                if not (os.path.isfile(real) and os.access(real, os.R_OK)):
                    raise KieError("bad_file", "not a readable regular file")
                size = os.path.getsize(real)
                mime = mimetypes.guess_type(real)[0]
                if size == 0 or size > MAX_UPLOAD:
                    raise KieError("bad_file", "file size %d outside 1..%d bytes" % (size, MAX_UPLOAD))
                if not mime or not mime.startswith(UPLOAD_MIMES):
                    raise KieError("bad_file", "unsupported mime %r" % mime)
                name = os.path.basename(real)
                with open(real, "rb") as f:
                    blob = f.read()
                if size <= B64_LIMIT:
                    method = "base64"
                    j = self.call("POST", self.upl + "/api/file-base64-upload", {
                        "base64Data": "data:%s;base64,%s" % (mime, base64.b64encode(blob).decode()),
                        "uploadPath": up, "fileName": name})
                else:
                    method = "stream"
                    b = uuid.uuid4().hex
                    parts = b"".join(
                        ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, k, v)).encode()
                        for k, v in (("uploadPath", up), ("fileName", name)))
                    parts += ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
                              "Content-Type: %s\r\n\r\n" % (b, name.replace('"', ""), mime)).encode() + blob + \
                        ("\r\n--%s--\r\n" % b).encode()
                    j = self.call("POST", self.upl + "/api/file-stream-upload", parts,
                                  headers={"Content-Type": "multipart/form-data; boundary=" + b}, timeout=600)
            d = j.get("data") or {}
            if not d.get("downloadUrl"):
                raise KieError("bad_response", "upload returned no downloadUrl")
            w = []
            if "expiresAt" not in d:
                w.append("no expiresAt returned; assume 24h (docs say 24h in one place, 3 days in another)")
            return self.result(warnings=w, data={"download_url": d["downloadUrl"], "upload_method": method,
                                                 "expires_at": d.get("expiresAt"), "file_name": d.get("fileName"),
                                                 "file_size": d.get("fileSize")})
        except KieError as e:
            return self.fail(e)

    # -- price / preflight (one price authority: live catalog pricingDesc, registry snapshot as fallback)
    def _price_text(self, model):
        """-> (pricing_desc|None, source, warnings)."""
        try:
            models, fetched, src = self.catalog()
            for m in models:
                if m.get("model") == model:
                    return m.get("pricingDesc"), "catalog:" + src, []
            live_note = ["model not in the live catalog"]
        except KieError as e:
            live_note = ["live catalog unavailable (%s: %s)" % (e.code, self.redact(e.msg))]
        ent = self.reg_entry(model)
        if ent:
            pr = ent.get("pricing") or {}
            return pr.get("raw"), "registry", live_note + self._reg_note()
        return None, "none", live_note

    def cmd_price(self, model, units=1):
        raw, src, w = self._price_text(model)
        if src == "none":
            return self.fail(KieError("price_unavailable", "no live catalog entry and no registry entry for %s" % model),
                             model_id=model, warnings=w)
        parsed = parse_pricing(raw)
        est = estimate_credits(parsed, units)
        if est is None:
            w = w + ["pricing text has no credit figure; no estimate (price source: %s)" % src]
        elif parsed["unit"] != "per-job":
            w = w + ["price is %s; estimate = highest listed rate x units (%s)" % (parsed["unit"], units)]
        d = {"pricing_desc": raw, "credits_min": parsed["credits_min"], "credits_max": parsed["credits_max"],
             "unit": parsed["unit"], "units": units, "credits_estimate": est,
             "preflight_required": preflight_amount(est), "preflight_multiplier": PREFLIGHT_MULT, "price_source": src}
        return self.result(model_id=model, schema_source=src, warnings=w, data=d)

    def cmd_preflight(self, model, units=1):
        p = self.cmd_price(model, units)
        if p["state"] == "fail":
            return p
        need = p["data"]["preflight_required"]
        if need is None:
            return self.fail(KieError("price_unestimable", "no numeric price for %s; cannot preflight" % model),
                             model_id=model, warnings=p["warnings"], data=p["data"])
        try:
            bal = self.call("GET", self.api + "/api/v1/chat/credit").get("data")
        except KieError as e:
            return self.fail(e, model_id=model, warnings=p["warnings"], data=p["data"])
        if not isinstance(bal, (int, float)) or isinstance(bal, bool):
            return self.fail(KieError("bad_response", "credit balance is not a number"), model_id=model, data=p["data"])
        short = max(0.0, round(need - bal, 2))
        d = dict(p["data"], balance=bal, required=need, ok=short == 0, shortfall=short)
        if short:
            return self.result(state="fail", model_id=model, warnings=p["warnings"], data=d,
                               error={"code": "insufficient_credits",
                                      "msg": "balance %s is short by %s credits (required %s = price x %s)" % (
                                          bal, short, need, PREFLIGHT_MULT)})
        return self.result(state="validated", model_id=model, warnings=p["warnings"], data=d)

    # -- success rate (shared 1 req/s discovery budget)
    def success_rate(self, model):
        j = self.call("GET", "%s/api/v1/models/%s/success-rate" % (self.api, urllib.parse.quote(model, safe="/")),
                      discovery=True)
        d = j.get("data") or {}
        pts = d.get("points") if isinstance(d, dict) else None
        pts = pts if isinstance(pts, list) else []
        rates = [p["successRate"] for p in pts if isinstance(p, dict) and isinstance(p.get("successRate"), (int, float))]
        return {"points": len(pts), "samples": len(rates),
                "avg_success_rate": round(sum(rates) / len(rates), 2) if rates else None,
                "last_success_rate": rates[-1] if rates else None,
                "all_normal": all(p.get("isNormal") is not False for p in pts if isinstance(p, dict)) if pts else None}

    def cmd_success_rate(self, model):
        try:
            d = self.success_rate(model)
        except KieError as e:
            return self.fail(e, model_id=model)
        w = [] if d["samples"] else ["no monitoring data in the last 24 hours (not the same as 0 percent)"]
        return self.result(model_id=model, warnings=w, data=d)

    # -- prompt budget (owner order 2026-10-05: 95-100 percent of max, never below 80 percent)
    def _limits(self, model):
        """Live schema first, registry fallback, policy owner (66/67/68) for what the schema does not state."""
        notes, pf = [], {"name": None, "maxLength": None, "verbatim": False, "max_source": None, "limits_listed": []}
        src = "none"
        try:
            oa, fetched, ssrc = self.schema(model)
            path, method, body = pick_submit(oa)
            fields, _, _ = flatten_input(self.input_schema(path, body))
            pf, src = prompt_field_of(model, fields, self._task_types(model)), "live-schema:" + ssrc
        except KieError as e:
            notes.append("live schema unavailable (%s: %s)" % (e.code, self.redact(e.msg)))
            ent = self.reg_entry(model)
            if ent and isinstance(ent.get("prompt_field"), dict):
                pf, src = dict(pf, **ent["prompt_field"]), "registry"
                notes += self._reg_note()
        mx, how = pf.get("maxLength"), pf.get("max_source")
        pol, owner, confirmed = policy_limit(model)
        if pf.get("name") is not None and pol:
            if confirmed and how != "schema":
                notes.append("owner-confirmed limit %s from %s used over %s" % (pol, owner, how or "no stated limit"))
                mx, src = pol, "policy-owner:%s (owner-confirmed)" % owner
            elif mx is None:
                mx, src = pol, "policy-owner:%s" % owner
            elif pol != mx:
                notes.append("policy owner %s records %s; %s says %s; using %s" % (owner, pol, src, mx, mx))
        if how == "description" and src.startswith(("live", "registry")):
            src += " (stated in the field description, not a schema maxLength)"
        if pf.get("limits_listed"):
            notes.append("description lists several limits %s (per-version table); using the most common %s" % (
                pf["limits_listed"], pf.get("maxLength")))
        return {"field": pf.get("name"), "max": mx, "verbatim": bool(pf.get("verbatim")), "source": src, "notes": notes}

    def _task_types(self, model):
        c = self._read(self._cpath("catalog.json")) or {}
        for m in c.get("models", []):
            if m.get("model") == model:
                return m.get("taskType") or []
        ent = self.reg_entry(model)
        return (ent or {}).get("taskType") or []

    def cmd_prompt_budget(self, model, check=False, prompt_text=None):
        lim = self._limits(model)
        mx, verb = lim["max"], lim["verbatim"]
        d = {"field": lim["field"], "max": mx, "verbatim": verb, "limit_source": lim["source"],
             "floor": None, "target_min": None, "target_max": mx, "status": "OK", "exit_code": 0}
        w = list(lim["notes"])
        if lim["field"] is None:
            d["status"] = "NO_PROMPT_FIELD"
            w.append("no prompt field found for %s; nothing to budget" % model)
        elif mx is None:
            d["status"] = "UNKNOWN"
            w.append("prompt limit UNKNOWN for %s: no schema maxLength and no policy-owner limit; floor not enforced" % model)
        elif verb:
            d["status"] = "VERBATIM"
            w.append("%s is verbatim content (spoken or sung exactly): no floor, ceiling %d applies" % (lim["field"], mx))
        else:
            d.update(budget(mx))
        if check and mx is not None:
            n = len((prompt_text or "").strip())
            pct = round(100.0 * n / mx, 1)
            d.update(chars=n, percent_of_max=pct)
            if n > mx:
                d.update(status="ABOVE_MAX", exit_code=4, cut=n - mx)
            elif not verb and n < d["floor"]:
                d.update(status="BELOW_FLOOR", exit_code=3, add_to_floor=d["floor"] - n, add_to_target=d["target_min"] - n)
            elif not verb and n < d["target_min"]:
                d["status"] = "BELOW_TARGET"
                w.append("prompt is %d chars (%s%% of max); target is 95-100%%: add %d chars to reach %d" % (
                    n, pct, d["target_min"] - n, d["target_min"]))
        d["max_known"] = mx is not None
        if d["exit_code"] == 4:
            return self.result(state="fail", model_id=model, warnings=w, data=d, error={
                "code": "prompt_above_max", "msg": "prompt is %d chars; max is %d; CUT exactly %d chars" % (
                    d["chars"], mx, d["cut"])})
        if d["exit_code"] == 3:
            return self.result(state="fail", model_id=model, warnings=w, data=d, error={
                "code": "prompt_below_floor", "msg": "prompt is %d chars (%s%% of max %d); floor is %d: ADD at least %d chars "
                "(%d to reach the 95%% target of %d)" % (d["chars"], d["percent_of_max"], mx, d["floor"],
                                                       d["add_to_floor"], d["add_to_target"], d["target_min"])})
        return self.result(state="validated", model_id=model, warnings=w, data=d)

    # -- latest generation of a family (owner order 2026-10-05: GPT Image follows the newest generation)
    def _promo_state(self):
        return self._read(self._cpath("promotion-state.json")) or {}

    def _groups(self, entries, caps):
        """entries: [{id, taskType}] -> {(version key, variant): {version, variant, routes{cap: [ids]}}}."""
        groups = {}
        for e in entries:
            v = version_of(e["id"])
            if v is None:
                continue
            g = groups.setdefault((_vkey(v), variant_of(e["id"])),
                                  {"version": v, "variant": variant_of(e["id"]), "routes": {}})
            for tt in e.get("taskType") or []:
                g["routes"].setdefault(tt, []).append(e["id"])
        want = {c.lower() for c in caps}
        out = {}
        for k, g in groups.items():
            have = {t.lower(): t for t in g["routes"]}
            if want and not want <= set(have):
                continue
            order = [c.lower() for c in caps] if caps else sorted(have)  # caller's capability order is stable
            g["routes"] = {have[c]: sorted(g["routes"][have[c]])[0] for c in order}
            out[k] = g
        return out

    def _resolve_latest(self, entries, caps, cur, readable, rank):
        """Newest generation with every capability route readable; variant preference per owner order."""
        notes, groups = [], self._groups(entries, caps)
        cur_var = variant_of(cur) if cur else None
        for vk in sorted({k[0] for k in groups}, reverse=True):
            viable = []
            for k, g in sorted((k, g) for k, g in groups.items() if k[0] == vk):
                bad = [i for i in g["routes"].values() if not readable(i)]
                if bad:
                    notes.append("skipped %s: schema not readable for %s" % ("-".join(map(str, vk)) + (g["variant"] and "/" + g["variant"] or ""), ", ".join(bad)))
                else:
                    viable.append(g)
            if not viable:
                continue
            same = [g for g in viable if g["variant"] == cur_var]
            if same:
                return same[0], "variant-match", notes, viable
            if len(viable) == 1:
                return viable[0], "only-candidate", notes, viable
            rk = {id(g): rank(g) for g in viable}  # one live success-rate read per candidate
            ranked = sorted(viable, key=lambda g: (-rk[id(g)][0], rk[id(g)][1], g["variant"] or ""))
            return ranked[0], ("success-rate" if rk[id(ranked[0])][0] != rk[id(ranked[-1])][0] else "price"), notes, viable
        return None, "none", notes, []

    def cmd_latest_family(self, family, capabilities=None, current=None, refresh=False):
        caps = capabilities or DEFAULT_CAPS.get(family) or []
        st = self._promo_state().get(family) or {}
        cur = current or (st.get("routes") or {}).get(caps[0] if caps else "") or KNOWN_DEFAULTS.get(family)
        key = hashlib.sha256(json.dumps([family, sorted(caps), variant_of(cur) if cur else None]).encode()).hexdigest()[:20]
        cp = self._cpath("latest", key + ".json")
        c = self._read(cp)
        if c and not refresh and self.now() - c.get("fetched_at", 0) < LATEST_TTL:
            return self.result(capability=family, schema_source="latest:cache", schema_fetched_at=c["fetched_at"],
                               warnings=list(c.get("warnings") or []), data=dict(c["data"], source="cache"))
        w, source = [], "live"
        try:
            models, fetched, csrc = self.catalog()
            entries = [{"id": m.get("model"), "taskType": m.get("taskType") or [], "price": m.get("pricingDesc")}
                       for m in models if family_of(m.get("model")) == family]
            readable = lambda i: self._readable(i)
            by_id = {e["id"]: e for e in entries}

            def rank(g):  # live 24h success rate (higher first), then lower price
                i = next(iter(g["routes"].values()))
                try:
                    sr = self.success_rate(i)["avg_success_rate"]
                except KieError:
                    sr = None
                est = estimate_credits(parse_pricing(by_id.get(i, {}).get("price")))
                return (sr if sr is not None else -1.0, est if est is not None else float("inf"))
        except KieError as e:
            w.append("live catalog unavailable (%s: %s); using the registry snapshot" % (e.code, self.redact(e.msg)))
            reg = self.registry()[1]
            if not reg:
                return self.fail(KieError("latest_unavailable", "no live catalog and no registry; caller falls back to its own default"),
                                 warnings=w)
            source, fetched = "registry", None
            w += self._reg_note()
            entries = [{"id": i, "taskType": m.get("taskType") or [], "ok": (m.get("schema") or {}).get("readable")}
                       for i, m in reg.items() if family_of(i) == family]
            ok = {e["id"]: e["ok"] for e in entries}
            readable = lambda i: bool(ok.get(i))

            def rank(g):  # registry has no live success rate: price decides
                raw = ((reg.get(next(iter(g["routes"].values()))) or {}).get("pricing") or {}).get("raw")
                return (-1.0, estimate_credits(parse_pricing(raw)) or float("inf"))
        g, by, notes, viable = self._resolve_latest(entries, caps, cur, readable, rank)
        if g is None:
            return self.fail(KieError("latest_unavailable", "no %s generation has all of %s with a readable schema" % (family, caps or "any")),
                             warnings=w + notes)
        routes = g["routes"]
        first = routes[caps[0]] if caps and caps[0] in routes else next(iter(routes.values()))
        prev = (st.get("routes") or {}).get(caps[0] if caps else "") or KNOWN_DEFAULTS.get(family)
        changed = bool(prev) and first != prev
        d = {"family": family, "version": g["version"], "variant": g["variant"], "routes": routes, "default": first,
             "chosen_by": by, "previous_default": prev, "changed": changed, "source": source,
             "candidates": [{"version": x["version"], "variant": x["variant"], "routes": x["routes"]} for x in viable]}
        if source == "live":
            if changed or not st:
                self._write(self._cpath("promotion-state.json"), dict(self._promo_state(), **{family: {
                    "routes": routes, "at": int(self.now())}}))
            if changed:
                self.receipt("default_promotion", family=family, previous=prev, current=first, routes=routes, chosen_by=by)
                self._write(os.path.join(self.rdir, "promotions", "%s-%d.json" % (family, int(self.now()))),
                            {"family": family, "previous": prev, "current": first, "routes": routes, "chosen_by": by,
                             "ts": int(self.now())})
                w.append("DEFAULT CHANGED for %s: %s -> %s (receipt written; report to the operator)" % (family, prev, first))
            self._write(cp, {"fetched_at": self.now(), "data": d, "warnings": w + notes})
        return self.result(capability=family, schema_source="latest:" + source, schema_fetched_at=fetched,
                           warnings=w + notes, data=d)

    def _readable(self, model):
        try:
            self.schema(model)
            return True
        except KieError:
            return False

    # -- account
    def cmd_credits(self):
        try:
            j = self.call("GET", self.api + "/api/v1/chat/credit")
        except KieError as e:
            return self.fail(e)
        return self.result(data={"credits": j.get("data")})

    def cmd_health(self):
        d = {"key": "SET" if self.key else "NOT-SET", "mode": self.mode, "cache_dir": self.cache}
        if not self.key:
            return self.result(state="fail", error={"code": "no_key", "msg": "KIE_API_KEY is not set"}, data=d)
        try:
            d["credits"] = self.call("GET", self.api + "/api/v1/chat/credit").get("data")
        except KieError as e:
            return self.fail(e, data=d)
        return self.result(data=d)


# --------------------------------------------------------------------- CLI
def _load_json(path):
    with open(path) as f:
        return json.load(f)


def main(argv=None, adapter=None, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="kie_live_adapter.py", description=__doc__.splitlines()[0])
    sp = ap.add_subparsers(dest="cmd", required=True)

    def add(name, *args):
        p = sp.add_parser(name)
        p.add_argument("--json", action="store_true", help="accepted; output is always JSON")
        p.add_argument("--mode", choices=["off", "shadow", "active"], help="per-call mode override")
        for a, kw in args:
            p.add_argument(a, **kw)
        return p
    add("health")
    add("discover", ("--modality", {"default": "any", "choices": ["image", "video", "audio", "any"]}),
        ("--query", {}), ("--provider", {}), ("--task-type", {}), ("--limit", {"type": int, "default": 50}))
    add("schema", ("--model", {"required": True}))
    add("validate", ("--model", {"required": True}), ("--payload", {"required": True}))
    add("upload", ("--file", {}), ("--url", {}), ("--upload-path", {"default": "openclaw/uploads"}))
    add("submit", ("--request", {"required": True}), ("--dry-run", {"action": "store_true"}))
    add("wait", ("--task-id", {"required": True}), ("--timeout", {"type": float, "default": 300}))
    add("run", ("--request", {"required": True}), ("--save-dir", {"required": True}),
        ("--timeout", {"type": float, "default": None}))
    add("credits")
    add("price", ("--model", {"required": True}), ("--units", {"type": float, "default": 1.0}))
    add("preflight", ("--model", {"required": True}), ("--units", {"type": float, "default": 1.0}))
    add("success-rate", ("--model", {"required": True}))
    add("prompt-budget", ("--model", {"required": True}), ("--check", {"action": "store_true"}),
        ("--prompt-file", {}))
    add("latest-family", ("--family", {"required": True}), ("--capability", {"action": "append"}),
        ("--current-default", {}), ("--refresh", {"action": "store_true"}))
    add("save", ("--task-id", {"required": True}), ("--save-dir", {"required": True}))
    a = ap.parse_args(argv)
    try:
        ad = adapter or Adapter()
    except KieError as e:
        out.write(json.dumps({"state": "fail", "error": {"code": e.code, "msg": e.msg}}) + "\n")
        return 1
    if a.mode:
        ad.mode = a.mode
    exit_code = None
    try:
        if a.cmd == "health":
            r = ad.cmd_health()
        elif a.cmd == "discover":
            r = ad.cmd_discover(a.modality, a.query, a.provider, a.task_type, a.limit)
        elif a.cmd == "schema":
            r = ad.cmd_schema(a.model)
        elif a.cmd == "validate":
            r = ad.cmd_validate(a.model, _load_json(a.payload))
        elif a.cmd == "upload":
            if bool(a.file) == bool(a.url):
                raise KieError("bad_request", "give exactly one of --file / --url")
            r = ad.cmd_upload(a.file, a.url, a.upload_path)
        elif a.cmd == "submit":
            r = ad.cmd_submit(_load_json(a.request), a.dry_run)
        elif a.cmd == "wait":
            r = ad.cmd_wait(a.task_id, a.timeout)
        elif a.cmd == "run":
            r = ad.cmd_run(_load_json(a.request), a.save_dir, a.timeout)
        elif a.cmd == "credits":
            r = ad.cmd_credits()
        elif a.cmd == "price":
            r = ad.cmd_price(a.model, a.units)
        elif a.cmd == "preflight":
            r = ad.cmd_preflight(a.model, a.units)
        elif a.cmd == "success-rate":
            r = ad.cmd_success_rate(a.model)
        elif a.cmd == "prompt-budget":
            if a.check and not a.prompt_file:
                raise KieError("bad_request", "--check needs --prompt-file")
            text = None
            if a.check:
                if a.prompt_file == "-":
                    text = sys.stdin.read()
                else:
                    with open(a.prompt_file, encoding="utf-8") as f:
                        text = f.read()
            r = ad.cmd_prompt_budget(a.model, a.check, text)
            exit_code = r["data"].get("exit_code", 0)
        elif a.cmd == "latest-family":
            caps = [c.strip() for x in (a.capability or []) for c in x.split(",") if c.strip()]
            r = ad.cmd_latest_family(a.family, caps or None, a.current_default, a.refresh)
        else:
            r = ad.cmd_save(a.task_id, a.save_dir)
    except (KieError, OSError, ValueError) as e:
        r = ad.result(state="fail", error={"code": getattr(e, "code", "error"), "msg": ad.redact(getattr(e, "msg", str(e)))})
    out.write(ad.redact(json.dumps(r, indent=2)) + "\n")
    if exit_code:  # prompt-budget --check: 3 below the floor, 4 above the max
        return exit_code
    return 1 if r["state"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
