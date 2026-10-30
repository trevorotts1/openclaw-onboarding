/*
 * Council chamber, unit C: the room panel (section#ch-room).
 *
 * Nine 3D bust seats on a shallow arc, a typing bubble above each head, a name
 * pill per seat, one spotlight seat, and a dome-shaped table in front holding
 * the round panel (round label, timer, headline, explainer, weighing line and
 * progress bar). Clicking a seat dispatches chamber:open-seat; the seat card
 * itself belongs to unit E.
 *
 * Pure helpers (arcLayout, weighingParts, seatLabel, progressModel,
 * connectionNote) are exposed on councilChamber.room for node:vm tests. The DOM
 * part only runs in a browser and writes text through textContent only.
 */
(function (root) {
  var ns = (root.councilChamber = root.councilChamber || {});
  var room = (ns.room = ns.room || {});

  // Phone: the front row sits this many percent of the seat area below the back
  // row. chamber-room.css uses the same number as --ch-room-drop (.56) so the
  // seat area is exactly tall enough. The arc uses an 18 percent drop (.18).
  var ARC_DROP = 18;
  var COMPACT_DROP = 56;

  function r2(v) {
    return Math.round(v * 100) / 100;
  }

  /*
   * Seat positions as percentages of the seat area. Arc: x evenly spaced across
   * 6..94, y drops ((2t-1)^2 * 18) so the centre is highest, z grows toward the
   * edges so edge seats are drawn in front. Compact (phone): two rows, the back
   * row takes the first ceil(n/2) seats, the front row the rest, offset by half
   * a step so the front busts sit between the back ones.
   */
  room.arcLayout = function arcLayout(n, compact) {
    var out = [];
    var count = Math.max(0, Math.floor(Number(n) || 0));
    var i;
    if (count === 0) return out;
    if (!compact) {
      for (i = 0; i < count; i += 1) {
        var t = count === 1 ? 0.5 : i / (count - 1);
        var edge = Math.abs(2 * t - 1);
        out.push({ xPct: r2(6 + 88 * t), yPct: r2((2 * t - 1) * (2 * t - 1) * ARC_DROP), z: Math.round(edge * 10) });
      }
      return out;
    }
    var back = Math.ceil(count / 2);
    var front = count - back;
    var step = back > 1 ? 88 / (back - 1) : 0;
    for (i = 0; i < count; i += 1) {
      var inBack = i < back;
      var k = inBack ? i : i - back;
      var rowN = inBack ? back : front;
      var x = back > 1 ? 6 + k * step + (inBack ? 0 : step / 2) : 50;
      var e = rowN > 1 ? Math.abs((2 * k) / (rowN - 1) - 1) : 0;
      out.push({ xPct: r2(x), yPct: inBack ? 0 : COMPACT_DROP, z: (inBack ? 0 : 5) + Math.round(e * 4) });
    }
    return out;
  };

  function findSeat(seats, id) {
    var found = null;
    var i;
    if (seats && typeof seats.get === 'function') found = seats.get(id);
    else if (Array.isArray(seats)) {
      for (i = 0; i < seats.length; i += 1) if (seats[i] && seats[i].id === id) found = seats[i];
    } else if (seats && typeof seats === 'object') found = seats[id] || null;
    if (!found && ns.seats && typeof ns.seats.get === 'function') found = ns.seats.get(id);
    return found || null;
  }

  /* The weighing line: bold name, then the rest in muted text. */
  room.weighingParts = function weighingParts(weighing, seats) {
    if (!weighing) return { name: '', rest: '' };
    var text = weighing.text == null ? '' : String(weighing.text);
    if (weighing.kind === 'chair') return { name: 'The chair', rest: ' is weighing: ' + text };
    var seat = findSeat(seats, weighing.seatId) || {};
    var name = seat.short || seat.name || String(weighing.seatId || '');
    if (weighing.kind === 'said') return { name: name, rest: ' said: “' + text + '”' };
    return { name: name, rest: ' is weighing: ' + (seat.weighing || text) };
  };

  var STATUS_TEXT = { writing: 'Writing now', done: 'Position in', idle: 'Has not spoken yet', blocked: 'No accepted response recorded' };
  // A blocked seat says what the typed blocked_reason recorded, never the
  // generic "has not spoken yet" when an output was rejected or a call failed.
  var BLOCKED_TEXT = {
    rejected: 'Response failed validation',
    provider_failed: 'Provider request failed',
    no_result: 'No result recorded',
    unclassified: 'No accepted response recorded'
  };

  room.seatLabel = function seatLabel(seat, status, blockedKind) {
    var state = status === 'blocked' ? (BLOCKED_TEXT[blockedKind] || STATUS_TEXT.blocked) : (STATUS_TEXT[status] || STATUS_TEXT.idle);
    return seat.name + ', ' + seat.domain + '. ' + state;
  };

  /* progress.value is a fraction 0..1 (values above 1 are read as percent). */
  room.progressModel = function progressModel(progress) {
    if (!progress || progress.indeterminate) return { indeterminate: true, pct: 0 };
    var v = Number(progress.value);
    if (!isFinite(v) || v < 0) v = 0;
    var pct = v > 1 ? v : v * 100;
    return { indeterminate: false, pct: Math.min(100, Math.round(pct * 10) / 10) };
  };

  var NOTE_STATUSES = { retrying: 1, lost: 1, ended: 1, unavailable: 1 };
  room.connectionNote = function connectionNote(connection) {
    if (!connection || !NOTE_STATUSES[connection.status] || !connection.text) return null;
    return { text: String(connection.text), canReconnect: connection.canReconnect === true };
  };

  /*
   * Click target = the visible bust, not its 150px box. Seats are about 100px
   * apart, so the transparent sides of one bust sit on top of its neighbour's
   * face; the browser hit-tests boxes, not alpha. This turns the portrait's
   * alpha channel (RGBA bytes, w x h) into a clip-path polygon (left edge down,
   * right edge back up, one band per pixel row). clip-path is honoured by hit
   * testing, so the pointer sees exactly the painted shape. Returns null when
   * nothing is opaque.
   */
  room.silhouette = function silhouette(rgba, w, h, threshold) {
    var limit = threshold == null ? 16 : threshold;
    var left = [];
    var right = [];
    var x;
    var y;
    for (y = 0; y < h; y += 1) {
      var lo = -1;
      var hi = -1;
      for (x = 0; x < w; x += 1) {
        if (rgba[(y * w + x) * 4 + 3] > limit) {
          if (lo < 0) lo = x;
          hi = x;
        }
      }
      if (lo >= 0) {
        left.push([lo, y]);
        right.push([hi + 1, y]);
      }
    }
    if (!left.length) return null;
    var pts = [];
    function add(px, py) {
      var last = pts[pts.length - 1];
      if (!last || last[0] !== px || last[1] !== py) pts.push([px, py]);
    }
    left.forEach(function (p) {
      add(p[0], p[1]);
      add(p[0], p[1] + 1);
    });
    for (var i = right.length - 1; i >= 0; i -= 1) {
      add(right[i][0], right[i][1] + 1);
      add(right[i][0], right[i][1]);
    }
    return (
      'polygon(' +
      pts
        .map(function (p) {
          return r2((p[0] / w) * 100) + '% ' + r2((p[1] / h) * 100) + '%';
        })
        .join(',') +
      ')'
    );
  };

  if (typeof document === 'undefined') return;

  var EMPTY_HEADLINE = 'No council in session.';
  var EMPTY_EXPLAIN = 'Ask a new question to convene the nine advisors, or watch a demo replay.';

  var mount = null;
  var stage;
  var seatsBox;
  var seatRefs = {};
  var seatKey = '';
  var layoutKey = '';
  var els = {};
  var mq = typeof root.matchMedia === 'function' ? root.matchMedia('(max-width: 599.98px)') : null;
  var lastView = null;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  function setHidden(node, hidden) {
    if (node.hidden !== hidden) node.hidden = hidden;
  }

  function setAttr(node, name, value) {
    if (node.getAttribute(name) !== value) node.setAttribute(name, value);
  }

  function seatData(id) {
    var data = ns.seats && typeof ns.seats.get === 'function' ? ns.seats.get(id) : null;
    return data || { id: id, name: id, short: id, domain: '', owns: '', weighing: '' };
  }

  function portraitSources(id) {
    if (ns.seats && typeof ns.seats.portraitSources === 'function') return ns.seats.portraitSources(id);
    return ['portraits/' + id + '.webp', 'portraits/' + id + '.svg'];
  }

  function openSeat(id, opener) {
    document.dispatchEvent(new CustomEvent('chamber:open-seat', { detail: { seatId: id, opener: opener } }));
  }

  var shapeCanvas = null;
  function shapeOf(img) {
    try {
      if (!shapeCanvas) {
        shapeCanvas = document.createElement('canvas');
        shapeCanvas.width = 160;
        shapeCanvas.height = 200;
      }
      var cx = shapeCanvas.getContext('2d', { willReadFrequently: true });
      cx.clearRect(0, 0, 160, 200);
      cx.drawImage(img, 0, 0, 160, 200);
      return room.silhouette(cx.getImageData(0, 0, 160, 200).data, 160, 200) || '';
    } catch (e) {
      return '';
    }
  }

  function buildSeat(id) {
    var data = seatData(id);
    var btn = el('button', 'ch-seat');
    btn.type = 'button';
    btn.setAttribute('aria-haspopup', 'dialog');
    btn.setAttribute('data-seat-id', id);

    var bubbleSlot = el('span', 'ch-seat-bubbleslot');
    var bubble = el('span', 'ch-bubble');
    bubble.setAttribute('aria-hidden', 'true');
    bubble.hidden = true;
    var dots = el('span', 'ch-bubble-dots');
    for (var d = 0; d < 3; d += 1) dots.appendChild(el('span', 'ch-bubble-dot'));
    var bubbleText = el('span', 'ch-bubble-text');
    var bubbleCheck = el('span', 'ch-bubble-check', '✓');
    bubble.appendChild(dots);
    bubble.appendChild(bubbleText);
    bubble.appendChild(bubbleCheck);
    bubbleSlot.appendChild(bubble);

    var img = document.createElement('img');
    img.className = 'ch-seat-img';
    img.alt = '';
    img.draggable = false;
    img.decoding = 'async';
    var sources = portraitSources(id);
    var tried = 0;
    var bust = el('span', 'ch-seat-bust');
    img.addEventListener('load', function () {
      // Only the alpha cutout gets a shape; the svg medallion keeps the default
      // one-step-wide column from the stylesheet.
      bust.style.clipPath = tried === 0 ? shapeOf(img) : '';
    });
    img.addEventListener('error', function () {
      tried += 1;
      bust.style.clipPath = '';
      if (tried < sources.length) {
        img.classList.add('ch-seat-img--medallion');
        img.src = sources[tried];
      } else {
        img.style.visibility = 'hidden';
      }
    });
    img.src = sources[0];
    bust.appendChild(img);

    var pillSlot = el('span', 'ch-seat-pillslot');
    var pill = el('span', 'ch-seat-pill');
    pill.textContent = data.pill || data.name || data.short;
    pillSlot.appendChild(pill);

    btn.appendChild(bubbleSlot);
    btn.appendChild(bust);
    btn.appendChild(pillSlot);
    btn.addEventListener('click', function () {
      openSeat(id, btn);
    });
    return { id: id, data: data, btn: btn, bubble: bubble, bubbleText: bubbleText };
  }

  /*
   * A duplicated room is a stale stage, a stale seat box or a second name pill
   * for the same seat: the panel clips it, so it reads as a second row of
   * portraits with the same names. The page owns one stage and one seat box.
   * Runs on every render through the guarded helpers below; a minimal test DOM
   * without selectors keeps its single stage and is never touched.
   */
  function removeNode(node) {
    if (node && node.parentNode) node.parentNode.removeChild(node);
  }

  function duplicateSeatId(pill) {
    var slot = pill.parentNode;
    var btn = slot ? slot.parentNode : null;
    return btn && btn.getAttribute ? btn.getAttribute('data-seat-id') : '';
  }

  function pruneDuplicates() {
    if (!mount) return;
    try {
      if (typeof mount.querySelectorAll !== 'function') return;
      var stages = mount.querySelectorAll('.ch-room-stage');
      for (var i = stages.length - 1; i >= 1; i -= 1) removeNode(stages[i]);
      var boxes = mount.querySelectorAll('.ch-room-seats');
      for (var j = boxes.length - 1; j >= 1; j -= 1) removeNode(boxes[j]);
      var pills = mount.querySelectorAll('.ch-seat-pill');
      var seen = {};
      for (var k = 0; k < pills.length; k += 1) {
        var id = duplicateSeatId(pills[k]);
        if (id && seen[id]) removeNode(pills[k]);
        else if (id) seen[id] = true;
      }
    } catch (e) {
      /* no selector support: the DOM path built exactly one stage itself */
    }
  }

  function ensureSeats(ids) {
    var key = ids.join('|');
    if (key === seatKey) return;
    pruneDuplicates();
    seatKey = key;
    layoutKey = '';
    seatRefs = {};
    while (seatsBox.firstChild) seatsBox.removeChild(seatsBox.firstChild);
    ids.forEach(function (id) {
      var ref = buildSeat(id);
      seatRefs[id] = ref;
      seatsBox.appendChild(ref.btn);
    });
  }

  function applyLayout(ids) {
    var compact = !!(mq && mq.matches);
    var key = ids.length + ':' + compact;
    if (key === layoutKey) return;
    layoutKey = key;
    var pts = room.arcLayout(ids.length, compact);
    ids.forEach(function (id, i) {
      var b = seatRefs[id].btn;
      b.style.left = pts[i].xPct + '%';
      b.style.top = pts[i].yPct + '%';
      b.style.setProperty('--z', String(pts[i].z));
    });
  }

  function renderSeat(ref, entry) {
    var status = entry && entry.status ? entry.status : 'idle';
    var bubble = (entry && entry.bubble) || { kind: 'none', text: '' };
    var kind = bubble.kind || 'none';
    var spot = !!(entry && entry.spotlight);
    setAttr(ref.btn, 'aria-label', room.seatLabel(ref.data, status, entry && entry.blockedKind));
    setAttr(ref.btn, 'data-status', status);
    ref.btn.classList.toggle('ch-seat--spot', spot);
    ref.btn.classList.toggle('ch-seat--speaking', kind === 'line');
    setAttr(ref.bubble, 'data-kind', kind);
    setHidden(ref.bubble, kind === 'none');
    setText(ref.bubbleText, kind === 'line' ? String(bubble.text || '') : '');
  }

  function buildRound() {
    var table = el('div', 'ch-table');
    table.appendChild(el('div', 'ch-table-mark'));
    var round = el('div', 'ch-round');

    var top = el('div', 'ch-round-top');
    els.label = el('span', 'ch-round-label');
    els.dot = el('span', 'ch-round-dot', '●');
    els.dot.setAttribute('aria-hidden', 'true');
    els.labelText = document.createTextNode('');
    els.label.appendChild(els.dot);
    els.label.appendChild(els.labelText);
    els.timer = el('span', 'ch-round-timer');
    els.timer.setAttribute('aria-hidden', 'true');
    top.appendChild(els.label);
    top.appendChild(els.timer);

    els.headline = el('p', 'ch-round-headline');
    els.explain = el('p', 'ch-round-explain');
    els.counts = el('p', 'ch-round-counts');
    els.counts.hidden = true;
    els.weighing = el('p', 'ch-round-weighing');
    els.weighName = el('b', 'ch-round-name');
    els.weighRest = el('span', 'ch-round-rest');
    els.weighing.appendChild(els.weighName);
    els.weighing.appendChild(els.weighRest);

    els.track = el('div', 'ch-round-track');
    els.track.setAttribute('aria-hidden', 'true');
    els.fill = el('span', 'ch-round-fill');
    els.track.appendChild(els.fill);

    // Native, keyboard-safe disclosure: a raw validator/schema message is
    // available on demand, escaped by textContent, and never in the summary.
    els.tech = el('details', 'ch-round-tech');
    els.tech.hidden = true;
    els.techSummary = el('summary', 'ch-round-tech-summary', 'Technical details');
    els.techList = el('ul', 'ch-round-tech-list');
    els.tech.appendChild(els.techSummary);
    els.tech.appendChild(els.techList);
    els.techKey = '';

    els.conn = el('div', 'ch-round-conn');
    els.connText = el('span', 'ch-round-conn-text');
    els.conn.setAttribute('role', 'status');
    els.reconnect = el('button', 'ch-btn ch-round-btn', 'Reconnect');
    els.reconnect.type = 'button';
    els.reconnect.addEventListener('click', function () {
      if (ns.live && ns.live.reconnect) ns.live.reconnect();
    });
    els.conn.appendChild(els.connText);
    els.conn.appendChild(els.reconnect);

    els.actions = el('div', 'ch-round-actions');
    els.newQ = el('button', 'ch-btn ch-btn--primary ch-round-btn', 'New question');
    els.newQ.type = 'button';
    els.newQ.addEventListener('click', function () {
      document.dispatchEvent(new CustomEvent('chamber:open-composer'));
    });
    els.demo = el('button', 'ch-btn ch-round-btn', 'Watch a demo replay');
    els.demo.type = 'button';
    els.replay = el('button', 'ch-btn ch-round-btn', 'Replay again');
    els.replay.type = 'button';
    [els.demo, els.replay].forEach(function (b) {
      b.addEventListener('click', function () {
        if (ns.live && ns.live.startDemo) ns.live.startDemo();
      });
    });
    els.actions.appendChild(els.newQ);
    els.actions.appendChild(els.demo);
    els.actions.appendChild(els.replay);

    els.sr = el('div', 'ch-round-sr');
    els.sr.setAttribute('aria-live', 'polite');
    els.sr.setAttribute('aria-atomic', 'true');

    [top, els.headline, els.explain, els.counts, els.weighing, els.track, els.tech, els.conn, els.actions, els.sr].forEach(function (n) {
      round.appendChild(n);
    });
    table.appendChild(round);
    return table;
  }

  function renderRound(view) {
    var session = view.session;
    var mode = view.mode;
    var r = (session && session.round) || null;
    var empty = !session;

    if (empty) {
      setText(els.headline, mode === 'loading' ? 'Opening the chamber.' : EMPTY_HEADLINE);
      setText(els.explain, mode === 'loading' ? '' : EMPTY_EXPLAIN);
    } else {
      setText(els.headline, (r && r.headline) || '');
      setText(els.explain, (r && r.explain) || '');
    }
    setHidden(els.explain, !els.explain.textContent);

    var partial = !!(r && r.countsFinal === false && session && session.voters > 0 &&
      (session.status === 'blocked' || session.status === 'failed'));
    setText(els.counts, partial ? 'The preference tally is partial and not final.' : '');
    setHidden(els.counts, !partial);

    var tech = r && Array.isArray(r.blockedDetails) ? r.blockedDetails : [];
    setHidden(els.tech, tech.length === 0);
    if (tech.length) {
      var key = tech.map(function (d) { return String((d && d.label) || '') + '\u0000' + String((d && d.text) || ''); }).join('\u0001');
      if (key !== els.techKey) {
        els.techKey = key;
        while (els.techList.firstChild) els.techList.removeChild(els.techList.firstChild);
        tech.forEach(function (d) {
          var item = el('li', 'ch-round-tech-item');
          item.appendChild(el('span', 'ch-round-tech-label', String((d && d.label) || '')));
          item.appendChild(el('span', 'ch-round-tech-text', String((d && d.text) || '')));
          els.techList.appendChild(item);
        });
      }
    }

    var showLabel = !!(r && (r.label || r.timer));
    setHidden(els.label.parentNode, !showLabel);
    if (els.labelText.nodeValue !== ' ' + ((r && r.label) || '')) els.labelText.nodeValue = ' ' + ((r && r.label) || '');
    setText(els.timer, (r && r.timer) || '');

    var parts = r ? room.weighingParts(r.weighing, ns.seats) : { name: '', rest: '' };
    setText(els.weighName, parts.name);
    setText(els.weighRest, parts.rest);
    setHidden(els.weighing, !parts.name);

    var showTrack = !!r;
    setHidden(els.track, !showTrack);
    if (r) {
      var pm = room.progressModel(r.progress);
      setAttr(els.track, 'data-mode', pm.indeterminate ? 'indeterminate' : 'determinate');
      els.fill.style.width = pm.indeterminate ? '' : pm.pct + '%';
    }

    var note = room.connectionNote(view.connection);
    setHidden(els.conn, !note);
    setText(els.connText, note ? note.text : '');
    setHidden(els.reconnect, !(note && note.canReconnect));

    var finishedDemo = !!(session && session.demo && session.status === 'complete');
    setHidden(els.newQ, !(empty && mode === 'empty'));
    setHidden(els.demo, !(empty && mode === 'empty'));
    setHidden(els.replay, !finishedDemo);
    setHidden(els.actions, !(empty && mode === 'empty') && !finishedDemo);

    var sr = ((r && r.headline) || (empty ? els.headline.textContent : '')) + ((r && r.progressText) ? ' ' + r.progressText : '');
    setText(els.sr, sr);
  }

  function render(view) {
    lastView = view;
    pruneDuplicates();
    var session = view.session || null;
    var ids = session && session.seats && session.seats.length
      ? session.seats.map(function (s) { return s.id; })
      : (ns.seats && ns.seats.order ? ns.seats.order.slice() : []);
    ensureSeats(ids);
    applyLayout(ids);
    var byId = {};
    if (session && session.seats) session.seats.forEach(function (s) { byId[s.id] = s; });
    ids.forEach(function (id) {
      renderSeat(seatRefs[id], byId[id]);
    });
    renderRound(view);
    setAttr(mount, 'data-mode', view.mode || 'loading');
  }

  function init() {
    mount = document.getElementById('ch-room');
    if (!mount) return;
    // Defence in depth only. A second evaluation (double script tag, a cached
    // inline copy, a hot reload) converges on the stage already mounted
    // instead of stacking a second room under the first. The duplicated
    // portrait row seen in a screenshot is NOT proven to come from a second
    // stage: init clears #ch-room before appending one stage, and index.html
    // has one #ch-room and one script tag. Browser capture is the only
    // discriminator; this prune removes only extra stages, extra seat boxes
    // and a second pill for the same data-seat-id, never unique user DOM.
    if (room._booted) {
      pruneDuplicates();
      return;
    }
    room._booted = true;
    pruneDuplicates();
    mount.classList.add('ch-room-panel');
    if (!mount.hasAttribute('aria-label')) mount.setAttribute('aria-label', 'The council room');
    stage = el('div', 'ch-room-stage');
    seatsBox = el('div', 'ch-room-seats');
    seatsBox.setAttribute('role', 'group');
    seatsBox.setAttribute('aria-label', 'Council seats');
    stage.appendChild(seatsBox);
    stage.appendChild(buildRound());
    while (mount.firstChild) mount.removeChild(mount.firstChild);
    mount.appendChild(stage);

    ns.room.render = render;
    if (mq) {
      var relayout = function () {
        layoutKey = '';
        if (lastView) render(lastView);
      };
      if (mq.addEventListener) mq.addEventListener('change', relayout);
      else if (mq.addListener) mq.addListener(relayout);
    }
    if (ns.live && typeof ns.live.subscribe === 'function') ns.live.subscribe(render);
    else render({ mode: 'empty', connection: null, session: null });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(typeof globalThis !== 'undefined' ? globalThis : this);
