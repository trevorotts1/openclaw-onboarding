import io
import json
import os
import tempfile
import unittest

from fakes import K, MODEL, make, slurp

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import build_model_registry as B  # noqa: E402


def schema(prompt_max=None, desc=None, extra=None):
    p = {"type": "string"}
    if prompt_max:
        p["maxLength"] = prompt_max
    if desc:
        p["description"] = desc
    props = {"prompt": p, "resolution": {"type": "string", "enum": ["1K", "2K"]}}
    props.update(extra or {})
    inp = {"type": "object", "required": ["prompt"], "properties": props}
    body = {"type": "object", "required": ["model", "input"], "properties": {"model": {"type": "string"}, "input": inp}}
    doc = {"paths": {K.JOB_PATH: {"post": {"requestBody": {"content": {"application/json": {"schema": body}}}}}}}
    return (200, {"code": 200, "data": {"model": "x", "openapi": doc}})


def cat(*rows):
    return (200, {"code": 200, "data": {"total": len(rows), "models": [
        {"model": m, "title": m, "provider": "OpenAI", "taskType": tt, "pricingDesc": pr} for m, tt, pr in rows]}})


T2I, I2I = ["Text to Image"], ["Image to Image"]
G25S, G25S_I = "gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-5-sunburst-image-to-image"
G3A, G3A_I = "gpt-image-3-aurora-text-to-image", "gpt-image-3-aurora-image-to-image"
G3B, G3B_I = "gpt-image-3-borealis-text-to-image", "gpt-image-3-borealis-image-to-image"


def sr(rate):
    return (200, {"code": 200, "data": {"model": "x", "points": [{"successRate": rate, "isNormal": True}, {"successRate": None}]}})


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)
        # no sibling-skill policy owners and no repo registry unless a test supplies them
        self.empty = os.path.join(self.tmp, "none.json")
        self._old = os.environ.get("KIE_POLICY_ROOT")
        os.environ["KIE_POLICY_ROOT"] = os.path.join(self.tmp, "skills")
        self.addCleanup(self._restore)

    def _restore(self):
        if self._old is None:
            os.environ.pop("KIE_POLICY_ROOT", None)
        else:
            os.environ["KIE_POLICY_ROOT"] = self._old

    def adapter(self, routes, env=None):
        e = {"KIE_LIVE_REGISTRY": self.empty, "OPENCLAW_SKILLS_DIR": os.path.join(self.tmp, "skills")}
        e.update(env or {})
        return make(self.tmp, routes, extra_env=e)

    def write_registry(self, models, gen="2026-10-05T00:00:00Z"):
        p = os.path.join(self.tmp, "reg.json")
        with open(p, "w") as f:
            json.dump({"generated_at": gen, "source": "live-api", "models": models}, f)
        return p

    def cli(self, a, argv):
        out = io.StringIO()
        rc = K.main(argv, adapter=a, out=out)
        return rc, json.loads(out.getvalue())


class Helpers(unittest.TestCase):
    def test_budget_integer_math(self):
        self.assertEqual(K.budget(20000), {"max": 20000, "floor": 16000, "target_min": 19000, "target_max": 20000})
        self.assertEqual(K.budget(5000)["floor"], 4000)
        self.assertEqual(K.budget(3072)["floor"], 2458)  # ceil(2457.6)
        self.assertEqual(K.budget(3072)["target_min"], 2919)  # ceil(2918.4)

    def test_family_version_variant(self):
        self.assertEqual((K.family_of(G25S), K.version_of(G25S), K.variant_of(G25S)), ("gpt-image", [2, 5], "sunburst"))
        self.assertEqual((K.version_of("gpt-image-2-text-to-image"), K.variant_of("gpt-image-2-text-to-image")), ([2], None))
        self.assertEqual(K.version_of("gpt-image/1.5-text-to-image"), [1, 5])
        self.assertIsNone(K.version_of("4o-image-api"))
        self.assertEqual(K.family_of("ai-music-api/generate"), "suno")

    def test_parse_pricing(self):
        p = K.parse_pricing("now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, and 16 credits ($0.08) for 4 K")
        self.assertEqual((p["credits_min"], p["credits_max"], p["unit"]), (6.0, 16.0, "per-job"))
        self.assertEqual(K.parse_pricing("27 credits per second (~$0.135)")["unit"], "per-second")
        self.assertEqual(K.parse_pricing("Input 100 credits / 1M tokens, Output 700 credits / 1M tokens")["unit"], "per-1m-tokens")
        self.assertIsNone(K.parse_pricing("")["credits_max"])
        self.assertEqual(K.preflight_amount(6), 7.8)

    def test_described_limits(self):
        self.assertEqual(K.described_limits("Text prompts, up to 20,000 characters."), [20000])
        self.assertEqual(K.described_limits("Maximum length is 1800 characters."), [1800])
        self.assertEqual(K.described_limits("no limit stated"), [])


