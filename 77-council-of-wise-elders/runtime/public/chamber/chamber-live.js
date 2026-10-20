/*
 * Council chamber store and transport. Dependency-free, same-origin only.
 * Does NO DOM rendering: it owns fetch, timers, location.hash and
 * history.replaceState, and hands renderers one ChamberView through
 * ns.live.subscribe.
 *
 *   ns.live = {getView, subscribe, select, refreshList, startDemo, stopDemo, reconnect}
 *
 * Real sessions come from GET /api/council/sessions. The selected session is
 * read from GET /council/<id> (which carries cards and the verdict) and
 * streamed from GET /api/council/sessions/<id>/events (committed journal rows
 * only), read with fetch so a finished stream does not silently reconnect and
 * replay. card_accepted carries no card text, so each burst of accepted cards
 * (and the verdict and any terminal state) triggers one debounced re-read.
 * Nothing here invents a session, a stance or an event. The demo replay is a
 * labelled fictional file played through the same reducer.
 */
(function (root) {
  'use strict';
  var ns = root.councilChamber = root.councilChamber || {};

  var MAX_RETRIES = 5;
  var RETRY_MS = 3000;
  var LIST_REFRESH_MS = 15000;
  var REFETCH_MS = 300;
  var TICK_MS = 1000;

  // ---------------------------------------------------------------- pure

  /** Split a buffer into complete SSE blocks; returns parsed frames and the unfinished rest. */
  function parseSse(buffer) {
    var text = String(buffer).replace(/\r\n/g, '\n');
    var blocks = text.split('\n\n');
    var rest = blocks.pop();
    var frames = [];
    blocks.forEach(function (block) {
      var data = [];
      block.split('\n').forEach(function (line) {
        if (line.indexOf('data:') === 0) data.push(line.slice(5).replace(/^ /, ''));
      });
      if (data.length === 0) return;
      try {
        var frame = JSON.parse(data.join('\n'));
        if (frame && typeof frame === 'object') frames.push(frame);
      } catch (e) {
        /* a malformed block is skipped, never repaired */
      }
    });
    return { frames: frames, rest: rest };
  }

  function label(value) {
    return String(value).replace(/_/g, ' ');
  }

  function when(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
  }

  /** Assign text only when it differs, so unchanged live regions are not re-announced. */
  function setText(node, text) { if (node.textContent !== text) node.textContent = text; }

  /**
   * Update a session list in place, keyed by session_id, so a refresh never
   * removes the button that has keyboard focus. Nodes are created only for new
   * sessions, removed (before ordering) only for sessions that are gone, and moved only
   * when the order of the remaining sessions changed.
   */
  function reconcileList(list, sessions, selected, onSelect, doc) {
    var keep = {};
    sessions.forEach(function (s) { keep[s.session_id] = true; });
    var byId = {};
    var node = list.firstChild;
    while (node) {
      var next = node.nextSibling;
      var id = node.getAttribute('data-session-id');
      if (keep[id]) byId[id] = node; else list.removeChild(node);
      node = next;
    }
    var cursor = list.firstChild;
    sessions.forEach(function (s) {
      var li = byId[s.session_id];
      delete byId[s.session_id];
      var btn;
      if (li) {
        btn = li.firstChild;
      } else {
        li = doc.createElement('li');
        li.setAttribute('data-session-id', s.session_id);
        btn = doc.createElement('button');
        btn.className = 'council-session-btn';
        btn.type = 'button';
        btn.appendChild(doc.createElement('strong'));
        var meta = doc.createElement('span');
        meta.className = 'council-meta';
        btn.appendChild(meta);
        btn.addEventListener('click', function () { onSelect(s.session_id); });
        li.appendChild(btn);
      }
      btn.setAttribute('aria-pressed', s.session_id === selected ? 'true' : 'false');
      setText(btn.firstChild, s.question || s.session_id);
      setText(btn.lastChild, label(s.state) + ' | ' + s.mode + ' | ' + when(s.created_at) +
        (s.sample ? ' | synthetic sample session' : ''));
      if (li === cursor) cursor = cursor.nextSibling;
      else list.insertBefore(li, cursor);
    });
  }

  /** '#demo' -> {kind:'demo'}, '#session=<id>' -> {kind:'session', id}, anything else -> null. */
  function parseHash(hash) {
    var h = String(hash || '');
    if (h === '#demo') return { kind: 'demo' };
    var m = /^#session=(.+)$/.exec(h);
    if (!m) return null;
    try { return { kind: 'session', id: decodeURIComponent(m[1]) }; } catch (e) { return null; }
  }

  var pure = { reconcileList: reconcileList, parseSse: parseSse, parseHash: parseHash };
  if (typeof globalThis !== 'undefined') globalThis.councilLive = pure;

  // --------------------------------------------------------------- store

  // Only a real page (or a test that supplies fetch and document) starts the store.
  if (typeof document === 'undefined' || typeof fetch !== 'function' || !ns.state) return;
  var state = ns.state;

  var listState = { status: 'loading', sessions: [], error: null };
  var connection = { status: 'idle', text: '', canReconnect: false };
  var mode = 'loading';
  var selectedId = null;
  var model = null;
  var demo = null; // {data, base, start, timer, index, prevId}
  var subscribers = [];
  var stream = null;
  var retries = 0;
  var retryTimer = null;
  var refetchTimer = null;
  var tickTimer = null;
  var generation = 0;

  function nowMs() {
    if (demo && demo.base !== null) return demo.base + (Date.now() - demo.start);
    return Date.now();
  }

  var TERMINAL = { COMPLETED: true, CANCELLED: true, FAILED: true };

  function terminal() {
    return !!(model && model.state && TERMINAL[model.state] === true);
  }

  function getView() {
    var now = nowMs();
    return {
      mode: mode,
      now: now,
      list: listState,
      connection: connection,
      session: model ? state.view(model, now) : null
    };
  }

  function notify() {
    var v = getView();
    subscribers.slice().forEach(function (fn) {
      try { fn(v); } catch (e) { /* one renderer failing never silences the others */ }
    });
    ensureTick();
  }

  function ensureTick() {
    var want = subscribers.length > 0 && !!model && !terminal();
    if (want && !tickTimer) tickTimer = setInterval(notify, TICK_MS);
    else if (!want && tickTimer) { clearInterval(tickTimer); tickTimer = null; }
  }

  function subscribe(fn) {
    subscribers.push(fn);
    try { fn(getView()); } catch (e) { /* see notify */ }
    ensureTick();
    return function () {
      var i = subscribers.indexOf(fn);
      if (i >= 0) subscribers.splice(i, 1);
      ensureTick();
    };
  }

  function setConn(status, text, canReconnect) {
    connection = { status: status, text: text, canReconnect: !!canReconnect };
  }

  function setHash(hash) {
    try {
      var loc = root.location;
      if (root.history && root.history.replaceState && loc) {
        root.history.replaceState(null, '', hash || (loc.pathname + (loc.search || '')));
      }
    } catch (e) { /* the address bar is a convenience only */ }
  }

  // ------------------------------------------------------------- streaming

  function stopStream() {
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    if (refetchTimer) { clearTimeout(refetchTimer); refetchTimer = null; }
    if (stream) { stream.abort(); stream = null; }
  }

  function readSession(id) {
    return fetch('/council/' + encodeURIComponent(id), { headers: { accept: 'application/json' } })
      .then(function (res) {
        if (res.status === 404) throw new Error('This session is no longer known to the service.');
        if (!res.ok) throw new Error('The service answered HTTP ' + res.status + '.');
        return res.json();
      })
      .then(function (body) {
        if (!body || !body.session) throw new Error('The service returned no session record.');
        return body.session;
      });
  }

  function scheduleRefetch() {
    if (refetchTimer) return; // later cards in the same burst ride along
    var id = selectedId;
    var gen = generation;
    refetchTimer = setTimeout(function () {
      refetchTimer = null;
      readSession(id).then(function (record) {
        if (gen !== generation || !model) return;
        state.applyRecord(model, record);
        notify();
      }).catch(function () { /* the next card or verdict triggers another read */ });
    }, REFETCH_MS);
  }

  function applyFrames(frames) {
    var changed = false;
    var wantRead = false;
    frames.forEach(function (frame) {
      if (!state.apply(model, frame)) return;
      changed = true;
      if (frame.type === 'card_accepted' || frame.type === 'verdict_validated' || frame.type === 'session_blocked') wantRead = true;
      // The service explains a block (blocked_reason) only on a read, and records its last error after session_blocked.
      if (frame.type === 'operation_completed' && frame.payload && frame.payload.kind === 'worker_error') wantRead = true;
    });
    if (changed && terminal()) wantRead = true;
    if (wantRead) scheduleRefetch();
    return changed;
  }

  function startStream() {
    if (stream) { stream.abort(); stream = null; }
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    var id = selectedId;
    var gen = generation;
    var ctl = new AbortController();
    stream = ctl;
    setConn('connecting', retries ? 'Reconnecting...' : 'Connecting to the event stream...', false);
    notify();

    function drop(text) {
      if (ctl.signal.aborted || gen !== generation) return;
      stream = null;
      if (retries >= MAX_RETRIES) {
        setConn('lost', 'Lost the event stream. Use Reconnect to try again.', true);
        notify();
        return;
      }
      retries += 1;
      setConn('retrying', text + ' Retrying (' + retries + ' of ' + MAX_RETRIES + ')...', false);
      notify();
      retryTimer = setTimeout(startStream, RETRY_MS);
    }

    fetch('/api/council/sessions/' + encodeURIComponent(id) + '/events', {
      signal: ctl.signal,
      headers: { accept: 'text/event-stream' }
    }).then(function (res) {
      if (gen !== generation) return null;
      if (!res.ok || !res.body) {
        stream = null;
        setConn('unavailable', 'The event stream is unavailable (HTTP ' + res.status + ').', true);
        notify();
        return null;
      }
      setConn('live', 'Live: connected. New committed events appear as they happen.', false);
      notify();
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      function pump() {
        return reader.read().then(function (chunk) {
          if (gen !== generation || ctl.signal.aborted) return null;
          if (chunk.done) {
            if (terminal()) {
              stream = null;
              setConn('ended', 'This council has finished.', false);
              notify();
            } else drop('The service ended the stream early.');
            return null;
          }
          buf += decoder.decode(chunk.value, { stream: true });
          var parsed = parseSse(buf);
          buf = parsed.rest;
          if (applyFrames(parsed.frames)) retries = 0;
          if (terminal()) {
            // Finished: nothing more will be committed, so stop listening.
            ctl.abort();
            stream = null;
            setConn('ended', 'This council has finished.', false);
            notify();
            return null;
          }
          notify();
          return pump();
        });
      }
      return pump();
    }).catch(function () {
      drop('Connection lost.');
    });
  }

  // -------------------------------------------------------------- sessions

  function leaveDemo() {
    if (!demo) return;
    if (demo.timer) clearTimeout(demo.timer);
    demo = null;
  }

  function select(id, quiet) {
    if (typeof id !== 'string' || !id) return;
    leaveDemo();
    stopStream();
    generation += 1;
    var gen = generation;
    selectedId = id;
    model = null;
    retries = 0;
    mode = 'loading';
    setConn('idle', '', false);
    if (!quiet) setHash('#session=' + encodeURIComponent(id));
    notify();
    return readSession(id).then(function (record) {
      if (gen !== generation) return;
      model = state.create(record);
      mode = 'live';
      notify();
      startStream();
    }).catch(function (err) {
      if (gen !== generation) return;
      model = null;
      mode = 'empty';
      setConn('unavailable', (err && err.message) || 'Could not open this session.', true);
      notify();
    });
  }

  function refreshList() {
    return fetch('/api/council/sessions', { headers: { accept: 'application/json' } })
      .then(function (res) {
        return res.json().then(function (body) { return { status: res.status, body: body }; });
      })
      .then(function (r) {
        if (r.status === 501) {
          listState = { status: 'unbound', sessions: [], error: 'This service cannot list sessions yet (' +
            (r.body && r.body.code ? r.body.code : 'not bound') + ').' };
        } else if (r.status !== 200 || !r.body || !Array.isArray(r.body.sessions)) {
          throw new Error('The service answered HTTP ' + r.status + '.');
        } else {
          listState = { status: 'ready', sessions: r.body.sessions, error: null };
        }
        notify();
        return listState;
      })
      .catch(function (err) {
        listState = { status: 'error', sessions: [], error: 'Could not reach the council service: ' + ((err && err.message) || 'request failed') };
        notify();
        return listState;
      });
  }

  function openDefault() {
    var newest = listState.sessions[0];
    if (newest) return select(newest.session_id, true);
    leaveDemo();
    stopStream();
    generation += 1;
    selectedId = null;
    model = null;
    mode = 'empty';
    setConn('idle', '', false);
    notify();
    return Promise.resolve();
  }

  // ------------------------------------------------------------------ demo

  function playDemo(d, gen) {
    var next = d.data.timeline[d.index];
    if (!next) return;
    var wait = Math.max(0, next.at_ms - (Date.now() - d.start));
    d.timer = setTimeout(function () {
      if (gen !== generation || demo !== d) return;
      var frame = next.frame;
      state.apply(model, frame);
      // A card's content is revealed only when its card_accepted frame plays.
      var p = frame.payload || {};
      if (frame.type === 'card_accepted') {
        var hit = (d.data.cards || []).filter(function (c) { return c.seat_id === p.seat_id && Number(c.round) === Number(p.round); })[0];
        if (hit) state.applyRecord(model, { cards: [hit] });
      } else if (frame.type === 'verdict_validated' && d.data.verdict) {
        state.applyRecord(model, { verdict: d.data.verdict });
      }
      d.index += 1;
      notify();
      playDemo(d, gen);
    }, wait);
  }

  function startDemo() {
    var prevId = demo ? demo.prevId : selectedId;
    leaveDemo();
    var d = { data: null, index: 0, timer: null, prevId: prevId, start: 0, base: null };
    demo = d; // set now so stopDemo works while the file loads
    stopStream();
    generation += 1;
    var gen = generation;
    selectedId = null;
    model = null;
    mode = 'loading';
    setConn('idle', '', false);
    setHash('#demo');
    notify();
    return fetch('./demo-replay.json', { headers: { accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (gen !== generation || demo !== d) return;
        if (!data || !data.record || !Array.isArray(data.timeline) || data.timeline.length === 0) throw new Error('not a demo file');
        var first = data.timeline[0];
        var firstMs = Date.parse(first.frame && first.frame.created_at);
        d.data = data;
        d.start = Date.now();
        d.base = isFinite(firstMs) ? firstMs - first.at_ms : null;
        model = state.create(data.record);
        mode = 'demo';
        notify();
        playDemo(d, gen);
      })
      .catch(function (err) {
        if (gen !== generation || demo !== d) return;
        demo = null;
        model = null;
        mode = 'empty';
        setConn('unavailable', 'The demo replay could not be loaded (' + ((err && err.message) || 'error') + ').', false);
        notify();
      });
  }

  function stopDemo() {
    if (!demo) return Promise.resolve();
    var prev = demo.prevId;
    leaveDemo();
    setHash('');
    if (prev) return select(prev);
    return openDefault();
  }

  function reconnect() {
    if (demo || !selectedId) {
      if (!demo && mode === 'empty') return openDefault();
      return;
    }
    retries = 0;
    if (!model) return select(selectedId);
    startStream();
  }

  function route() {
    var target = parseHash(root.location && root.location.hash);
    if (target && target.kind === 'demo') return startDemo();
    if (target && target.kind === 'session') return select(target.id);
    return openDefault();
  }

  ns.live = {
    getView: getView, subscribe: subscribe, select: select, refreshList: refreshList,
    startDemo: startDemo, stopDemo: stopDemo, reconnect: reconnect
  };

  // Start: list first, then route. #demo and #session=<id> need no list to open.
  var target = parseHash(root.location && root.location.hash);
  var listing = refreshList();
  if (target) route(); else listing.then(function () { return openDefault(); });

  setInterval(function () { if (!document.hidden) refreshList(); }, LIST_REFRESH_MS);
  if (typeof root.addEventListener === 'function') {
    root.addEventListener('hashchange', function () {
      var t = parseHash(root.location && root.location.hash);
      if (t && t.kind === 'demo' && !demo) startDemo();
      else if (t && t.kind === 'session' && t.id !== selectedId) select(t.id);
    });
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
