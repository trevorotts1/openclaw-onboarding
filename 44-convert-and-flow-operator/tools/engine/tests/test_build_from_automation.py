"""U-skill44-05: reader -> engine path, Skill 50 hand-off, custom-field/pipeline create,
payments through the shared products/prices module.

Mock-only: no network, no credentials. Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_build_from_automation.py -q
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
REPO = SKILL.parent
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel import gohighlevel_cli as cli_mod  # noqa: E402
from cli_anything.gohighlevel.gohighlevel_cli import cli  # noqa: E402
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plan_reader = _load("u44_05_plan_reader", SKILL / "automation-templates" / "launch-c" / "plan_reader.py")
emit = _load("u44_05_emit_build_plan", REPO / "50-email-engine" / "tools" / "emit_build_plan.py")

LOC = "LOC1"
CALENDAR = {
    "launch_at": "2026-11-03T12:00:00-05:00",
    "doors_open_at": "2026-11-03T09:00:00-05:00",
    "doors_close_at": "2026-11-10T23:59:00-05:00",
    "timezone": "America/New_York",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    for key, value in {"CAF_DATA_DIR": str(tmp_path), "CAF_ALLOWED_LOCATION_IDS": LOC,
                       "CAF_APPROVAL_TOKEN": "t", "GHL_API_KEY": "fake-pit-token",
                       "GHL_LOCATION_ID": LOC}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CAF_DRY_RUN", raising=False)
    monkeypatch.delenv("CAF_BUILD_JOURNAL", raising=False)


def run(*args):
    return CliRunner().invoke(cli, ["--json", "--location-id", LOC, *args])


# ---- a ready automation-build document, from the real launch-c reader ----------

def _skill50_sequence(seq_id):
    templates = [
        {"id": "e%d" % i, "type": "email", "name": "Email %d" % i,
         "attributes": {"subject": "s%d" % i, "body": "<p>b</p>", "html": "<p>b</p>",
                        "fromName": "Sender", "conditions": []}}
        for i in range(2)
    ]
    return {"folder": "Drafts", "_meta": {"sequence_id": seq_id, "draft_only": True,
                                          "deploy_mode": "draft-only"},
            seq_id: {"name": "%s (DRAFT)" % seq_id, "tag": "launch:%s" % seq_id,
                     "status": "draft", "templates": templates}}


def ready_document(tmp_path):
    plan = {
        "schema_version": "1.0.0", "launch_id": "u44-05",
        "offer": {"name": "Synthetic", "price_usd": 1, "currency": "USD", "payment_plans": False},
        "launch_calendar": dict(CALENDAR),
        "a2p_ready": False,
        "conversation_ai": {"requested": False, "mode": "none"},
        "pages": [{"id": "page_landing", "kind": "landing", "url": "https://example.test",
                   "waits_for": []}],
        "email_sequences": [{"id": "email_pre_launch", "kind": "pre_launch", "provider": "skill50",
                             "email_count": 2, "draft_only": True, "waits_for": []}],
        "text_sets": [],
        "automations": [{"id": "auto_pre_launch", "family": "pre_launch", "template": "launch-a/launch-a-prelaunch-window",
                         "build_rail": "skill44_engine", "draft_only": True,
                         "trigger": {"type": "tag_added"},
                         "waits_for": ["email_pre_launch", "page_landing"]}],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "seq.json").write_text(json.dumps(_skill50_sequence("email_pre_launch")))
    out = tmp_path / "automation-builds.json"
    assert plan_reader.main(["--launch-plan", str(tmp_path / "plan.json"), "--out", str(out),
                             "--build-plan", str(tmp_path / "seq.json"),
                             "--now", "2026-11-01T00:00:00-05:00"]) == 0
    return out


# ---- rows 1 + 4: --from-automation-build ---------------------------------------

def test_dry_run_compiles_through_compile_launch_builds(tmp_path):
    doc = ready_document(tmp_path)
    journal = tmp_path / "j.jsonl"
    seen = []
    real = wb.compile_launch_builds

    def spy(document, **kw):
        seen.append(kw)
        return real(document, **kw)

    with patch.object(wb, "compile_launch_builds", spy), \
            patch.object(cli_mod, "_get_internal_client", side_effect=AssertionError("no client")):
        result = run("workflows", "build", "--from-automation-build", str(doc),
                     "--journal", str(journal), "--dry-run")
    assert result.exit_code == 0, result.output
    assert seen == [{"require_ready": True}]
    report = json.loads(result.output)
    assert report["dry_run"] is True and report["errors"] == []
    assert [w["unit_key"] for w in report["workflows"]] == ["u44-05/auto_pre_launch/email_pre_launch"]
    assert not journal.exists(), "dry run must not write the journal"


def test_live_build_runs_compile_then_build_with_journal(tmp_path):
    doc = ready_document(tmp_path)
    journal = tmp_path / "j.jsonl"
    calls = {}
    selected_browser_executor = object()

    class Builder:
        def __init__(self, client, v4=None):
            calls["client"] = client

        # Mirror CampaignBuilder.build's real signature: the CLI forwards the
        # F11 browser capability, so a stub without it fails on the kwarg.
        def build(self, campaign, folder_name=None, folder_id=None, *,
                  journal=None, browser_executor=None):
            calls.update(campaign=campaign, folder=folder_name, journal=journal,
                         browser_executor=browser_executor)
            return {"errors": []}

        def format_summary(self):
            return "ok"

    with patch.object(wb, "CampaignBuilder", Builder), \
            patch.object(wb, "resolve_browser_executor", return_value=selected_browser_executor), \
            patch.object(cli_mod, "_get_internal_client", return_value=object()), \
            patch.object(cli_mod, "_get_public_v4", return_value=(None, "off")):
        result = CliRunner().invoke(cli, [
            "--experimental", "--json", "--location-id", LOC, "workflows", "build",
            "--from-automation-build", str(doc), "--journal", str(journal)])
    assert result.exit_code == 0, result.output
    assert calls["journal"] == str(journal)
    assert calls["browser_executor"] is selected_browser_executor
    assert calls["folder"] == "launch-u44-05"
    key, wf = next(iter(calls["campaign"].items()))
    assert wf["unit_key"] == "u44-05/auto_pre_launch/email_pre_launch" and wf["promotional"] is True
    assert wf["settings"]["suppression"]["stopOnVerifiedPurchase"] is True  # guards applied


def test_blocked_document_is_refused_before_any_client(tmp_path):
    doc = ready_document(tmp_path)
    data = json.loads(doc.read_text())
    data["builds"][0]["state"] = "blocked"
    data["builds"][0]["blocked_by"] = ["schedule_suppressed:email_pre_launch"]
    doc.write_text(json.dumps(data))
    with patch.object(cli_mod, "_get_internal_client", side_effect=AssertionError("no client")):
        result = run("workflows", "build", "--from-automation-build", str(doc),
                     "--journal", str(tmp_path / "j"), "--dry-run")
    assert result.exit_code == 1 and "BUILD-BLOCKED" in result.output


def test_automation_build_requires_journal_and_one_source(tmp_path):
    doc = ready_document(tmp_path)
    assert run("workflows", "build", "--from-automation-build", str(doc), "--dry-run").exit_code == 2
    assert run("workflows", "build", "--dry-run").exit_code == 2
    assert run("workflows", "build", "--from-plan", str(doc), "--from-automation-build", str(doc),
               "--journal", "j", "--dry-run").exit_code == 2


# ---- rows 2 + 5: Skill 50 plans through --from-plan ----------------------------

def _emails_doc(fam):
    return {
        "sequence_type": fam["profile"], "profile": fam["profile"],
        "sequence_id": fam["sequence_id"], "founder_name": "Jordan Marsh",
        "emails": [{"e_slot": slot, "framework": fam["framework_map"][str(slot)],
                    "objective": fam["objective"],
                    "subjects": ["subject A %d" % slot, "subject B %d" % slot],
                    "previews": ["preview A %d" % slot, "preview B %d" % slot][:fam["preview_count"]],
                    "body": "Body %d.\n\n[CTA ->]" % slot, "ctas": ["[CTA ->]"]}
                   for slot in range(1, fam["email_count"] + 1)],
    }


def test_legacy_skill50_plan_no_longer_fails_on_meta(tmp_path):
    plan = emit.build_plan({"answers": {"objective": "promotional"}}, {
        "sequence_id": "sequence-landing-page-10-promo", "founder_name": "J",
        "emails": [{"e_slot": 1, "framework": "f", "subjects": ["a", "b"], "previews": ["p"],
                    "body": "Hi", "ctas": []}]})
    assert "_meta" in plan
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    result = run("workflows", "build", "--from-plan", str(path), "--dry-run")
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert [w["key"] for w in report["workflows"]] == ["sequence-landing-page-10-promo"]
    # precheck shares the same plan loader and must not treat _meta as a workflow either
    with patch.object(cli_mod, "_get_internal_client", return_value=type("C", (), {"location_id": LOC})()), \
            patch.object(wb.CampaignBuilder, "precheck",
                         lambda self, loc, wf: {"present": [], "missing": [], "unverified": []}):
        res = CliRunner().invoke(cli, ["--experimental", "--json", "--location-id", LOC,
                                       "workflows", "precheck", "--from-plan", str(path)])
    assert res.exit_code == 0, res.output
    assert list(json.loads(res.output)["workflows"]) == ["sequence-landing-page-10-promo"]


@pytest.mark.parametrize("kind", list(emit.launch_profiles.PLANNED_KINDS))
def test_every_launch_family_plan_is_refused_with_a_pointer(tmp_path, kind):
    fam = emit.FAMILIES[kind]
    plan = emit.build_plan({"answers": {"objective": fam["objective"],
                                        "sequence_position": fam["sequence_position"]}},
                           _emails_doc(fam))
    assert plan["_meta"]["profile"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    for extra in (["--dry-run"], []):
        result = CliRunner().invoke(cli, ["--experimental", "--json", "--location-id", LOC,
                                          "workflows", "build", "--from-plan", str(path), *extra])
        assert result.exit_code == 2, result.output
        assert "--from-automation-build" in result.output


# ---- rows 3 + 6: custom-fields / pipelines create ------------------------------

class Api:
    """Fake ghl_client: records calls, serves a stored record on read-back."""

    def __init__(self, post_answer, read_answer=None, read_fails=False):
        self.posts, self.gets = [], []
        self.post_answer, self.read_answer, self.read_fails = post_answer, read_answer, read_fails

    def post(self, path, data=None, version=None):
        self.posts.append((path, data))
        return self.post_answer

    def get(self, path, params=None, version=None):
        self.gets.append((path, params))
        if self.read_fails:
            raise RuntimeError("boom")
        return self.read_answer


def test_custom_field_create_reads_back():
    fake = Api({"customField": {"id": "CF1"}},
               {"customField": {"id": "CF1", "name": "Purchased", "dataType": "CHECKBOX"}})
    with patch.object(cli_mod.api, "post", fake.post), patch.object(cli_mod.api, "get", fake.get):
        result = run("custom-fields", "create", "--name", "Purchased", "--data-type", "checkbox")
    assert result.exit_code == 0, result.output
    path, body = fake.posts[0]
    assert path == "/custom-fields/" and body["locationId"] == LOC and body["dataType"] == "CHECKBOX"
    assert fake.gets == [("/custom-fields/CF1", None)]
    assert json.loads(result.output)["verified"] is True


def test_custom_field_readback_mismatch_or_failure_exits_3_and_never_reposts():
    fake = Api({"id": "CF1"}, {"id": "CF1", "name": "Other", "dataType": "TEXT"})
    with patch.object(cli_mod.api, "post", fake.post), patch.object(cli_mod.api, "get", fake.get):
        assert run("custom-fields", "create", "--name", "Purchased").exit_code == 3
    fake = Api({"id": "CF1"}, read_fails=True)
    with patch.object(cli_mod.api, "post", fake.post), patch.object(cli_mod.api, "get", fake.get):
        assert run("custom-fields", "create", "--name", "Purchased").exit_code == 3
    assert len(fake.posts) == 1 and len(fake.gets) == 2  # one write, one read-only retry


def test_pipeline_create_reads_back_name_and_ordered_stages():
    stages = [{"name": "New", "position": 0}, {"name": "Bought", "position": 1}]
    fake = Api({"id": "PL1"}, {"pipeline": {"id": "PL1", "name": "Buyers", "stages": stages[::-1]}})
    with patch.object(cli_mod.api, "post", fake.post), patch.object(cli_mod.api, "get", fake.get):
        result = run("pipelines", "create", "--name", "Buyers", "--stage", "New", "--stage", "Bought")
    assert result.exit_code == 0, result.output
    path, body = fake.posts[0]
    assert path == "/opportunities/pipelines" and body["stages"] == stages
    assert fake.gets[0][0] == "/opportunities/pipelines/PL1"
    wrong = Api({"id": "PL1"}, {"id": "PL1", "name": "Buyers", "stages": stages[:1]})
    with patch.object(cli_mod.api, "post", wrong.post), patch.object(cli_mod.api, "get", wrong.get):
        assert run("pipelines", "create", "--name", "Buyers", "--stage", "New",
                   "--stage", "Bought").exit_code == 3


@pytest.mark.parametrize("args", [["custom-fields", "create", "--name", "X"],
                                  ["pipelines", "create", "--name", "X", "--stage", "A"]])
def test_creates_are_gated_by_the_safety_gate(monkeypatch, args):
    monkeypatch.setenv("CAF_ALLOWED_LOCATION_IDS", "OTHER")
    with patch("cli_anything.gohighlevel.utils.ghl_client.requests.post") as mock_post:
        result = run(*args)
    assert result.exit_code != 0
    mock_post.assert_not_called()


# ---- row 3: payments through shared-utils/ghl/products_prices.py ---------------

class Catalog:
    """Stateful fake GHL products API behind ghl_client (read-first routes included)."""

    def __init__(self, price_amount=49.0):
        self.calls = []
        self.price_amount = price_amount
        self.products, self.prices = [], []

    def post(self, path, data=None, version=None):
        self.calls.append(("POST", path, data))
        if path == "/products/":
            created = {"_id": "P1", "name": data["name"], "productType": data["productType"],
                       "locationId": data["locationId"]}
            self.products.append(created)
            return {"_id": "P1"}
        created = {**data, "_id": "PR1", "product": "P1", "amount": self.price_amount}
        self.prices.append(created)
        return {"_id": "PR1"}

    def get(self, path, params=None, version=None):
        self.calls.append(("GET", path, params))
        route = path.split("?")[0]
        if route == "/products/":
            return {"products": list(self.products), "total": len(self.products)}
        if route == "/products/P1/price":
            return {"prices": list(self.prices), "total": len(self.prices)}
        if route == "/products/P1":
            return dict(self.products[0])
        return dict(self.prices[0])  # /products/P1/price/PR1

    def routes(self):
        return [(c[0], c[1].split("?")[0]) for c in self.calls]


# TEST-ONLY approval: the CLI's verify hook is faked with the shape approval_record.verify
# returns; no approval authority is contacted and nothing here is a real approval.
APPROVAL = ["--approval-id", "TEST-ONLY-APPROVAL", "--plan-sha256", "0" * 64]


@pytest.fixture
def approved(monkeypatch):
    monkeypatch.setattr(cli_mod, "_verify_automation_write", lambda *a: {
        "ok": True, "approval_id": "TEST-ONLY-APPROVAL", "kind": "automation_write",
        "client_identity": "test-only-client", "expires_at": "2999-01-01T00:00:00+00:00",
        "authority": "local-test-record", "test_only": True})


def _patched(catalog):
    return patch.object(cli_mod.api, "post", catalog.post), patch.object(cli_mod.api, "get", catalog.get)


def test_payments_create_product_and_price_route_through_the_shared_module(approved):
    shared = cli_mod._products_prices()
    assert Path(shared.__file__).resolve() == (REPO / "shared-utils" / "ghl" / "products_prices.py").resolve()
    catalog = Catalog()
    post, get = _patched(catalog)
    with post, get:
        product = run("payments", "create-product", "--name", "Seat", *APPROVAL)
        price = run("payments", "create-price", "--product-id", "P1", "--name", "Seat",
                    "--amount", "4900", *APPROVAL)
    assert product.exit_code == 0 and price.exit_code == 0, product.output + price.output
    assert catalog.routes() == [
        ("GET", "/products/"), ("POST", "/products/"), ("GET", "/products/P1"),
        ("GET", "/products/P1/price"), ("POST", "/products/P1/price"),
        ("GET", "/products/P1/price/PR1")]
    # the shared module's documented API amount (dollars), not the old raw cents
    assert catalog.calls[4][2]["amount"] == 49.0
    assert json.loads(price.output)["amount_minor"] == 4900
    assert json.loads(product.output)["readback"] == "verified"


def test_payments_price_body_is_the_shared_builder_body(approved):
    pp = cli_mod._products_prices()
    catalog = Catalog()
    post, get = _patched(catalog)
    with post, get:
        result = run("payments", "create-price", "--product-id", "P1", "--name", "Seat",
                     "--amount", "4900", *APPROVAL)
    assert result.exit_code == 0, result.output
    post_body = next(c[2] for c in catalog.calls if c[0] == "POST")
    assert post_body == pp.price_request_body(pp.PriceSpec("Seat", LOC, "one_time", "USD", 4900))
    assert post_body["amount"] == 49.0


def test_payments_create_product_twice_creates_once(approved):
    catalog = Catalog()
    post, get = _patched(catalog)
    with post, get:
        first = run("payments", "create-product", "--name", "Seat", *APPROVAL)
        second = run("payments", "create-product", "--name", "Seat", *APPROVAL)
    assert first.exit_code == 0 and second.exit_code == 0, first.output + second.output
    assert [c for c in catalog.routes() if c == ("POST", "/products/")] == [("POST", "/products/")]
    assert json.loads(second.output)["readback"] == "reconciled"


def test_payments_create_refused_without_approval_id_posts_nothing():
    catalog = Catalog()
    post, get = _patched(catalog)
    with post, get:
        product = run("payments", "create-product", "--name", "Seat")
        price = run("payments", "create-price", "--product-id", "P1", "--name", "Seat",
                    "--amount", "4900")
    assert product.exit_code != 0 and price.exit_code != 0
    assert [c for c in catalog.calls if c[0] == "POST"] == []


def test_payments_create_product_help_carries_no_zhc_hint():
    assert "ZHC" not in run("payments", "create-product", "--help").output


def test_payments_recurring_price_sends_interval_count_and_trial(approved):
    catalog = Catalog()
    post, get = _patched(catalog)
    with post, get:
        result = run("payments", "create-price", "--product-id", "P1", "--name", "Seat",
                     "--amount", "4900", "--type", "recurring", "--interval", "month",
                     "--interval-count", "3", "--trial-days", "7", *APPROVAL)
    assert result.exit_code == 0, result.output
    body = next(c[2] for c in catalog.calls if c[0] == "POST")
    assert body["recurring"] == {"interval": "month", "intervalCount": 3} and body["trialPeriod"] == 7


def test_payments_price_readback_mismatch_fails(approved):
    catalog = Catalog()
    post, get = _patched(catalog)
    real_post = catalog.post

    def wrong_amount(path, data=None, version=None):
        out = real_post(path, data, version)
        if path.endswith("/price"):
            catalog.prices[0]["amount"] = 4900.0  # the old raw-cents bug read back
        return out

    with patch.object(cli_mod.api, "post", wrong_amount), get:
        result = run("payments", "create-price", "--product-id", "P1", "--name", "Seat",
                     "--amount", "4900", *APPROVAL)
    assert result.exit_code == 1


def test_payments_image_url_is_refused_not_dropped():
    catalog = Catalog()
    with patch.object(cli_mod.api, "post", catalog.post), patch.object(cli_mod.api, "get", catalog.get):
        result = run("payments", "create-product", "--name", "Seat", "--image-url", "https://x/y.png")
    assert result.exit_code == 2 and catalog.calls == []