class Price(Base):
    def test_price_live_and_preflight_multiplier(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [cat((G25S, T2I, "6 credits for 1K, 16 credits for 4K"))]]])
        r = a.cmd_price(G25S)
        self.assertEqual((r["state"], r["data"]["credits_estimate"], r["data"]["preflight_required"]), ("success", 16.0, 20.8))
        self.assertEqual(r["data"]["price_source"], "catalog:live")

    def test_price_registry_fallback_and_unavailable(self):
        reg = self.write_registry([{"id": MODEL, "pricing": {"raw": "9 credits per image"}}])
        a, tr, c = self.adapter([], env={"KIE_LIVE_REGISTRY": reg, "KIE_API_KEY": ""})
        a.key = ""
        r = a.cmd_price(MODEL)
        self.assertEqual((r["state"], r["data"]["price_source"], r["data"]["credits_estimate"]), ("success", "registry", 9.0))
        self.assertTrue(any("registry snapshot" in w for w in r["warnings"]))
        self.assertEqual(a.cmd_price("nope/none")["error"]["code"], "price_unavailable")

    def test_preflight_ok_and_shortfall(self):
        routes = [["GET", "/api/v1/models", [cat((MODEL, T2I, "100 credits"))]],
                  ["GET", "/chat/credit", [(200, {"code": 200, "data": 130})]]]
        a, tr, c = self.adapter(routes)
        r = a.cmd_preflight(MODEL)
        self.assertEqual((r["state"], r["data"]["ok"], r["data"]["shortfall"]), ("validated", True, 0.0))
        routes[1][2] = [(200, {"code": 200, "data": 129})]
        a, tr, c = self.adapter(routes)
        r = a.cmd_preflight(MODEL)
        self.assertEqual((r["state"], r["error"]["code"], r["data"]["shortfall"]), ("fail", "insufficient_credits", 1.0))

    def test_per_second_units(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [cat(("omnihuman-1-5", ["Image to Video"], "27 credits per second"))]]])
        self.assertEqual(a.cmd_price("omnihuman-1-5", units=10)["data"]["credits_estimate"], 270.0)


