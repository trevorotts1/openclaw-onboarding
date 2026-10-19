/*
 * Council chamber live view (W27). Dependency-free, same-origin only.
 *
 * Reads real sessions from GET /api/council/sessions, and for the selected
 * session streams GET /api/council/sessions/<id>/events (committed journal
 * rows only). Nothing here invents a session, a seat stance or an event:
 * every line on screen is a field the service returned. The fictional
 * sample in index.html lives in its own hidden container and is never
 * rendered into the live area.
 *
 * The stream is read with fetch (not EventSource) so any committed event
 * type is delivered and a finished stream does not silently reconnect and
 * replay. All DOM text is set with textContent, never parsed as markup.
 */
(function () {
  'use strict';

  var SEAT_NAMES = {
    'simon-sinek': 'Simon Sinek',
    'td-jakes': 'T. D. Jakes',
    'oprah-winfrey': 'Oprah Winfrey',
    'tiffany-aliche': 'Tiffany Aliche',
    'russell-brunson': 'Russell Brunson',
    'michelle-obama': 'Michelle Obama',
    'brene-brown': 'Brené Brown',
    'dennis-kimbro': 'Dr. Dennis Kimbro',
    'les-brown': 'Les Brown'
  };
  var MAX_EVENTS_SHOWN = 100;
  var MAX_RETRIES = 5;
  var RETRY_MS = 3000;
  var LIST_REFRESH_MS = 15000;

  // ---------------------------------------------------------------- pure

  function seatName(id) {
    return Object.prototype.hasOwnProperty.call(SEAT_NAMES, id) ? SEAT_NAMES[id] : String(id);
  }

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

  function newModel(seatIds, state) {
    var order = Array.isArray(seatIds) ? seatIds.slice() : [];
    var seats = {};
    order.forEach(function (id) { seats[id] = []; });
    return { order: order, seats: seats, events: [], maxSeq: 0, state: state || null };
  }

  /** Apply one committed frame. Returns false for a duplicate or malformed frame. */
  function applyFrame(model, frame) {
    if (!frame || typeof frame.sequence !== 'number' || frame.sequence <= model.maxSeq) return false;
    model.maxSeq = frame.sequence;
    model.events.push(frame);
    if (typeof frame.to_state === 'string' && frame.to_state) model.state = frame.to_state;
    var payload = frame.payload;
    if (frame.type === 'card_accepted' && payload && typeof payload.seat_id === 'string') {
      if (!model.seats[payload.seat_id]) {
        model.seats[payload.seat_id] = [];
        model.order.push(payload.seat_id);
      }
      model.seats[payload.seat_id].push(payload.round === undefined ? '?' : String(payload.round));
    }
    return true;
  }

  function label(value) {
    return String(value).replace(/_/g, ' ');
  }

  function describeFrame(frame) {
    var parts = [label(frame.type)];
    if (typeof frame.to_state === 'string' && frame.to_state) parts.push('to ' + label(frame.to_state));
    var p = frame.payload;
    if (p && typeof p.seat_id === 'string') {
      parts.push(seatName(p.seat_id) + (p.round !== undefined ? ', round ' + p.round : ''));
    }
    return parts.join(' - ');
  }

  var api = { parseSse: parseSse, newModel: newModel, applyFrame: applyFrame, describeFrame: describeFrame, seatName: seatName };
  if (typeof globalThis !== 'undefined') globalThis.councilLive = api;

  // ----------------------------------------------------------------- DOM

  if (typeof document === 'undefined') return;
  var $ = function (id) { return document.getElementById(id); };
  var liveRoot = $('live-root');
  if (!liveRoot) return;

  var els = {
    status: $('live-status'),
    refresh: $('live-refresh'),
    list: $('session-list'),
    empty: $('live-empty'),
    error: $('live-error'),
    room: $('live-room'),
    question: $('room-question'),
    meta: $('room-meta'),
    seats: $('room-seats'),
    events: $('room-events'),
    conn: $('room-conn'),
    reconnect: $('room-reconnect'),
    sampleRoot: $('sample-root'),
    sampleToggle: $('sample-toggle')
  };

  function el(tag, text, cls) {
    var node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function show(node, on) { if (on) node.removeAttribute('hidden'); else node.setAttribute('hidden', ''); }
  function when(iso) {
    var d = new Date(iso);
    return isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
  }

  var selectedId = null;
  var model = null;
  var record = null;
  var stream = null;
  var retries = 0;
  var retryTimer = null;
  var lastList = [];

  function stopStream() {
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    if (stream) { stream.abort(); stream = null; }
  }

  function setConn(text, canReconnect) {
    els.conn.textContent = text;
    show(els.reconnect, !!canReconnect);
  }

  function renderRoom() {
    if (!model || !record) return;
    var brief = record.brief || {};
    var spec = record.spec || {};
    els.question.textContent = brief.question || record.session_id;
    clear(els.meta);
    var state = model.state || (record.state && record.state.state) || 'unknown';
    els.meta.appendChild(el('span', 'State: ' + label(state), 'council-meta'));
    els.meta.appendChild(el('span', ' | Mode: ' + (spec.mode || 'unknown'), 'council-meta'));
    els.meta.appendChild(el('span', ' | Events received: ' + model.events.length, 'council-meta'));
    if (record.sample) {
      els.meta.appendChild(el('span', 'Synthetic sample session (flagged by the service)', 'council-mode-badge'));
    }

    clear(els.seats);
    model.order.forEach(function (id) {
      var rounds = model.seats[id] || [];
      var li = el('li', null, 'live-seat');
      li.setAttribute('data-seat-id', id);
      li.setAttribute('data-status', rounds.length ? 'reported' : 'waiting');
      li.appendChild(el('strong', seatName(id)));
      li.appendChild(el('span', rounds.length
        ? ' - card accepted (round ' + rounds.join(', ') + ')'
        : ' - no card accepted yet'));
      els.seats.appendChild(li);
    });

    clear(els.events);
    model.events.slice(-MAX_EVENTS_SHOWN).reverse().forEach(function (frame) {
      var li = el('li');
      li.appendChild(el('span', '#' + frame.sequence + ' ', 'council-meta'));
      li.appendChild(el('span', describeFrame(frame)));
      if (frame.created_at) li.appendChild(el('span', ' (' + when(frame.created_at) + ')', 'council-meta'));
      els.events.appendChild(li);
    });
  }

  function startStream() {
    stopStream();
    var id = selectedId;
    var ctl = new AbortController();
    stream = ctl;
    setConn(retries ? 'Reconnecting...' : 'Connecting to the event stream...', false);
    fetch('/api/council/sessions/' + encodeURIComponent(id) + '/events', {
      signal: ctl.signal,
      headers: { accept: 'text/event-stream' }
    }).then(function (res) {
      if (!res.ok || !res.body) {
        setConn('The event stream is unavailable (HTTP ' + res.status + ').', true);
        return null;
      }
      retries = 0;
      setConn('Live: connected. New committed events appear as they happen.', false);
      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buf = '';
      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) {
            setConn('The service ended the stream after ' + model.events.length + ' events.', true);
            return null;
          }
          buf += decoder.decode(chunk.value, { stream: true });
          var parsed = parseSse(buf);
          buf = parsed.rest;
          var changed = false;
          parsed.frames.forEach(function (frame) { if (applyFrame(model, frame)) changed = true; });
          if (changed) renderRoom();
          return pump();
        });
      }
      return pump();
    }).catch(function () {
      if (ctl.signal.aborted || id !== selectedId) return;
      if (retries >= MAX_RETRIES) {
        setConn('Lost the event stream. Use Reconnect to try again.', true);
        return;
      }
      retries += 1;
      setConn('Connection lost; retrying (' + retries + ' of ' + MAX_RETRIES + ')...', false);
      retryTimer = setTimeout(startStream, RETRY_MS);
    });
  }

  function selectSession(id) {
    if (id === selectedId && stream) return;
    stopStream();
    selectedId = id;
    retries = 0;
    renderList(lastList);
    show(els.room, true);
    els.question.textContent = 'Loading session...';
    clear(els.seats); clear(els.events); clear(els.meta);
    setConn('', false);
    fetch('/council/' + encodeURIComponent(id), { headers: { accept: 'application/json' } })
      .then(function (res) {
        if (res.status === 404) throw new Error('This session is no longer known to the service.');
        if (!res.ok) throw new Error('The service answered HTTP ' + res.status + '.');
        return res.json();
      })
      .then(function (body) {
        if (id !== selectedId) return;
        record = body.session;
        if (!record) throw new Error('The service returned no session record.');
        var seatIds = record.spec && record.spec.seat_ids;
        model = newModel(seatIds, record.state && record.state.state);
        renderRoom();
        els.question.focus();
        startStream();
      })
      .catch(function (err) {
        if (id !== selectedId) return;
        els.question.textContent = 'Could not open this session.';
        setConn(err.message || 'Request failed.', false);
      });
  }

  function renderList(sessions) {
    clear(els.list);
    sessions.forEach(function (s) {
      var li = el('li');
      var btn = el('button', null, 'council-session-btn');
      btn.type = 'button';
      btn.setAttribute('aria-pressed', s.session_id === selectedId ? 'true' : 'false');
      btn.appendChild(el('strong', s.question || s.session_id));
      btn.appendChild(el('span', label(s.state) + ' | ' + s.mode + ' | ' + when(s.created_at) +
        (s.sample ? ' | synthetic sample session' : ''), 'council-meta'));
      btn.addEventListener('click', function () { selectSession(s.session_id); });
      li.appendChild(btn);
      els.list.appendChild(li);
    });
  }

  function loadList() {
    els.status.textContent = 'Loading council sessions...';
    return fetch('/api/council/sessions', { headers: { accept: 'application/json' } })
      .then(function (res) {
        return res.json().then(function (body) { return { status: res.status, body: body }; });
      })
      .then(function (r) {
        show(els.error, false);
        if (r.status === 501) {
          lastList = [];
          renderList(lastList);
          show(els.empty, false);
          els.error.textContent = 'This service cannot list sessions yet (' +
            (r.body && r.body.code ? r.body.code : 'not bound') + '). Nothing is shown rather than guessing.';
          show(els.error, true);
          els.status.textContent = 'Session list unavailable.';
          return;
        }
        if (r.status !== 200 || !r.body || !Array.isArray(r.body.sessions)) {
          throw new Error('The service answered HTTP ' + r.status + '.');
        }
        lastList = r.body.sessions;
        renderList(lastList);
        show(els.empty, lastList.length === 0);
        els.status.textContent = lastList.length === 0
          ? 'No council sessions yet.'
          : lastList.length + (lastList.length === 1 ? ' council session.' : ' council sessions.') +
            ' Choose one to watch it.';
      })
      .catch(function (err) {
        els.error.textContent = 'Could not reach the council service: ' + (err.message || 'request failed') + '.';
        show(els.error, true);
        els.status.textContent = 'Session list unavailable.';
      });
  }

  els.refresh.addEventListener('click', function () { loadList(); });
  els.reconnect.addEventListener('click', function () { retries = 0; startStream(); });

  // Live and sample are mutually exclusive; the sample is never rendered into the live area.
  var sampleOn = false;
  function setSample(on) {
    sampleOn = on;
    show(els.sampleRoot, on);
    show(liveRoot, !on);
    els.sampleToggle.setAttribute('aria-expanded', on ? 'true' : 'false');
    els.sampleToggle.textContent = on ? 'Back to live council sessions' : 'Show the fictional sample (not real data)';
    if (on) stopStream(); else if (selectedId && model) startStream();
  }
  show(els.sampleToggle, true);
  els.sampleToggle.addEventListener('click', function () { setSample(!sampleOn); });

  loadList();
  setInterval(function () { if (!document.hidden && !sampleOn) loadList(); }, LIST_REFRESH_MS);
})();
