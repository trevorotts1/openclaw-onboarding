"""Optional post-seed, same-SPA location activation for the canonical bridge.

The Nov 8, 2026 Convert & Flow capture has Workspace navigation/account groups
and target-location links. A route alone is never location-access proof. This
profile requires those protected controls AND the same seeded auth/get identity.
It neither resolves credentials nor substitutes PIT/OAuth for the browser user.
Missing/changed captured controls fail closed. No login, reload or API guess.
"""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit
import re


APP_ORIGINS = {"https://app.gohighlevel.com", "https://app.convertandflow.com"}
EDITOR_FRAMES = {
    "form-builder-v2": "form-builder-app",
    "survey-builder-v2": "survey-builder-app",
    "quiz-builder-v2": "quiz-builder-app",
    "page-builder": "funnel-builder",
}


def _refuse(reason):
    from ghl_auth import AuthBridgeError
    raise AuthBridgeError("REFUSE (P4 activation): " + reason + "; STOP before any write.")


def validate_target(target, expected_location_id, app_origin=None):
    """Validate the explicit opt-in before minting or touching a page."""
    if not isinstance(target, dict) or set(target) - {"location_name", "start_url", "expected_builder_title"}:
        _refuse("unsupported location activation contract")
    if not isinstance(expected_location_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", expected_location_id):
        _refuse("an exact expected location is required")
    name = target.get("location_name")
    if not isinstance(name, str) or not name.strip():
        _refuse("the exact visible account name is required")
    value = target.get("start_url")
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        _refuse("invalid activation URL")
    parsed = urlsplit(value)
    origin = parsed.scheme + "://" + parsed.netloc
    if origin not in APP_ORIGINS or (app_origin is not None and origin != app_origin) or parsed.query or parsed.fragment or parsed.username is not None or parsed.password is not None:
        _refuse("activation requires the approved exact app origin")
    match = re.fullmatch(r"/(?:v2/)?location/([A-Za-z0-9_-]+)(?:/(.*))?", parsed.path)
    if not match or match[1] != expected_location_id:
        _refuse("activation target belongs to a different location")
    suffix = (match[2] or "").split("/")
    editor = EDITOR_FRAMES.get(suffix[0])
    title = target.get("expected_builder_title")
    if editor and (len(suffix) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", suffix[1]) or not isinstance(title, str) or not title.strip()):
        _refuse("editor activation requires an exact object ID and expected title")
    if not editor and title is not None:
        _refuse("a builder title cannot be ignored on a non-editor target")
    return {"location_id": expected_location_id, "location_name": name,
            "origin": origin, "start_url": value, "target_path": parsed.path,
            "dashboard_path": "/v2/location/" + expected_location_id + "/dashboard",
            "editor_frame": editor, "expected_builder_title": title}


# Same auth/get, user/get and router.push contract as inject-ghl-auth.sh's
# captured ACTIVATE_JS. Store readiness may wait; an auth/scope refusal is never
# retried. Only safe identity fields leave the page, never apiKey/cookie/token.
ACTIVATE_SPA_JS = r"""async (spec) => {
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const bounded = async action => {
    let timer;
    try {
      return await Promise.race([action(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('ACTIVATION_READ_TIMEOUT')), 10000);
      })]);
    } finally { clearTimeout(timer); }
  };
  let store = null, router = null;
  for (let attempt = 0; attempt < 16; attempt++) {
    const root = document.querySelector('#app');
    const gp = root && root.__vue_app__ && root.__vue_app__.config && root.__vue_app__.config.globalProperties;
    if (gp && gp.$store && gp.$router) { store = gp.$store; router = gp.$router; break; }
    await pause(500);
  }
  if (!store || !router) return {state: 'SPA_CONTRACT_UNAVAILABLE'};
  // Reported location fields are evidence, including contradictions. Never
  // replace them with the requested route or discard a foreign alias.
  const location = value => {
    const ids = ['locationId', 'location_id'].map(key => value && value[key])
      .filter(id => id !== undefined && id !== null && id !== '');
    if (ids.some(id => typeof id !== 'string' || id !== spec.location_id))
      return {state: 'LOCATION_IDENTITY_MISMATCH'};
    return {state: 'OK', locationId: ids[0] || ''};
  };
  let user, details;
  try { user = await bounded(() => store.dispatch('auth/get')); }
  catch (_) { return {state: 'AUTH_REFUSED'}; }
  if (!user || !user.userId || !user.companyId || !user.apiKey) return {state: 'AUTH_IDENTITY_UNPROVEN'};
  if (user.userId !== spec.user_id || user.companyId !== spec.company_id) return {state: 'IDENTITY_MISMATCH'};
  if (location(user).state !== 'OK') return {state: 'LOCATION_IDENTITY_MISMATCH'};
  if (spec.target_path !== null) {
    try { details = await bounded(() => store.dispatch('user/get')); }
    catch (_) { return {state: 'USER_READ_REFUSED'}; }
    if (location(details).state !== 'OK') return {state: 'LOCATION_IDENTITY_MISMATCH'};
    try { await bounded(() => router.push({path: spec.target_path})); }
    catch (_) { return {state: 'ROUTE_ACTIVATION_REFUSED'}; }
  }
  // Store actions/router hooks can mutate the returned objects in place.
  // Recheck those same reported fields after navigation; do not read auth again.
  const authLocation = location(user), detailLocation = location(details);
  if (authLocation.state !== 'OK' || detailLocation.state !== 'OK')
    return {state: 'LOCATION_IDENTITY_MISMATCH'};
  if (user.userId !== spec.user_id || user.companyId !== spec.company_id)
    return {state: 'IDENTITY_MISMATCH'};
  return {state: 'OK', userId: user.userId, companyId: user.companyId,
    locationId: authLocation.locationId || detailLocation.locationId};
}"""


def _identity(value, expected_location_id):
    if not isinstance(value, dict):
        _refuse("seed identity is unavailable")
    user = value.get("userId") or value.get("user_id")
    company = value.get("companyId") or value.get("company_id")
    if not isinstance(user, str) or not user or not isinstance(company, str) or not company:
        _refuse("authenticated seed user and company must both be proven")
    locations = [value[key] for key in ("locationId", "location_id")
                 if key in value and value[key] is not None and value[key] != ""]
    if any(not isinstance(location, str) or location != expected_location_id
           for location in locations):
        _refuse("the same-session identity reports a different or invalid location")
    return {"userId": user, "companyId": company,
            "locationId": locations[0] if locations else ""}


def _auth(page, identity, path, expected_location_id):
    try:
        result = page.evaluate(ACTIVATE_SPA_JS, {"user_id": identity["userId"],
            "company_id": identity["companyId"], "target_path": path,
            "location_id": expected_location_id})
    except Exception:
        _refuse("same-session SPA activation could not be read")
    if not isinstance(result, dict) or result.get("state") != "OK":
        _refuse("same-session activation or identity was refused")
    actual = _identity(result, expected_location_id)
    if any(actual[key] != identity[key] for key in ("userId", "companyId")):
        _refuse("same-session browser identity changed")


def _route(page, contract, path):
    expected = contract["origin"] + path
    if page.url != expected:
        _refuse("the authenticated route did not match the target")
    detected_login_inputs = page.locator('input[type="password"]')
    if any(detected_login_inputs.nth(index).is_visible() for index in range(detected_login_inputs.count())):
        _refuse("a login wall is present")


def _wait_route(page, contract, path):
    try:
        page.wait_for_url(contract["origin"] + path, timeout=45000)
    except Exception:
        _refuse("the target route did not become ready")
    _route(page, contract, path)


def _workspace(page, contract):
    """Protected Nov 8 UI profile: exact account and target nav, not URL-only."""
    try:
        workspace = page.get_by_role("region", name="Workspace navigation", exact=True)
        workspace.wait_for(state="visible", timeout=45000)
        if workspace.count() != 1:
            _refuse("the captured workspace profile is unavailable or ambiguous")
        group = workspace.get_by_role("group", name=contract["location_name"], exact=True)
        group.wait_for(state="visible", timeout=45000)
        if group.count() != 1:
            _refuse("the workspace account is ambiguous")
        accounts = page.get_by_role("navigation", name="Accounts", exact=True)
        listed = accounts.get_by_role("list", name="All sub-accounts", exact=True)
        account = listed.get_by_role("button", name=contract["location_name"], exact=True)
        account.wait_for(state="visible", timeout=45000)
        if accounts.count() != 1 or listed.count() != 1 or account.count() != 1 or not account.is_visible():
            _refuse("the authenticated account directory does not identify the target")
        links = workspace.locator("a[href]")
        paths = set()
        for index in range(links.count()):
            href = links.nth(index).get_attribute("href")
            parsed = urlsplit(urljoin(contract["origin"], href or ""))
            match = re.match(r"/(?:v2/)?location/([A-Za-z0-9_-]+)(?:/|$)", parsed.path)
            if match:
                if parsed.scheme + "://" + parsed.netloc != contract["origin"] or match[1] != contract["location_id"]:
                    _refuse("workspace navigation identifies a different location")
                paths.add(parsed.path)
        if len(paths) < 2:
            _refuse("protected target-location navigation is not proven")
        return len(paths)
    except Exception as exc:
        from ghl_auth import AuthBridgeError
        if isinstance(exc, AuthBridgeError):
            raise
        _refuse("the protected workspace could not be verified")


def _target_ready(page, contract):
    frame_name = contract["editor_frame"]
    if frame_name is None:
        _workspace(page, contract)
        return
    selector = 'iframe[name="' + frame_name + '"]'
    try:
        page.locator(selector).wait_for(state="visible", timeout=45000)
        if page.locator(selector).count() != 1 or page.locator('iframe[name$="-builder-app"],iframe[name="funnel-builder"]').count() != 1:
            _refuse("the expected editor is ambiguous")
        frame = page.frame_locator(selector)
        title = (frame.get_by_text(contract["expected_builder_title"], exact=True)
                 if frame_name == "funnel-builder" else
                 frame.get_by_role("textbox", name="Form Name", exact=True))
        title.wait_for(state="visible", timeout=45000)
        if title.count() != 1:
            _refuse("the expected builder title is ambiguous")
        if frame_name != "funnel-builder" and title.input_value() != contract["expected_builder_title"]:
            _refuse("the protected editor belongs to a different object")
    except Exception as exc:
        from ghl_auth import AuthBridgeError
        if isinstance(exc, AuthBridgeError):
            raise
        _refuse("the protected target editor could not be verified")


def activate_and_verify_location(page, seed_identity, target, *, expected_location_id, expected_company_id=None, app_origin=None):
    """Run only AFTER real seeding, before canonical identity validation/writes.

    Both before/after same-SPA auth reads must identify the fresh seed user and
    company. Dashboard account scope and the exact target object are checked in
    that SAME page. No retry, re-seed, reload or separate credential is used.
    """
    contract = validate_target(target, expected_location_id, app_origin)
    identity = _identity(seed_identity, expected_location_id)
    if expected_company_id and identity["companyId"] != expected_company_id:
        _refuse("the seeded company does not match the task")
    if urlsplit(page.url).scheme + "://" + urlsplit(page.url).netloc != contract["origin"]:
        _refuse("the seeded page left its approved origin")
    _auth(page, identity, contract["dashboard_path"], expected_location_id)
    _wait_route(page, contract, contract["dashboard_path"])
    link_count = _workspace(page, contract)
    _route(page, contract, contract["dashboard_path"])
    _auth(page, identity, None, expected_location_id)
    _route(page, contract, contract["dashboard_path"])
    _workspace(page, contract)
    if contract["target_path"] != contract["dashboard_path"]:
        _auth(page, identity, contract["target_path"], expected_location_id)
        _wait_route(page, contract, contract["target_path"])
        _target_ready(page, contract)
        _auth(page, identity, None, expected_location_id)
        _route(page, contract, contract["target_path"])
    return {**identity, "locationId": contract["location_id"],
            "activation_proof": {"profile": "same-spa-workspace-20261108",
                "same_seeded_identity": True, "account_directory_verified": True,
                "protected_location_links": link_count, "target_verified": True}}