class PromptBudget(Base):
    def routes(self, sch):
        return [["GET", "/schema", [sch]], ["GET", "/api/v1/models", [cat((MODEL, T2I, "6 credits"))]]]

    def test_check_exit_codes(self):
        a, tr, c = self.adapter(self.routes(schema(1000)))
        f = os.path.join(self.tmp, "p.txt")
        for n, rc, status in ((500, 3, "BELOW_FLOOR"), (799, 3, "BELOW_FLOOR"), (800, 0, "BELOW_TARGET"),
                              (950, 0, "OK"), (1000, 0, "OK"), (1001, 4, "ABOVE_MAX")):
            with open(f, "w") as fh:
                fh.write("a" * n + "\n")
            got, r = self.cli(a, ["prompt-budget", "--model", MODEL, "--check", "--prompt-file", f])
            self.assertEqual((got, r["data"]["status"]), (rc, status), n)
        with open(f, "w") as fh:
            fh.write("a" * 799)
        r = self.cli(a, ["prompt-budget", "--model", MODEL, "--check", "--prompt-file", f])[1]
        self.assertIn("ADD at least 1 chars (151 to reach the 95% target of 950)", r["error"]["msg"])
        with open(f, "w") as fh:
            fh.write("a" * 1004)
        self.assertIn("CUT exactly 4 chars", self.cli(a, ["prompt-budget", "--model", MODEL, "--check", "--prompt-file", f])[1]["error"]["msg"])

    def test_budget_fields_without_check(self):
        a, tr, c = self.adapter(self.routes(schema(20000)))
        d = a.cmd_prompt_budget(MODEL)["data"]
        self.assertEqual((d["field"], d["max"], d["floor"], d["target_min"], d["target_max"]), ("prompt", 20000, 16000, 19000, 20000))

    def test_described_limit_used_with_note(self):
        a, tr, c = self.adapter(self.routes(schema(None, "Text prompts, up to 20,000 characters.")))
        r = a.cmd_prompt_budget(MODEL)
        self.assertEqual(r["data"]["max"], 20000)
        self.assertIn("description", r["data"]["limit_source"])

    def test_unknown_limit_exit_0_with_warning(self):
        a, tr, c = self.adapter(self.routes(schema(None, "A prompt.")))
        rc, r = self.cli(a, ["prompt-budget", "--model", MODEL, "--check", "--prompt-file", self._pf("x" * 10)])
        self.assertEqual((rc, r["data"]["status"]), (0, "UNKNOWN"))
        self.assertTrue(any("UNKNOWN" in w for w in r["warnings"]))

    def _pf(self, text):
        f = os.path.join(self.tmp, "pf.txt")
        with open(f, "w") as fh:
            fh.write(text)
        return f

    def test_policy_owner_limit_for_unknown(self):
        sk = os.path.join(self.tmp, "skills", "66-kie-image")
        os.makedirs(sk)
        with open(os.path.join(sk, "models.json"), "w") as f:
            json.dump({"models": [{"canonical_model_id": MODEL, "vendor_hard_cap_chars": 4000}]}, f)
        a, tr, c = self.adapter(self.routes(schema(None, "A prompt.")))
        d = a.cmd_prompt_budget(MODEL)["data"]
        self.assertEqual((d["max"], d["limit_source"]), (4000, "policy-owner:66-kie-image"))

    def test_legacy_n43_cap_superseded_warning(self):
        sk = os.path.join(self.tmp, "skills", "66-kie-image")
        os.makedirs(sk)
        with open(os.path.join(sk, "models.json"), "w") as f:
            json.dump({"models": [{"canonical_model_id": MODEL, "owner_observed_cap_chars": 25000,
                                   "live_schema_cap_chars": 20000}]}, f)
        a, tr, c = self.adapter(self.routes(schema(20000)))
        r = a.cmd_prompt_budget(MODEL, True, "x" * 20001)
        self.assertEqual((r["data"]["max"], r["data"]["exit_code"]), (20000, 4))
        self.assertTrue(any("25000" in w and "superseded" in w and "2026-10-05" in w for w in r["warnings"]), r["warnings"])
        # description-stated limit does not let the old 25,000 override the live figure either
        a, tr, c = self.adapter(self.routes(schema(None, "Text prompts, up to 20,000 characters.")), env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "cc")})
        self.assertEqual(a.cmd_prompt_budget(MODEL)["data"]["max"], 20000)

    def test_verbatim_field_has_no_floor(self):
        tts = "elevenlabs/text-to-speech-turbo-2-5"
        doc = {"paths": {K.JOB_PATH: {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "properties": {"input": {"type": "object", "required": ["text"], "properties": {
                "text": {"type": "string", "maxLength": 5000}}}}}}}}}}}}
        a, tr, c = self.adapter([["GET", "/schema", [(200, {"code": 200, "data": {"openapi": doc}})]]])
        r = a.cmd_prompt_budget(tts, True, "hello")
        self.assertEqual((r["state"], r["data"]["status"], r["data"]["verbatim"]), ("validated", "VERBATIM", True))
        self.assertEqual(a.cmd_prompt_budget(tts, True, "x" * 5001)["data"]["exit_code"], 4)

    def test_registry_fallback_when_live_down(self):
        reg = self.write_registry([{"id": MODEL, "prompt_field": {"name": "prompt", "maxLength": 2000, "verbatim": False}}])
        a, tr, c = self.adapter([["GET", "/schema", [(200, {"code": 401, "msg": "no"})]]], env={"KIE_LIVE_REGISTRY": reg})
        r = a.cmd_prompt_budget(MODEL, True, "x" * 100)
        self.assertEqual((r["data"]["max"], r["data"]["limit_source"], r["data"]["exit_code"]), (2000, "registry", 3))


