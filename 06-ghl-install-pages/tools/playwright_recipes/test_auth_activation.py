"""Post-seed location activation contracts; synthetic identities, no network."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import ghl_auth as ga
import ghl_auth_activation as activation
from playwright_recipes.recipe_cli import compile_recipe
from playwright_recipes.skill6_playwright import Stop, execute, validate_job
from playwright_recipes import skill6_playwright as core

LOC = "LOC_FIXTURE"
ORIGIN = "https://app.convertandflow.com"
URL = ORIGIN + "/v2/location/" + LOC + "/form-builder-v2/FORM_FIXTURE"
IDENTITY = {"userId": "seed-user", "companyId": "seed-company", "locationId": ""}
TARGET = {"location_name": "Fixture Account", "start_url": URL,
          "expected_builder_title": "ZHC Fixture Form"}


class Node:
    def __init__(self, page, kind, name=None):
        self.page, self.kind, self.name = page, kind, name

    def count(self):
        p = self.page
        if self.kind == "workspace": return p.workspace_count
        if self.kind == "group": return p.group_count if self.name == p.account_name else 0
        if self.kind == "accounts": return 1
        if self.kind == "list": return 1
        if self.kind == "account": return p.directory.count(self.name)
        if self.kind == "links": return len(p.links)
        if self.kind == "password_detection": return int(p.password)
        if self.kind == "frame": return int(self.name == p.frame_name)
        if self.kind == "all_frames": return p.builder_frame_count
        if self.kind == "title": return 1
        return 1

    def wait_for(self, **kw):
        self.page.waits.append((self.kind, self.name))
        if self.count() != 1: raise RuntimeError("synthetic absent control")

    def is_visible(self): return self.count() == 1

    def get_by_role(self, role, *, name=None, exact=None):
        kind = {("workspace", "group"): "group", ("accounts", "list"): "list",
                ("list", "button"): "account", ("builder", "textbox"): "title"}.get((self.kind, role))
        assert kind, (self.kind, role)
        return Node(self.page, kind, name)

    def get_by_text(self, name, exact=None): return Node(self.page, "title", name)

    def locator(self, selector):
        assert self.kind == "workspace" and selector == "a[href]"
        return Node(self.page, "links")

    def nth(self, index):
        if self.kind == "links": return Link(self.page.links[index])
        return self

    def input_value(self): return self.page.builder_title


class Link:
    def __init__(self, href): self.href = href
    def get_attribute(self, name):
        assert name == "href"
        return self.href


class Page:
    def __init__(self):
        self.url = ORIGIN + "/login"
        self.calls, self.waits = [], []
        self.workspace_count = self.group_count = 1
        self.account_name = "Fixture Account"
        self.directory = [self.account_name]
        self.links = ["/v2/location/LOC_FIXTURE/dashboard", "/v2/location/LOC_FIXTURE/form-builder/main"]
        self.password = False
        self.frame_name = "form-builder-app"
        self.builder_frame_count = 1
        self.builder_title = "ZHC Fixture Form"
        self.auth_states = []
        self.auth_identity = dict(IDENTITY)
        self.auth_identities = []
        self.route_override = None

    def evaluate(self, js, arg=None):
        if js == ga.PLAYWRIGHT_SEED_JS:
            self.calls.append("seed")
            return dict(IDENTITY)
        assert js == activation.ACTIVATE_SPA_JS
        self.calls.append("auth")
        if self.auth_states:
            state = self.auth_states.pop(0)
            if state != "OK": return {"state": state}
        if arg["target_path"] is not None:
            self.url = ORIGIN + arg["target_path"]
        return {"state": "OK", **(self.auth_identities.pop(0) if self.auth_identities else self.auth_identity)}

    def wait_for_url(self, expected, **kw):
        if self.route_override:
            self.url = self.route_override
        if self.url != expected: raise RuntimeError("synthetic routing refusal")

    def locator(self, selector):
        if selector == 'input[type="password"]': return Node(self, "password_detection")
        if selector == 'iframe[name$="-builder-app"],iframe[name="funnel-builder"]': return Node(self, "all_frames")
        return Node(self, "frame", selector.split('"')[1])

    def get_by_role(self, role, *, name, exact=True):
        if (role, name) == ("region", "Workspace navigation"): return Node(self, "workspace")
        if (role, name) == ("navigation", "Accounts"): return Node(self, "accounts")
        raise AssertionError((role, name))

    def frame_locator(self, selector): return Node(self, "builder")


class ActivationTests(unittest.TestCase):
    def run_bridge(self, page, **kw):
        context = type("Context", (), {"pages": [page]})()
        return ga.bridge_seed_into_context(context, {}, expected_location_id=LOC,
            app_origin=ORIGIN, activation_target=TARGET, **kw)

    def test_redirected_login_route_is_recovered_only_after_actual_seed_and_protected_proof(self):
        page = Page()
        receipt = self.run_bridge(page)
        self.assertTrue(receipt["ok"])
        self.assertIs(receipt.page, page)
        self.assertEqual(page.calls[0], "seed")
        self.assertEqual(receipt["identity"]["locationId"], LOC)
        self.assertTrue(receipt["activation_proof"]["target_verified"])
        self.assertEqual(page.url, URL)
        self.assertNotIn("Fixture Account", json.dumps(receipt))

    def test_default_bridge_does_not_activate_or_change_missing_location_refusal(self):
        page = Page()
        with self.assertRaisesRegex(ga.AuthBridgeError, "location identity could NOT"):
            ga.bridge_seed_into_context(type("Context", (), {"pages": [page]})(), {},
                expected_location_id=LOC, app_origin=ORIGIN)
        self.assertEqual(page.calls, ["seed"])

    def test_legacy_identity_hook_cannot_skip_the_actual_seed(self):
        page = Page()
        with self.assertRaises(ga.AuthBridgeError):
            self.run_bridge(page, identity_fetcher=lambda _: IDENTITY)
        self.assertEqual(page.calls, [])

    def test_wrong_seed_location_or_company_is_terminal_before_activation(self):
        for identity in ({**IDENTITY, "locationId": "FOREIGN"}, {**IDENTITY, "companyId": "foreign"}):
            with self.subTest(identity=identity):
                page = Page()
                with patch.object(page, "evaluate", return_value=identity):
                    with self.assertRaises(ga.AuthBridgeError):
                        self.run_bridge(page, expected_company_id="seed-company")

    def test_cached_foreign_browser_identity_cannot_be_blessed_by_matching_account_markup(self):
        for key in ("userId", "companyId"):
            page = Page()
            page.auth_identity[key] = "foreign"
            with self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)
            self.assertEqual(page.calls, ["seed", "auth"])

    def test_foreign_location_is_terminal_at_every_same_session_identity_read(self):
        for read_index in range(4):
            for reported in ({"locationId": "FOREIGN"}, {"location_id": "FOREIGN"},
                             {"locationId": LOC, "location_id": "FOREIGN"},
                             {"locationId": [LOC]}, {"locationId": False}):
                with self.subTest(read_index=read_index, reported=reported):
                    page = Page()
                    page.auth_identities = [dict(IDENTITY) for _ in range(read_index)] + [
                        {**IDENTITY, **reported}]
                    with self.assertRaisesRegex(ga.AuthBridgeError, "different or invalid location"):
                        self.run_bridge(page)
                    self.assertEqual(page.calls, ["seed"] + ["auth"] * (read_index + 1))

    def test_expected_and_absent_location_reads_remain_bound_to_protected_scope(self):
        for seed in (dict(IDENTITY), {**IDENTITY, "locationId": LOC}):
            page = Page()
            page.auth_identities = [
                {**IDENTITY, "locationId": LOC}, dict(IDENTITY),
                {**IDENTITY, "location_id": LOC}, dict(IDENTITY)]
            original_evaluate = page.evaluate
            def evaluate(js, arg=None):
                if js == ga.PLAYWRIGHT_SEED_JS:
                    page.calls.append("seed")
                    return dict(seed)
                return original_evaluate(js, arg)
            with patch.object(page, "evaluate", side_effect=evaluate):
                receipt = self.run_bridge(page)
            self.assertTrue(receipt["ok"])
            self.assertEqual(receipt["identity"]["locationId"], LOC)
            self.assertEqual(page.calls, ["seed"] + ["auth"] * 4)

    def test_conflicting_seed_location_aliases_stop_before_activation(self):
        page = Page()
        with patch.object(page, "evaluate", return_value={
                **IDENTITY, "locationId": LOC, "location_id": "FOREIGN"}):
            with self.assertRaisesRegex(ga.AuthBridgeError, "different or invalid location"):
                self.run_bridge(page)
        self.assertEqual(page.calls, [])

    def test_missing_or_duplicate_protected_account_controls_refuse(self):
        for change in ({"workspace_count": 0}, {"group_count": 2}, {"account_name": "Different Account"},
                       {"directory": []}, {"directory": ["Fixture Account", "Fixture Account"]}):
            page = Page()
            for key, value in change.items(): setattr(page, key, value)
            with self.subTest(change=change), self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)

    def test_url_only_or_foreign_navigation_is_not_scope_proof(self):
        for links in ([], ["/v2/location/LOC_FIXTURE/dashboard"],
                      ["/v2/location/FOREIGN/dashboard", "/v2/location/LOC_FIXTURE/form-builder/main"],
                      ["https://foreign.invalid/v2/location/LOC_FIXTURE/dashboard", "/v2/location/LOC_FIXTURE/form-builder/main"]):
            page = Page()
            page.links = links
            with self.subTest(links=links), self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)

    def test_login_wall_route_race_wrong_frame_and_wrong_object_refuse(self):
        for change in ({"password": True}, {"route_override": ORIGIN + "/login"},
                       {"frame_name": "survey-builder-app"}, {"builder_frame_count": 2},
                       {"builder_title": "Different Form"}):
            page = Page()
            for key, value in change.items(): setattr(page, key, value)
            with self.subTest(change=change), self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)

    def test_auth_or_scope_refusal_is_not_retried(self):
        for state in ("AUTH_REFUSED", "USER_READ_REFUSED", "IDENTITY_MISMATCH", "SPA_CONTRACT_UNAVAILABLE"):
            page = Page()
            page.auth_states = [state]
            with self.subTest(state=state), self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)
            self.assertEqual(page.calls, ["seed", "auth"])

    def test_identity_change_after_dashboard_proof_refuses_before_editor(self):
        page = Page()
        page.auth_states = ["OK", "IDENTITY_MISMATCH"]
        with self.assertRaises(ga.AuthBridgeError): self.run_bridge(page)
        self.assertNotEqual(page.url, URL)

    def test_invalid_contract_refuses_before_seed(self):
        for target in ({**TARGET, "start_url": "https://foreign.invalid/v2/location/LOC_FIXTURE/dashboard"},
                       {**TARGET, "start_url": ORIGIN + "/v2/location/FOREIGN/dashboard"},
                       {**TARGET, "start_url": URL + "?token=forbidden"},
                       {**TARGET, "expected_builder_title": ""}, {**TARGET, "unexpected": True}):
            page = Page()
            context = type("Context", (), {"pages": [page]})()
            with self.subTest(target=target), self.assertRaises(ga.AuthBridgeError):
                ga.bridge_seed_into_context(context, {}, expected_location_id=LOC,
                    app_origin=ORIGIN, activation_target=target)
            self.assertEqual(page.calls, [])

    def test_recipe_opt_in_is_preserved_and_validated_before_execution(self):
        data = {"location_id": LOC, "location_name": "Fixture Account", "start_url": URL,
                "settings": {"save_progress": False},
                "auth_activation": {"expected_builder_title": "ZHC Fixture Form"}}
        job = validate_job(compile_recipe("forms.settings", data), Path("."))
        self.assertEqual(job["auth_activation"], data["auth_activation"])
        for value in (None, True, {}, {"expected_builder_title": "ZHC", "skip_scope": True}):
            with self.subTest(value=value), self.assertRaises(Stop):
                validate_job({**job, "auth_activation": value}, Path("."))

    def test_attached_browser_cannot_opt_into_fresh_seed_activation(self):
        with patch.dict("os.environ", {"GHL_MANAGED_CDP_URL": "http://localhost:9222"}):
            with self.assertRaisesRegex(Stop, "fresh owned"):
                execute({"auth_activation": {}}, Path("unused"))

    def test_mint_rejects_replacement_hook_before_credential_or_network_work(self):
        page = Page()
        context = type("Context", (), {"pages": [page]})()
        calls = []
        with self.assertRaises(ga.AuthBridgeError):
            ga.mint_and_bridge(context, "fixture", "unused", env={},
                expected_location_id=LOC, app_origin=ORIGIN,
                activation_target=TARGET, identity_fetcher=lambda _: IDENTITY,
                seed_runner=lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        self.assertEqual(page.calls, [])

    def test_activation_auth_refusal_cannot_trigger_the_expired_reseed_branch(self):
        page = Page()
        page.auth_states = ["AUTH_REFUSED"]
        context = type("Context", (), {"pages": [page]})()
        calls = []
        def mint(session, out, env):
            calls.append(session)
            Path(out).write_text('{}')
            return 0
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ga.AuthBridgeError):
                ga.mint_and_bridge(context, "fixture", str(Path(root) / "seed.json"),
                    env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "AgNt" + "r3fr3sh" * 6},
                    expected_location_id=LOC, app_origin=ORIGIN,
                    activation_target=TARGET, seed_runner=mint)
        self.assertEqual(calls, ["fixture"])
        self.assertEqual(page.calls, ["seed", "auth"])


class OwnedExecutionTests(unittest.TestCase):
    def run_owned(self, opted_in, *, verified=True):
        page = Page()
        page.context = object()
        navigation = []
        def go(url, **kwargs):
            navigation.append(url)
            page.url = url
        page.goto = go
        class Managed:
            session = "fixture-session"
            pages = [page]
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def assert_alive(self): pass
        captured = []
        def mint(context, session, seed_path, **kwargs):
            captured.append(kwargs)
            return ga.BridgeReceipt({"ok": True,
                **({"activation_proof": {"target_verified": verified}} if opted_in else {})}, page=page)
        job = {"location_id": LOC, "location_name": "Fixture Account", "start_url": URL}
        if opted_in:
            job['auth_activation'] = {"expected_builder_title": "ZHC Fixture Form"}
        with tempfile.TemporaryDirectory() as root:
            with patch.dict("os.environ", {"GHL_MANAGED_CDP_URL": ""}), \
                    patch("browser_manager.PlaywrightSession", Managed), \
                    patch.object(ga, "mint_and_bridge", side_effect=mint), \
                    patch.object(core, "run_on_page", return_value={"status": "fixture-only"}) as runner:
                if opted_in and not verified:
                    with self.assertRaisesRegex(Stop, "verify this exact"):
                        execute(job, Path(root))
                    runner.assert_not_called()
                else:
                    self.assertEqual(execute(job, Path(root)), {"status": "fixture-only"})
                    runner.assert_called_once_with(page, job, Path(root))
        return navigation, captured

    def test_opted_in_execution_does_not_reload_or_navigate_after_same_spa_proof(self):
        navigation, captured = self.run_owned(True)
        self.assertEqual(navigation, [URL])
        self.assertEqual(captured[0]['expected_location_id'], LOC)
        self.assertEqual(captured[0]['activation_target'], TARGET)

    def test_default_execution_preserves_the_existing_bridge_contract(self):
        navigation, captured = self.run_owned(False)
        self.assertEqual(navigation, [URL, URL])
        self.assertNotIn('activation_target', captured[0])

    def test_missing_activation_receipt_cannot_reach_editor_writes(self):
        navigation, _ = self.run_owned(True, verified=False)
        self.assertEqual(navigation, [URL])


class ActualActivationJavaScript(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required for actual SPA script contract")
    def test_actual_script_binds_user_company_and_stops_scope_refusal_without_retry(self):
        program = r"""
