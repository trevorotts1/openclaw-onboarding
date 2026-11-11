"""The one billing vocabulary (issue 70, D-D): one CHECKOUT_BILLING table, every importer reads it.

Before billing.py, `installment` was legal in Skills 49, 71 and 78 and impossible in 79 and 83, and a client
learned it at checkout. Now the table and the client-facing refusal sentence live once, installment and trial
are refused when the plan is built, and the translation to Skill 79's vocabulary is one function.

Run: python3 -m pytest shared-utils/signature_launch_contract/tests/test_billing.py -q
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
CONTRACT = HERE.parents[1]
REPO = HERE.parents[3]
sys.path.insert(0, str(CONTRACT))
import billing  # noqa: E402
import offer_mapper as om  # noqa: E402


def test_the_translation_table_is_the_one_the_offer_mapper_uses():
    shared = sys.modules["signature_launch_billing"]  # the module the importers load by path
    assert om._billing_vocab is shared
    assert om.CHECKOUT_BILLING is shared.CHECKOUT_BILLING and om.CHECKOUT_BILLING == billing.CHECKOUT_BILLING
    assert om.BILLING_TYPES is shared.BILLING_TYPES


def test_every_record_billing_type_has_exactly_one_answer():
    assert set(billing.CHECKOUT_BILLING) == set(billing.BILLING_TYPES)
    assert billing.checkout_billing("one_time") == "one_time"
    assert billing.checkout_billing("recurring") == "recurring"
    assert billing.checkout_billing("trial") == "trial_then_recurring"  # 79 names it differently


def test_installment_and_unknown_types_are_refused_by_name():
    for bad in ("installment", "monthly", None, ""):
        with pytest.raises(billing.BillingError) as ctx:
            billing.checkout_billing(bad)
        assert ctx.value.code == "AF-CHECKOUT-BILLING"


def test_the_plan_time_refusal_is_installment_and_trial_with_the_shared_sentence():
    assert set(billing.PLAN_TIME_REFUSED) == {"installment", "trial"}
    for refused in billing.PLAN_TIME_REFUSED:
        said = billing.plan_time_refusal(refused)
        assert said == f"{refused!r}: payment plans are not supported in this release"
    for fine in ("one_time", "recurring", None):
        assert billing.plan_time_refusal(fine) is None


def test_the_offer_mapper_still_refuses_installment_at_checkout_by_the_same_table():
    record = {"plan_approval_ref": "ref", "tenant_id": "t", "location_id": "l", "launch_id": "L", "revision": 1,
              "brand_ref": "b", "test_only": True,
              "offers": [{"offer_id": "M", "entitlement_ids": ["m"], "native_product_id": None, "prices": [{
                  "price_choice_id": "M-USD", "currency": "USD", "amount_minor": 100, "billing_type": "installment",
                  "native_price_id": None, "schedule": [], "approval_status": "approved"}]}]}
    ctx = {k: "x" for k in om.CHECKOUT_CONTEXT}
    with pytest.raises(om.MapperError) as err:
        om.record_to_checkout_request(record, "M", checkout_mode="combined_single_offer", **ctx)
    assert err.value.code == "AF-CHECKOUT-BILLING"


def _definitions(root, pattern):
    hits = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or "__pycache__" in path.parts or path.name.startswith("test_"):
            continue
        hits += [path for _ in re.finditer(pattern, path.read_text(encoding="utf-8", errors="replace"), re.M)]
    return hits


def test_there_is_one_checkout_billing_table_and_one_refusal_sentence_in_the_launch_family():
    roots = [REPO / "shared-utils" / "signature_launch_contract"]
    roots += [REPO / d for d in ("49-signature-funnel/scripts", "83-black-friday-launcher/launcher_core",
                                 "83-black-friday-launcher/routes")]
    tables = [p for root in roots for p in _definitions(root, r'^CHECKOUT_BILLING\s*=\s*\{')]
    assert [p.name for p in tables] == ["billing.py"]
    sentences = [p for root in roots for p in _definitions(root, r'"payment plans are not supported in this release"')]
    assert [p.name for p in sentences] == ["billing.py"]


@pytest.mark.parametrize("path", ["49-signature-funnel/scripts/launch_plan.py",
                                  "83-black-friday-launcher/launcher_core/intake.py",
                                  "83-black-friday-launcher/launcher_core/checkout_instances.py",
                                  "shared-utils/signature_launch_contract/offer_mapper.py"])
def test_each_importer_reads_the_shared_module(path):
    text = (REPO / path).read_text(encoding="utf-8")
    assert "billing" in text and ("billing.py" in text or "billing_module" in text), path