class ValidateRegistry(Base):
    def test_registry_enforces_maxlength_enum_required(self):
        entry = {"id": MODEL, "taskType": T2I, "schema_paths": [{"path": K.JOB_PATH, "kind": "createTask"}],
                 "required": ["prompt"], "branches": [],
                 "input_fields": {"prompt": {"type": "string", "maxLength": 10}, "resolution": {"type": "string", "enum": ["1K"]}}}
        reg = self.write_registry([entry])
        a, tr, c = self.adapter([["GET", "/schema", [(200, {"code": 401, "msg": "no"})]]], env={"KIE_LIVE_REGISTRY": reg})
        self.assertEqual(a.cmd_validate(MODEL, {"prompt": "ok", "resolution": "1K"})["state"], "validated")
        for bad in ({}, {"prompt": "x" * 11}, {"prompt": "x", "resolution": "9K"}):
            r = a.cmd_validate(MODEL, bad)
            self.assertEqual((r["state"], r["error"]["code"]), ("fail", "validation_failed"), bad)
        self.assertEqual(r["schema_source"], "registry")
        self.assertTrue(any("registry snapshot" in w for w in r["warnings"]))

    def test_unknown_model_still_fails_with_live_error(self):
        a, tr, c = self.adapter([["GET", "/schema", [(200, {"code": 404, "msg": "gone"})]]])
        self.assertEqual(a.cmd_validate("zzz/none", {"prompt": "x"})["error"]["code"], 404)