const fs = require('fs');
const script = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const outputs = [];
  for (const mode of ['ok', 'foreign-user', 'foreign-company', 'auth403', 'user403', 'auth-hung', 'user-hung']) {
    const calls = [], paths = [];
    const nativeTimeout = global.setTimeout;
    const requestedTimeouts = [];
    if (mode.endsWith('-hung')) global.setTimeout = (callback, ms) => {
      requestedTimeouts.push(ms); return nativeTimeout(callback, 0);
    };
    const store = {dispatch: async name => {
      calls.push(name);
      if ((mode === 'auth403' && name === 'auth/get') || (mode === 'user403' && name === 'user/get')) throw Error('403 SECRET');
      if ((mode === 'auth-hung' && name === 'auth/get') || (mode === 'user-hung' && name === 'user/get')) return new Promise(() => {});
      return {userId: mode === 'foreign-user' ? 'foreign' : 'seed-user', companyId: mode === 'foreign-company' ? 'foreign' : 'seed-company', apiKey: 'PRIVATE-NEVER-RETURN'};
    }};
    const router = {push: async spec => paths.push(spec.path)};
    global.document = {querySelector: () => ({__vue_app__: {config: {globalProperties: {$store: store, $router: router}}}})};
    const result = await eval('(' + script + ')')({user_id: 'seed-user', company_id: 'seed-company', location_id: 'LOC_FIXTURE', target_path: '/v2/location/LOC_FIXTURE/dashboard'});
    global.setTimeout = nativeTimeout;
    outputs.push({mode, calls, paths, result, requestedTimeouts});
  }
  process.stdout.write(JSON.stringify(outputs));
})().catch(() => process.exit(1));
"""
        result = subprocess.run([shutil.which("node"), "-e", program], input=json.dumps(activation.ACTIVATE_SPA_JS),
            capture_output=True, text=True, timeout=15, check=True)
        self.assertNotIn("PRIVATE-NEVER-RETURN", result.stdout)
        self.assertNotIn("SECRET", result.stdout)
        outputs = json.loads(result.stdout)
        self.assertEqual(outputs[0]["result"]["state"], "OK")
        self.assertEqual(outputs[0]["paths"], ["/v2/location/LOC_FIXTURE/dashboard"])
        for entry in outputs[1:]:
            self.assertNotEqual(entry["result"]["state"], "OK")
            self.assertEqual(entry["paths"], [])
            self.assertEqual(entry["calls"].count("auth/get"), 1)
            if entry["mode"].endswith("-hung"):
                self.assertTrue(entry["requestedTimeouts"])
                self.assertEqual(set(entry["requestedTimeouts"]), {10000})

    @unittest.skipUnless(shutil.which("node"), "Node is required for actual SPA script contract")
    def test_actual_script_preserves_location_and_rejects_foreign_read_or_router_mutation(self):
        program = r"""
