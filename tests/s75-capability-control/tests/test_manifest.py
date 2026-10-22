import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests._support import fixture  # noqa: E402

from capability_control.manifest import (  # noqa: E402
    DispatchReceipt, effort_claims_findings, resolve_manifest,
)

BUILDER = "openrouter/xiaomi/mimo-v2.6-pro"
QC = "openrouter/z-ai/glm-5.3"


def build_catalogs():
    """Map captured fixtures onto the manifest's two catalog views.

    authoritative: OpenRouter /api/v1/models rows (supported_parameters).
    host: installed 9Router /v1/models rows (capability flags).
    """
    auth_raw = fixture("provider-catalog.openrouter.json")["models"]
    host_raw = fixture("host-catalog.9router.json")["models"]
    authoritative = {}
    for row in auth_raw.values():
        # openrouter catalog ids are provider-local; the host routes them as openrouter/<id>
        authoritative["openrouter/" + row["id"]] = row
    host = {row["id"]: row for row in host_raw}
    return authoritative, host


class TestManifestReconciliation(unittest.TestCase):
    """Acceptance: the manifest reconciles catalog, allowlist, provider entries
    and cache versions, with actual host dispatch proving the chosen model."""

    def setUp(self):
        self.authoritative, self.host = build_catalogs()
        self.router = fixture("router-surfaces.db.json")
        self.cache_meta = fixture("session-cache.model-catalog.json")["cache_meta"]
        self.surfaces = {
            "selectable": [BUILDER, QC],
            "allowlist": {
                "enabled": [BUILDER, QC],
                "disabled": self.router["kv"]["disabledModels"],
                "aliases": {"mimo-pro": BUILDER},
            },
            "provider_entries": [
                {"entry_id": "providerThinking:openrouter", "provider": "openrouter", "thinking_mode": "high"},
            ],
            "role_bindings": [
                {"role": "builder", "model_id": BUILDER, "requested_effort": "none"},
                {"role": "qc", "model_id": QC, "requested_effort": "high"},
            ],
            "scheduler_jobs": [{"job_id": "keepalive-15min", "schedule": "*/15 * * * *", "model_id": BUILDER}],
            "caches": [{
                "cache_id": "model-catalog.json",
                "source_revision": str(self.cache_meta.get("etag")),
                "fetched_at": str(self.cache_meta.get("syncedAt")),
                "refresh_path": "python3 -I tools/capture_fixtures.py --out fixtures/",
                "version": self.cache_meta.get("v"),
            }],
            "authoritative_revision": "live-2026-10-22",
        }

    def test_manifest_resolves_models_with_honest_effort_flags(self):
        m = resolve_manifest("s75-w04-u2/capability-config/v1", self.authoritative, self.host, self.surfaces)
        builder = m.model(BUILDER)
        qc = m.model(QC)
        self.assertIsNotNone(builder)
        self.assertIsNotNone(qc)
        # MiMo 2.6 Pro: reasoning WITHOUT an effort selector (both catalogs agree)
        self.assertTrue(builder.reasoning)
        self.assertFalse(builder.effort_selector)
        # GLM 5.3: reasoning WITH an effort selector
        self.assertTrue(qc.reasoning)
        self.assertTrue(qc.effort_selector)
        self.assertEqual([f.code for f in m.findings if f.code == "UNKNOWN_MODEL"], [])

    def test_cache_rows_carry_provenance_and_stale_is_flagged(self):
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        row = m.caches[0]
        self.assertTrue(row["source_revision"])
        self.assertTrue(row["fetched_at"])
        self.assertTrue(row["refresh_path"])
        self.assertIn("CACHE_STALE", [f.code for f in m.findings])  # cache revision != live capture revision

    def test_cache_without_refresh_path_is_flagged(self):
        self.surfaces["caches"][0] = {"cache_id": "session-ui", "source_revision": "r", "fetched_at": "t"}
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        self.assertIn("CACHE_PROVENANCE_INCOMPLETE", [f.code for f in m.findings])

    def test_allowlist_entries_must_resolve(self):
        self.surfaces["allowlist"]["enabled"].append("openrouter/ghost/model")
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        self.assertIn("ALLOWLIST_DRIFT", [f.code for f in m.findings])

    def test_provider_entry_drift_flagged(self):
        self.surfaces["provider_entries"].append({"entry_id": "providerThinking:ghost", "provider": "ghost-provider"})
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        self.assertIn("PROVIDER_ENTRY_DRIFT", [f.code for f in m.findings])

    def test_scheduler_job_pin_must_resolve(self):
        self.surfaces["scheduler_jobs"].append({"job_id": "stale-cron", "schedule": "* * * * *", "model_id": "openrouter/ghost"})
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        self.assertIn("SCHEDULER_JOB_DRIFT", [f.code for f in m.findings])

    def test_role_verified_only_by_actual_host_dispatch(self):
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        # a label alone never verifies
        self.assertEqual(sorted(m.unverified_roles()), ["builder", "qc"])
        result = m.verify_dispatch(DispatchReceipt(
            role="builder", requested_model=BUILDER, resolved_model=BUILDER,
            response_model=BUILDER, router_request_id="req-1", timestamp="2026-10-22T00:00:00Z"))
        self.assertEqual(result.code, "DISPATCH_VERIFIED")
        self.assertEqual(m.unverified_roles(), ["qc"])
        # provider-local echo of the bound route counts (openrouter/x/y echoes x/y)
        m2 = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        result = m2.verify_dispatch(DispatchReceipt(
            role="builder", requested_model=BUILDER, resolved_model=BUILDER,
            response_model="xiaomi/mimo-v2.6-pro", router_request_id="gen-1", timestamp="t"))
        self.assertEqual(result.code, "DISPATCH_VERIFIED")
        # a mismatched response model is never proof
        result = m.verify_dispatch(DispatchReceipt(
            role="qc", requested_model=QC, resolved_model="some/other-model",
            response_model="some/other-model", router_request_id="req-2", timestamp="t"))
        self.assertEqual(result.code, "DISPATCH_MISMATCH")
        self.assertEqual(m.unverified_roles(), ["qc"])

    def test_combo_effort_annotations_are_checked_against_the_catalog(self):
        # Live router combos annotate per-model effort, e.g. "model(max)".
        claimed = {}
        for combo in self.router["combos"]:
            for entry in combo["models"]:
                match = re.match(r"^(.+)\((\w+)\)$", entry.strip())
                if match:
                    claimed.setdefault(match.group(1), match.group(2))
        self.assertIn(BUILDER, claimed, "captured combos should claim effort for the builder model")
        m = resolve_manifest("s1", self.authoritative, self.host, self.surfaces)
        findings = effort_claims_findings(m, claimed)
        flagged = [f.detail for f in findings if f.code == "UNSUPPORTED_EFFORT_CLAIM"]
        # MiMo 2.6 Pro claims (high)/(max) in live combos but has no effort selector -> fabrication
        self.assertTrue(any("claimed for %s" % BUILDER in d for d in flagged), flagged)
        # GLM 5.3 has a real selector -> its claims are not fabrication
        self.assertFalse(any("claimed for %s" % QC in d for d in flagged), flagged)


if __name__ == "__main__":
    unittest.main()