class LatestFamily(Base):
    def routes(self, rows, schemas=None, rates=None):
        r = []
        for mid, s in (schemas or {}).items():
            r.append(["GET", "/models/%s/schema" % mid, [s]])
        for mid, v in (rates or {}).items():
            r.append(["GET", "/models/%s/success-rate" % mid, [sr(v)]])
        r.append(["GET", "/schema", [schema(20000)]])
        r.append(["GET", "/api/v1/models", [cat(*rows)]])
        return r

    BASE = [(G25S, T2I, "6 credits"), (G25S_I, I2I, "6 credits")]

    def test_current_default_when_nothing_newer(self):
        a, tr, c = self.adapter(self.routes(self.BASE))
        d = a.cmd_latest_family("gpt-image")["data"]
        self.assertEqual((d["default"], d["changed"], d["chosen_by"]), (G25S, False, "variant-match"))

    def test_newer_generation_becomes_default_with_receipt(self):
        rows = self.BASE + [(G3A, T2I, "7 credits"), (G3A_I, I2I, "7 credits")]
        a, tr, c = self.adapter(self.routes(rows, rates={G3A: 99.0}))
        r = a.cmd_latest_family("gpt-image")
        d = r["data"]
        self.assertEqual((d["default"], d["routes"]["Image to Image"], d["changed"], d["previous_default"]), (G3A, G3A_I, True, G25S))
        self.assertTrue(any("DEFAULT CHANGED" in w for w in r["warnings"]))
        rd = os.path.join(self.tmp, "cache", "receipts")
        self.assertTrue(os.path.isdir(os.path.join(rd, "promotions")))
        self.assertIn("default_promotion", "".join(slurp(os.path.join(rd, f)) for f in os.listdir(rd) if f.endswith(".jsonl")))
        # next run: state remembers the promotion, no new receipt, same answer
        c.t += 7 * 3600
        d2 = a.cmd_latest_family("gpt-image")["data"]
        self.assertEqual((d2["default"], d2["changed"]), (G3A, False))

    def test_needs_both_routes_and_readable_schema(self):
        rows = self.BASE + [(G3A, T2I, "7 credits")]  # no image-to-image: not eligible
        a, tr, c = self.adapter(self.routes(rows))
        self.assertEqual(a.cmd_latest_family("gpt-image")["data"]["default"], G25S)
        rows = self.BASE + [(G3A, T2I, "7"), (G3A_I, I2I, "7")]
        bad = (200, {"code": 200, "data": {"model": "x", "openapi": None}})
        a, tr, c = self.adapter(self.routes(rows, schemas={G3A_I: bad}), env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "c9")})
        r = a.cmd_latest_family("gpt-image")
        self.assertEqual(r["data"]["default"], G25S)
        self.assertTrue(any("schema not readable" in w for w in r["warnings"]))

    def test_variant_preference_then_success_rate_then_price(self):
        two = [(G3A, T2I, "9 credits"), (G3A_I, I2I, "9 credits"), (G3B, T2I, "5 credits"), (G3B_I, I2I, "5 credits")]
        # no sunburst in the new generation: success rate decides
        a, tr, c = self.adapter(self.routes(self.BASE + two, rates={G3A: 80.0, G3B: 95.0}))
        d = a.cmd_latest_family("gpt-image")["data"]
        self.assertEqual((d["default"], d["chosen_by"]), (G3B, "success-rate"))
        # equal rates: lower price decides
        a, tr, c = self.adapter(self.routes(self.BASE + two, rates={G3A: 90.0, G3B: 90.0}), env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "c2")})
        d = a.cmd_latest_family("gpt-image")["data"]
        self.assertEqual((d["default"], d["chosen_by"]), (G3B, "price"))
        # a sunburst variant in the new generation wins over better numbers
        sun = [("gpt-image-3-sunburst-text-to-image", T2I, "20"), ("gpt-image-3-sunburst-image-to-image", I2I, "20")]
        a, tr, c = self.adapter(self.routes(self.BASE + two + sun, rates={G3A: 99.0, G3B: 99.0}), env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "c3")})
        d = a.cmd_latest_family("gpt-image")["data"]
        self.assertEqual((d["default"], d["chosen_by"]), ("gpt-image-3-sunburst-text-to-image", "variant-match"))

    def test_numeric_version_order(self):
        rows = self.BASE + [("gpt-image/1.5-text-to-image", T2I, "4"), ("gpt-image/1.5-image-to-image", I2I, "4"),
                            ("gpt-image-2-text-to-image", T2I, "6"), ("gpt-image-2-image-to-image", I2I, "6"),
                            ("4o-image-api", T2I + I2I, "6")]
        a, tr, c = self.adapter(self.routes(rows))
        self.assertEqual(a.cmd_latest_family("gpt-image")["data"]["version"], [2, 5])

    def test_registry_fallback_when_catalog_unreachable(self):
        def row(i, tt, ok=True):
            return {"id": i, "taskType": tt, "schema": {"readable": ok}, "pricing": {"raw": "6 credits"}}
        reg = self.write_registry([row(G25S, T2I), row(G25S_I, I2I), row(G3A, T2I), row(G3A_I, I2I, ok=False)])
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]], env={"KIE_LIVE_REGISTRY": reg})
        r = a.cmd_latest_family("gpt-image")
        self.assertEqual((r["state"], r["data"]["default"], r["data"]["source"]), ("success", G25S, "registry"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "cache", "promotion-state.json")), "registry never promotes")

    def test_unavailable_without_catalog_or_registry(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]])
        self.assertEqual(a.cmd_latest_family("gpt-image")["error"]["code"], "latest_unavailable")

    def test_six_hour_cache(self):
        a, tr, c = self.adapter(self.routes(self.BASE))
        a.cmd_latest_family("gpt-image")
        n = tr.n("GET", "/api/v1/models")
        a.cmd_latest_family("gpt-image")
        self.assertEqual(tr.n("GET", "/api/v1/models"), n)
        self.assertEqual(a.cmd_latest_family("gpt-image")["data"]["source"], "cache")

    def test_cli_capability_and_current_default(self):
        a, tr, c = self.adapter(self.routes(self.BASE))
        rc, r = self.cli(a, ["latest-family", "--family", "gpt-image", "--capability", "Text to Image", "--current-default", G25S])
        self.assertEqual((rc, list(r["data"]["routes"])), (0, ["Text to Image"]))