const fs = require('fs');
const script = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  const outputs = [];
  const modes = ['missing', 'expected-auth', 'expected-user', 'foreign-auth',
    'foreign-snake-auth', 'conflicting-auth', 'invalid-auth', 'foreign-user',
    'mutated-auth', 'mutated-user'];
  for (const mode of modes) {
    const calls = [], paths = [];
    const user = {userId: 'seed-user', companyId: 'seed-company', apiKey: 'PRIVATE-NEVER-RETURN'};
    const details = {};
    if (mode === 'expected-auth') user.locationId = 'LOC_FIXTURE';
    if (mode === 'expected-user') details.location_id = 'LOC_FIXTURE';
    if (mode === 'foreign-auth') user.locationId = 'FOREIGN';
    if (mode === 'foreign-snake-auth') user.location_id = 'FOREIGN';
    if (mode === 'conflicting-auth') {user.locationId = 'LOC_FIXTURE'; user.location_id = 'FOREIGN';}
    if (mode === 'invalid-auth') user.locationId = ['LOC_FIXTURE'];
    if (mode === 'foreign-user') details.locationId = 'FOREIGN';
    const store = {dispatch: async name => {calls.push(name); return name === 'auth/get' ? user : details;}};
    const router = {push: async spec => {
      paths.push(spec.path);
      if (mode === 'mutated-auth') user.locationId = 'FOREIGN';
      if (mode === 'mutated-user') details.location_id = 'FOREIGN';
    }};
    global.document = {querySelector: () => ({__vue_app__: {config: {globalProperties: {$store: store, $router: router}}}})};
    const result = await eval('(' + script + ')')({user_id: 'seed-user', company_id: 'seed-company',
      location_id: 'LOC_FIXTURE', target_path: '/v2/location/LOC_FIXTURE/dashboard'});
    outputs.push({mode, calls, paths, result});
  }
  process.stdout.write(JSON.stringify(outputs));
})().catch(() => process.exit(1));
"""
        result = subprocess.run([shutil.which("node"), "-e", program], input=json.dumps(activation.ACTIVATE_SPA_JS),
            capture_output=True, text=True, timeout=15, check=True)
        self.assertNotIn("PRIVATE-NEVER-RETURN", result.stdout)
        outputs = {entry["mode"]: entry for entry in json.loads(result.stdout)}
        self.assertEqual(outputs["missing"]["result"], {
            "state":"OK", "userId":"seed-user", "companyId":"seed-company", "locationId":""})
        for mode in ("expected-auth", "expected-user"):
            self.assertEqual(outputs[mode]["result"]["locationId"], LOC)
        for mode in ("foreign-auth", "foreign-snake-auth", "conflicting-auth", "invalid-auth", "foreign-user"):
            self.assertEqual(outputs[mode]["result"]["state"], "LOCATION_IDENTITY_MISMATCH")
            self.assertEqual(outputs[mode]["paths"], [])
            self.assertEqual(outputs[mode]["calls"].count("auth/get"), 1)
        for mode in ("mutated-auth", "mutated-user"):
            self.assertEqual(outputs[mode]["result"]["state"], "LOCATION_IDENTITY_MISMATCH")
            self.assertEqual(outputs[mode]["paths"], ["/v2/location/LOC_FIXTURE/dashboard"])
            self.assertEqual(outputs[mode]["calls"], ["auth/get", "user/get"])


if __name__ == "__main__":
    unittest.main()
