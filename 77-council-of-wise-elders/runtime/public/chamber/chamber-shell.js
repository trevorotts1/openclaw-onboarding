/*
 * Chamber shell (unit A). Dependency-free, same-origin only.
 *
 * Owns the top bar (phase stepper, three buttons), the demo banner and the
 * three shell dialogs: How it works, Past sessions and New question. The
 * composer convenes for real through POST /api/council/convene on the route
 * the client picks; nothing is preselected, because convening is the
 * approval. Every string on screen is set with textContent.
 *
 * Pure API for tests: councilChamber.shell.buildBrief and .stepperModel.
 */
(function (root) {
  'use strict';

  var ns = root.councilChamber = root.councilChamber || {};

  // ---------------------------------------------------------------- pure

  var STEPS = [
    { key: 'brief', label: 'Brief' },
    { key: 'openings', label: 'Openings' },
    { key: 'fault_lines', label: 'Fault lines' },
    { key: 'debate', label: 'Debate' },
    { key: 'vote', label: 'Vote' },
    { key: 'verdict', label: 'Verdict' }
  ];
  var STEP_STATUSES = { done: 1, current: 1, todo: 1, skipped: 1 };

  /** The six steps for the top bar. With no session, Brief is current. */
  function stepperModel(view) {
    var session = view && view.session;
    var given = session && Array.isArray(session.steps) ? session.steps : null;
    var model = STEPS.map(function (step, index) {
      var found = null;
      if (given) {
        for (var i = 0; i < given.length; i += 1) {
          if (given[i] && given[i].key === step.key) found = given[i];
        }
      }
      var status = found && STEP_STATUSES[found.status] === 1
        ? found.status
        : (!session && index === 0 ? 'current' : 'todo');
      return { key: step.key, label: step.label, status: status };
    });
    // A finished session has every step done; Verdict stays the current one.
    if (session && !model.some(function (m) { return m.status === 'current'; }) && model[5].status !== 'skipped') {
      model[5].status = 'current';
    }
    return model;
  }

  var OPTION_KINDS = { status_quo: 1, bounded_test: 1, change: 1, other: 1 };
  var KIND_BY_LABEL = {
    'Keep as is': 'status_quo',
    'Small test': 'bounded_test',
    'Change': 'change',
    'Other': 'other'
  };
  var OPTION_IDS = ['A', 'B', 'C', 'D'];

  function kindOf(value) {
    if (typeof value !== 'string') return 'other';
    if (OPTION_KINDS[value] === 1) return value;
    return Object.prototype.hasOwnProperty.call(KIND_BY_LABEL, value) ? KIND_BY_LABEL[value] : 'other';
  }

  function nowMsOf(now) {
    var ms = now instanceof Date ? now.getTime() : (now === undefined || now === null ? Date.now() : new Date(now).getTime());
    return isFinite(ms) ? ms : Date.now();
  }

  function zoneOf(timeZone) {
    if (typeof timeZone === 'string' && timeZone) return timeZone;
    try {
      var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (zone) return zone;
    } catch (e) { /* fall through */ }
    return 'UTC';
  }

  /**
   * Build a DecisionBrief the council contract accepts from the composer's
   * fields. Every seat gets weight 2: an empty weight map would leave the
   * verdict with no active seats.
   */
  function buildBrief(input) {
    var o = input || {};
    var options = [];
    var given = Array.isArray(o.options) ? o.options : [];
    for (var i = 0; i < given.length && options.length < OPTION_IDS.length; i += 1) {
      var label = given[i] && typeof given[i].label === 'string' ? given[i].label.trim() : '';
      if (!label) continue;
      options.push({ id: OPTION_IDS[options.length], label: label, kind: kindOf(given[i].kind) });
    }
    var facts = [];
    var lines = typeof o.context === 'string' ? o.context.split(/\r?\n/) : [];
    for (var j = 0; j < lines.length; j += 1) {
      var statement = lines[j].trim();
      if (statement) facts.push({ id: 'fact-' + (facts.length + 1), statement: statement, evidence_ids: [] });
    }
    var weights = {};
    var seatIds = Array.isArray(o.seatIds) ? o.seatIds : [];
    for (var k = 0; k < seatIds.length; k += 1) weights[seatIds[k]] = 2;
    return {
      schema_version: 'wise-elders.brief/v1',
      brief_id: 'brief-draft',
      session_id: 'draft',
      revision: 1,
      question: typeof o.question === 'string' ? o.question.trim() : '',
      facts: facts,
      assumptions: [],
      unknowns: [],
      constraints: [],
      options: options,
      relevance_weights: weights,
      critical_domains: [],
      evidence_manifest: [],
      private_preference_ref: null,
      created_at: new Date(nowMsOf(o.now)).toISOString(),
      display_timezone: zoneOf(o.timeZone)
    };
  }

  ns.shell = { buildBrief: buildBrief, stepperModel: stepperModel };

  if (typeof document === 'undefined') return;

  // ---------------------------------------------------------------- DOM

  var DEMO_BANNER = 'Demo replay: a fictional sample decision. Not a real session and not real advisor output.';
  var DEFAULT_MODEL_TEXT = {
    harness_default: 'your claude-nine default model',
    sonnet: 'Sonnet',
    latest_deepseek_flash: 'newest DeepSeek Flash, read live'
  };
  var STATE_TEXT = {
    DRAFT: 'Draft', READY: 'Ready', QUEUED: 'Queued', PREPARING: 'Preparing',
    ROUND_1: 'Round 1', CRUX_REVIEW: 'Fault lines', ROUND_2: 'Round 2',
    DRAFT_RESOLUTION: 'Drafting the resolution', ROUND_3: 'Round 3', VERIFYING: 'Checking the verdict',
    COMPLETED: 'Complete', CONSULTING: 'Consulting', RESUMING: 'Resuming', BLOCKED: 'Blocked', FAILED: 'Failed'
  };

  var lastView = null;
  var openers = new WeakMap();
  var els = {};

  function byId(id) { return document.getElementById(id); }

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function live() { return ns.live || null; }

  // ---- dialogs

  function openDialog(dialog, opener) {
    if (!dialog || typeof dialog.showModal !== 'function' || dialog.open) return;
    var from = opener && opener.focus ? opener : document.activeElement;
    openers.set(dialog, from && from !== document.body ? from : null);
    dialog.showModal();
  }

  function wireDialog(dialog, closeOnBackdrop) {
    dialog.addEventListener('close', function () {
      var back = openers.get(dialog);
      if (back && back.isConnected && typeof back.focus === 'function') back.focus();
    });
    var closers = dialog.querySelectorAll('[data-ch-close]');
    for (var i = 0; i < closers.length; i += 1) {
      closers[i].addEventListener('click', function () { dialog.close(); });
    }
    if (closeOnBackdrop) {
      dialog.addEventListener('click', function (event) {
        if (event.target !== dialog) return;
        var box = dialog.getBoundingClientRect();
        var inside = event.clientX >= box.left && event.clientX <= box.right &&
          event.clientY >= box.top && event.clientY <= box.bottom;
        if (!inside) dialog.close();
      });
    }
  }

  // ---- stepper and banner

  var currentKey = null;

  // On a phone the strip scrolls inside itself; keep the current phase visible.
  function keepInView(item) {
    var strip = els.stepper;
    var left = item.offsetLeft - 8;
    var right = item.offsetLeft + item.offsetWidth + 8;
    if (left < strip.scrollLeft) strip.scrollLeft = left;
    else if (right > strip.scrollLeft + strip.clientWidth) strip.scrollLeft = right - strip.clientWidth;
  }

  function renderStepper(view) {
    var model = stepperModel(view);
    for (var i = 0; i < model.length; i += 1) {
      var item = els.stepper.querySelector('[data-step="' + model[i].key + '"]');
      if (!item) continue;
      var status = model[i].status;
      if (item.getAttribute('data-status') !== status) item.setAttribute('data-status', status);
      if (status === 'current') {
        item.setAttribute('aria-current', 'step');
        if (currentKey !== model[i].key) {
          currentKey = model[i].key;
          keepInView(item);
        }
      } else item.removeAttribute('aria-current');
      var sr = item.querySelector('.ch-step-sr');
      if (!sr) {
        sr = make('span', 'ch-sr-only ch-step-sr');
        item.appendChild(sr);
      }
      var srText = status === 'todo' ? '' : ' (' + status + ')';
      if (sr.textContent !== srText) sr.textContent = srText;
    }
  }

  function renderBanner(view) {
    var demo = !!(view && view.mode === 'demo');
    if (els.banner.hidden === demo) els.banner.hidden = !demo;
    if (demo && els.bannerText.textContent !== DEMO_BANNER) els.bannerText.textContent = DEMO_BANNER;
  }

  // ---- past sessions

  function stateText(state) {
    if (typeof state !== 'string' || !state) return 'Unknown state';
    if (Object.prototype.hasOwnProperty.call(STATE_TEXT, state)) return STATE_TEXT[state];
    var plain = state.toLowerCase().replace(/_/g, ' ');
    return plain.charAt(0).toUpperCase() + plain.slice(1);
  }

  function localTime(iso) {
    var ms = typeof iso === 'string' ? Date.parse(iso) : NaN;
    return isFinite(ms) ? new Date(ms).toLocaleString() : 'time unknown';
  }

  function newestFirst(sessions) {
    return sessions.slice().sort(function (a, b) {
      var ta = Date.parse(a && a.created_at);
      var tb = Date.parse(b && b.created_at);
      return (isFinite(tb) ? tb : 0) - (isFinite(ta) ? ta : 0);
    });
  }

  var sessionsSig = null;

  function renderSessions(view, force) {
    var list = (view && view.list) || { status: 'loading', sessions: [] };
    var sessions = Array.isArray(list.sessions) ? list.sessions : [];
    var openId = view && view.session ? view.session.id : null;
    // The tick re-delivers the view every second; rebuild only on a real change so keyboard focus survives.
    var sig = JSON.stringify([list.status, list.error || null, openId, sessions]);
    if (!force && sig === sessionsSig) return;
    sessionsSig = sig;
    var message = '';
    if (list.status === 'loading') message = 'Loading council sessions...';
    else if (list.status === 'unbound') message = 'Session history is not available: this service has no session list connected, so it cannot show past sessions.';
    else if (list.status === 'error') message = (list.error ? String(list.error).replace(/\.+\s*$/, '') : 'Could not load past sessions') + '. Choose Refresh to try again.';
    else if (sessions.length === 0) message = 'No council sessions yet. Choose New question to convene one.';
    else message = sessions.length + (sessions.length === 1 ? ' session' : ' sessions') + ', newest first.';
    els.sessionsStatus.textContent = message;

    clear(els.sessionsList);
    if (list.status !== 'ready') return;
    var ordered = newestFirst(sessions);
    for (var i = 0; i < ordered.length; i += 1) {
      els.sessionsList.appendChild(sessionItem(ordered[i], openId));
    }
  }

  function sessionItem(session, openId) {
    var li = make('li');
    var button = make('button', 'ch-sessions-item');
    button.type = 'button';
    if (session.session_id === openId) button.setAttribute('aria-current', 'true');
    button.appendChild(make('span', 'ch-sessions-q', session.question || 'Untitled question'));
    var meta = stateText(session.state) + ' · ' + localTime(session.created_at) + (session.sample ? ' · Sample' : '');
    button.appendChild(make('span', 'ch-sessions-meta', meta));
    button.addEventListener('click', function () {
      if (live()) live().select(session.session_id);
      els.sessions.close();
    });
    li.appendChild(button);
    return li;
  }

  function openSessions(opener) {
    if (live() && live().refreshList) live().refreshList();
    renderSessions(lastView, true);
    openDialog(els.sessions, opener);
  }

  // ---- composer

  var routes = { loaded: false };
  var posting = false;
  var optionInputs = [];

  var KIND_CHOICES = [
    ['other', 'Other'],
    ['status_quo', 'Keep as is'],
    ['bounded_test', 'Small test'],
    ['change', 'Change']
  ];

  function buildOptionRows() {
    for (var i = 0; i < OPTION_IDS.length; i += 1) {
      var row = make('div', 'ch-composer-option-row');
      row.appendChild(make('span', 'ch-composer-letter', OPTION_IDS[i]));
      var input = make('input', 'ch-composer-input');
      input.type = 'text';
      input.autocomplete = 'off';
      input.maxLength = 200;
      input.setAttribute('aria-label', 'Option ' + OPTION_IDS[i] + (i < 2 ? '' : ' (optional)'));
      if (i >= 2) input.placeholder = 'Optional';
      var select = make('select', 'ch-composer-select');
      select.setAttribute('aria-label', 'Option ' + OPTION_IDS[i] + ' kind');
      for (var c = 0; c < KIND_CHOICES.length; c += 1) {
        var option = make('option', null, KIND_CHOICES[c][1]);
        option.value = KIND_CHOICES[c][0];
        select.appendChild(option);
      }
      row.appendChild(input);
      row.appendChild(select);
      els.optionRows.appendChild(row);
      optionInputs.push({ input: input, select: select });
    }
  }

  function selectedRoute() {
    var checked = els.routesList.querySelector('input[name="ch-route"]:checked');
    return checked ? checked.value : null;
  }

  function updateSubmit() {
    els.submit.disabled = posting || selectedRoute() === null;
  }

  // A refusal detail can be a string, an empty object (route refusals) or raw
  // JSON (issues). Show a plain sentence, never "{}" or JSON.
  function detailText(detail, fallback) {
    if (typeof detail === 'string' && detail.trim()) return detail;
    var issues = detail && Array.isArray(detail.issues) ? detail.issues : null;
    if (issues) {
      var lines = [];
      for (var i = 0; i < issues.length; i += 1) {
        var m = issues[i] && typeof issues[i].message === 'string' ? issues[i].message : '';
        if (m) lines.push(issues[i].path ? issues[i].path + ': ' + m : m);
      }
      if (lines.length) return lines.join('; ');
    }
    return fallback;
  }

  function showError(parts) {
    clear(els.error);
    if (parts.code) els.error.appendChild(make('p', 'ch-composer-error-code', parts.code));
    if (parts.detail) els.error.appendChild(make('p', null, parts.detail));
    if (parts.recovery) els.error.appendChild(make('p', null, 'What to do: ' + parts.recovery));
    els.error.hidden = false;
    if (els.error.scrollIntoView) els.error.scrollIntoView({ block: 'nearest' });
  }

  function hideError() {
    els.error.hidden = true;
    clear(els.error);
  }

  function defaultModelText(routeId, defaults) {
    var keys = defaults ? Object.keys(defaults) : [];
    for (var i = 0; i < keys.length; i += 1) {
      var entry = defaults[keys[i]];
      if (entry && entry.route_id === routeId) {
        return Object.prototype.hasOwnProperty.call(DEFAULT_MODEL_TEXT, entry.model)
          ? DEFAULT_MODEL_TEXT[entry.model]
          : String(entry.model);
      }
    }
    return 'set by the route itself';
  }

  function renderRoutes(body) {
    clear(els.routesList);
    var list = Array.isArray(body.routes) ? body.routes : [];
    if (list.length === 0) {
      els.routesStatus.textContent = 'This service offers no routes, so it cannot convene yet. Configure a model route for the council, then reopen this window.';
      return;
    }
    els.routesStatus.textContent = 'Pick the route that runs this council. Nothing is chosen for you.';
    for (var i = 0; i < list.length; i += 1) {
      var route = list[i];
      var label = make('label', 'ch-composer-route');
      var radio = make('input');
      radio.type = 'radio';
      radio.name = 'ch-route';
      radio.value = route.route_id;
      var usable = route.composable === true;
      radio.disabled = !usable;
      if (!usable) label.setAttribute('data-disabled', 'true');
      radio.addEventListener('change', updateSubmit);
      label.appendChild(radio);
      label.appendChild(make('span', 'ch-composer-route-name', ns.state.routeLabel(route.route_id, null)));
      if (usable) {
        label.appendChild(make('span', 'ch-composer-route-line', 'Default model: ' + defaultModelText(route.route_id, body.harness_defaults)));
      } else {
        label.appendChild(make('span', 'ch-composer-route-line', 'Not available for the council yet'));
      }
      els.routesList.appendChild(label);
    }
  }

  function loadRoutes() {
    clear(els.routesList);
    els.routesStatus.textContent = 'Loading routes...';
    updateSubmit();
    var token = {};
    routes.token = token;
    fetch('/api/council/routes', { headers: { accept: 'application/json' }, cache: 'no-store' })
      .then(function (res) {
        return res.text().then(function (text) {
          var body = null;
          try { body = JSON.parse(text); } catch (e) { /* not JSON */ }
          return { ok: res.ok, status: res.status, body: body };
        });
      })
      .then(function (result) {
        if (routes.token !== token) return;
        if (!result.ok || !result.body) {
          var b = result.body || {};
          els.routesStatus.textContent = 'Routes could not be loaded (' + (b.code || 'HTTP ' + result.status) + ')' +
            (b.detail ? ': ' + String(b.detail) : '') + (b.recovery ? ' ' + String(b.recovery) : '');
          return;
        }
        renderRoutes(result.body);
        updateSubmit();
      })
      .catch(function () {
        if (routes.token !== token) return;
        els.routesStatus.textContent = 'Routes could not be loaded: the council service did not answer. Reopen this window to try again.';
      });
  }

  function openComposer(opener) {
    hideError();
    updateSubmit();
    loadRoutes();
    openDialog(els.composer, opener);
  }

  function resetComposer() {
    els.question.value = '';
    els.context.value = '';
    els.model.value = '';
    for (var i = 0; i < optionInputs.length; i += 1) {
      optionInputs[i].input.value = '';
      optionInputs[i].select.value = 'other';
    }
    hideError();
  }

  function submitComposer() {
    if (posting) return;
    hideError();
    var routeId = selectedRoute();
    var options = [];
    for (var i = 0; i < optionInputs.length; i += 1) {
      var label = optionInputs[i].input.value.trim();
      if (label) options.push({ label: label, kind: optionInputs[i].select.value });
    }
    var question = els.question.value.trim();
    var seats = ns.seats && ns.seats.order;
    if (!routeId) return showError({ detail: 'Pick a route first. Convening runs on the route you choose.' });
    if (!question) return showError({ detail: 'Write the question the council should answer.' });
    if (options.length < 2) return showError({ detail: 'Give the council at least two options to weigh.' });
    if (!seats || !seats.length) return showError({ detail: 'The advisor roster did not load, so the council cannot be convened. Reload the page.' });

    var request = {
      brief: buildBrief({ question: question, options: options, context: els.context.value, now: new Date(), seatIds: seats }),
      route_id: routeId,
      requested_by: 'chamber-composer'
    };
    var model = els.model.value.trim();
    if (model) request.model = model;

    posting = true;
    els.submit.textContent = 'Convening...';
    updateSubmit();
    fetch('/api/council/convene', {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(request)
    })
      .then(function (res) {
        return res.text().then(function (text) {
          var body = null;
          try { body = JSON.parse(text); } catch (e) { /* not JSON */ }
          return { status: res.status, body: body || {} };
        });
      })
      .then(function (result) {
        if (result.status === 202 && result.body.session_id) {
          if (live()) live().select(result.body.session_id);
          resetComposer();
          els.composer.close();
          return;
        }
        showError({
          code: result.body.code || (result.status === 202 ? 'CONVENE_NO_SESSION' : 'HTTP_' + result.status),
          detail: detailText(result.body.detail, result.status === 202 ? 'The service accepted the request but returned no session id.' : 'The service refused the request.'),
          recovery: result.body.recovery || 'Check the question, the options and the route, then try again.'
        });
      })
      .catch(function () {
        showError({ code: 'CONVENE_UNREACHABLE', detail: 'The council service did not answer.', recovery: 'Check that the service is running, then try again.' });
      })
      .then(function () {
        posting = false;
        els.submit.textContent = 'Convene';
        updateSubmit();
      });
  }

  // ---- boot

  function init() {
    els = {
      stepper: byId('ch-stepper'),
      banner: byId('ch-banner'),
      bannerText: document.querySelector('#ch-banner .ch-banner-text'),
      how: byId('ch-how'),
      sessions: byId('ch-sessions'),
      sessionsStatus: byId('ch-sessions-status'),
      sessionsList: byId('ch-sessions-list'),
      composer: byId('ch-composer'),
      question: byId('ch-composer-question'),
      context: byId('ch-composer-context'),
      model: byId('ch-composer-model'),
      optionRows: byId('ch-composer-option-rows'),
      routesStatus: byId('ch-composer-routes-status'),
      routesList: byId('ch-composer-routes-list'),
      error: byId('ch-composer-error'),
      submit: byId('ch-composer-submit')
    };
    if (!els.stepper || !els.banner || !els.how || !els.sessions || !els.composer) return;

    buildOptionRows();
    wireDialog(els.how, true);
    wireDialog(els.sessions, true);
    wireDialog(els.composer, false);

    byId('ch-open-how').addEventListener('click', function (event) { openDialog(els.how, event.currentTarget); });
    byId('ch-open-sessions').addEventListener('click', function (event) { openSessions(event.currentTarget); });
    byId('ch-open-composer').addEventListener('click', function (event) { openComposer(event.currentTarget); });
    document.addEventListener('chamber:open-how', function (event) { openDialog(els.how, event.detail && event.detail.opener); });
    document.addEventListener('chamber:open-sessions', function (event) { openSessions(event.detail && event.detail.opener); });
    document.addEventListener('chamber:open-composer', function (event) { openComposer(event.detail && event.detail.opener); });

    byId('ch-how-demo').addEventListener('click', function () {
      els.how.close();
      if (live()) live().startDemo();
    });
    byId('ch-banner-exit').addEventListener('click', function () { if (live()) live().stopDemo(); });
    byId('ch-sessions-refresh').addEventListener('click', function () { if (live()) live().refreshList(); });
    byId('ch-composer-form').addEventListener('submit', function (event) {
      event.preventDefault();
      submitComposer();
    });

    function render(view) {
      lastView = view;
      renderStepper(view);
      renderBanner(view);
      if (els.sessions.open) renderSessions(view);
    }
    render(live() && live().getView ? live().getView() : null);
    if (live() && live().subscribe) live().subscribe(render);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(typeof globalThis !== 'undefined' ? globalThis : this);