class Misc(Base):
    def test_success_rate(self):
        a, tr, c = self.adapter([["GET", "/success-rate", [sr(97.5)]]])
        d = a.cmd_success_rate(MODEL)["data"]
        self.assertEqual((d["avg_success_rate"], d["samples"], d["points"]), (97.5, 1, 2))
        self.assertTrue(tr.calls[0]["url"].endswith("/api/v1/models/%s/success-rate" % MODEL))
        a, tr, c = self.adapter([["GET", "/success-rate", [(200, {"code": 200, "data": {"model": "x", "points": []}})]]])
        r = a.cmd_success_rate(MODEL)
        self.assertIsNone(r["data"]["avg_success_rate"])
        self.assertTrue(r["warnings"])

    def test_callback_url_recorded_and_validated(self):
        from fakes import std_routes
        a, tr, c = make(self.tmp, std_routes(), mode="active")
        r = a.cmd_submit({"model": MODEL, "input": {"prompt": "x"}, "callBackUrl": "https://relay.example/cb"})
        self.assertEqual((r["data"]["callback_url"], r["data"]["callback_sent"]), ("https://relay.example/cb", True))
        body = json.loads(next(x for x in tr.calls if x["method"] == "POST")["body"])
        self.assertEqual(body["callBackUrl"], "https://relay.example/cb")
        self.assertEqual(a.cmd_submit({"model": MODEL, "input": {"prompt": "x"}, "callBackUrl": "ftp://x"})["error"]["code"], "bad_request")
        a, tr, c = make(self.tmp, std_routes(), mode="shadow")
        r = a.cmd_submit({"model": MODEL, "input": {"prompt": "x"}, "callBackUrl": "https://relay.example/cb"})
        self.assertEqual((r["state"], r["data"]["callback_sent"]), ("skipped", False))

    def test_per_call_mode_override(self):
        from fakes import std_routes
        a, tr, c = make(self.tmp, std_routes(), mode="shadow")
        req = os.path.join(self.tmp, "req.json")
        with open(req, "w") as f:
            json.dump({"model": MODEL, "input": {"prompt": "x"}}, f)
        rc, r = self.run_cli(a, ["submit", "--request", req])
        self.assertEqual(r["state"], "skipped")
        rc, r = self.run_cli(a, ["submit", "--request", req, "--mode", "active"])
        self.assertEqual((r["state"], r["adapter_mode"]), ("queued", "active"))
        a2, tr2, c2 = make(self.tmp, std_routes(), mode="active")
        rc, r = self.run_cli(a2, ["submit", "--request", req, "--mode", "off"])
        self.assertEqual(r["state"], "skipped")

    def run_cli(self, a, argv):
        out = io.StringIO()
        rc = K.main(argv, adapter=a, out=out)
        return rc, json.loads(out.getvalue())


class RegistryBuild(Base):
    def test_build_live_registry_with_fake_transport(self):
        rows = [(G25S, T2I, "6 credits for 1K"), ("claude-x", ["Chat"], "Input 10 credits / 1M tokens"), ("bad/none", T2I, "")]
        sync = {"paths": {"/claude/v1/messages": {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "required": ["messages"], "properties": {"messages": {"type": "array"}, "model": {"type": "string"}}}}}}}}}}
        routes = [["GET", "/models/%s/schema" % G25S, [schema(20000, extra={"seed": {"type": "integer", "minimum": 0}})]],
                  ["GET", "/models/claude-x/schema", [(200, {"code": 200, "data": {"openapi": sync}})]],
                  ["GET", "/models/bad/none/schema", [(200, {"code": 200, "data": {"openapi": None}})]],
                  ["GET", "/api/v1/models", [cat(*rows)]]]
        a, tr, c = self.adapter(routes)
        out = os.path.join(self.tmp, "reg", "r.json")
        reg = B.build(ad=a, source="auto", out=out, now=c.now, log=lambda *x: None)
        self.assertEqual((reg["source"], reg["counts"]["models"], reg["counts"]["schema_readable"], reg["counts"]["kind_sync"]), ("live-api", 3, 2, 1))
        by = {m["id"]: m for m in json.loads(slurp(out))["models"]}
        g = by[G25S]
        self.assertEqual((g["family"], g["version"], g["variant"], g["prompt_field"]["maxLength"], g["pricing"]["credits_max"]), ("gpt-image", [2, 5], "sunburst", 20000, 6.0))
        self.assertEqual(g["input_fields"]["seed"]["minimum"], 0)
        self.assertEqual(g["input_fields"]["resolution"]["enum"], ["1K", "2K"])
        self.assertEqual(by["claude-x"]["schema"]["kind"], "sync")
        self.assertEqual(by["bad/none"]["schema"]["error"]["code"], "schema_not_synced")
        gaps = [s for s in c.slept if s >= 1.0]
        self.assertTrue(len(gaps) >= 3, "schema and catalog calls are spaced")
        self.assertNotIn("fake-key", json.dumps(reg))

    def test_no_key_selects_public_docs(self):
        a, tr, c = self.adapter([])
        a.key = ""
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not importable")
        md = """# Title
```yaml
openapi: 3.0.1
paths:
  /api/v1/jobs/createTask:
    post:
      tags: [a/Market/Image/GPT Image]
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                model:
                  enum: [%s]
                input:
                  type: object
                  required: [prompt]
                  properties:
                    prompt: {type: string, maxLength: 20000}
```
""" % G25S
        tr.add("GET", "docs.kie.ai/market/gpt/x.md", [(200, md.encode())])
        tr.add("GET", "llms.txt", [(200, b"- [GPT X](https://docs.kie.ai/market/gpt/x.md): d\n- [CN](https://docs.kie.ai/cn/market/gpt/x.md): d\n")])
        reg = B.build(ad=a, source="auto", out=os.path.join(self.tmp, "d.json"), now=c.now, log=lambda *x: None, transport=tr)
        self.assertEqual(reg["source"], "public-docs")
        m = reg["models"][0]
        self.assertEqual((m["id"], m["prompt_field"]["maxLength"], m["pricing"]["status"]), (G25S, 20000, "unavailable-without-key"))


if __name__ == "__main__":
    unittest.main()


class RealPricing(Base):
    """Units must come from KIE's real phrasings (credits/s, credits / sec, credits per video second, ...)."""

    def test_real_strings_parse_to_the_right_unit(self):
        from real_pricing import REAL
        for mid, unit, raw in REAL:
            self.assertEqual(K.parse_pricing(raw)["unit"], unit, mid)

    def test_duration_prices_stay_per_job(self):
        from real_pricing import REAL
        p = K.parse_pricing(dict((m, r) for m, _, r in REAL)["kling/v2-1-pro"])
        self.assertEqual((p["unit"], p["credits_max"]), ("per-job", 100.0))
        self.assertEqual(K.estimate_credits(p, 7), 100.0, "per-job price does not scale with units")
        self.assertEqual(K.parse_pricing("5s at 720p costs 12 credits per video, 10s at 720p costs 30 credits per video")["unit"], "per-job")

    def test_free_is_zero_credits(self):
        p = K.parse_pricing("Check Voice is free.")
        self.assertEqual((p["credits_max"], K.estimate_credits(p)), (0.0, 0.0))

    def test_scaling_with_units(self):
        from real_pricing import REAL
        raws = dict((m, r) for m, _, r in REAL)
        sd = K.parse_pricing(raws["bytedance/seedance-2"])
        top = sd["credits_max"]
        self.assertEqual(K.estimate_credits(sd, 5), round(top * 5, 4))
        self.assertEqual(K.preflight_amount(K.estimate_credits(sd, 5)), K.preflight_amount(top * 5))
        hh = K.parse_pricing(raws["happyhorse/text-to-video"])
        self.assertEqual((hh["credits_max"], K.estimate_credits(hh, 10)), (48.0, 480.0))
        tts = K.parse_pricing(raws["elevenlabs/text-to-speech-turbo-2-5"])
        self.assertEqual(K.estimate_credits(tts, 3), 18.0)  # 6 credits per 1,000 characters x 3 thousand

    def test_price_command_scales_real_seedance(self):
        from real_pricing import REAL
        raws = dict((m, r) for m, _, r in REAL)
        a, tr, c = self.adapter([["GET", "/api/v1/models", [cat(("bytedance/seedance-2", ["Text to Video"], raws["bytedance/seedance-2"]))]]])
        one = a.cmd_price("bytedance/seedance-2", 1)["data"]
        five = a.cmd_price("bytedance/seedance-2", 5)["data"]
        self.assertEqual((one["unit"], five["unit"]), ("per-second", "per-second"))
        self.assertEqual(five["credits_estimate"], round(one["credits_estimate"] * 5, 4))

    def test_committed_registry_units(self):
        """Registry-wide: no model whose pricing text is per second is labeled per-job; duration prices stay per-job."""
        reg = json.loads(slurp(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "kie-model-registry.json")))
        per_second_ids = {
            "bytedance/seedance-2", "bytedance/seedance-2-5", "bytedance/seedance-2-fast", "bytedance/seedance-2-mini",
            "bytedance/seedance-1.5-pro", "happyhorse/text-to-video", "happyhorse-1-1/text-to-video", "kling-3.0/video",
            "kling-3.0-omni/text-to-video", "kling-3.0/motion-control", "kling/v3-turbo-text-to-video",
            "pixverse-v6/text-to-video", "minimax-h3/text-to-video", "wan/3-0-video", "wan/3-0-video-prime",
            "wan/2-2-a14b-speech-to-video-turbo", "wan/2-2-animate-move", "grok-imagine/text-to-video",
            "kling/ai-avatar-pro", "hailuo/02-image-to-video-pro", "wan/2-7-text-to-video", "infinitalk/from-audio"}
        per_job_ids = {"kling/v2-1-pro", "kling/v2-1-master-text-to-video", "wan/2-6-text-to-video", "runway",
                       "kling/v2-5-turbo-text-to-video-pro", "veo-3-1", "gpt-image-2-5-sunburst-text-to-image"}
        by = {m["id"]: m for m in reg["models"]}
        for i in per_second_ids:
            self.assertEqual(by[i]["pricing"]["unit"], "per-second", i)
        for i in per_job_ids:
            self.assertEqual(by[i]["pricing"]["unit"], "per-job", i)
        import re
        phrase = re.compile(r"(?i)credits?\b[^\n]{0,40}?(?:/|／|per\s+(?:video[\s-])?)\s*(?:s|sec|second)s?\b")
        for m in reg["models"]:
            raw = m["pricing"].get("raw") or ""
            if any("Video" in t for t in m["taskType"]) and phrase.search(raw):
                self.assertNotEqual(m["pricing"]["unit"], "per-job", m["id"])
            if raw:
                self.assertEqual(m["pricing"]["unit"], K.parse_pricing(raw)["unit"], m["id"])
