/*
 * Council chamber KEY POINTS panel (unit D). Dependency-free, same-origin only.
 *
 * Renders into aside#ch-keypoints only: a KEY POINTS header and an
 * append-only list of milestone lines taken from view.session.keyPoints.
 * Rows are appended as the list grows; existing rows are never rebuilt.
 * The list is rebuilt only when a different session loads (reset).
 * Text is set with textContent only, never parsed as markup.
 */
(function (root) {
  'use strict';

  var ns = root.councilChamber = root.councilChamber || {};
  var EMPTY_TEXT = 'Key points appear here as the council works.';

  // ---------------------------------------------------------------- pure

  function labelOf(point) {
    return point && typeof point.label === 'string' ? point.label : '';
  }

  /**
   * Compare the list already rendered with the next one.
   * append: the points to add, in order. reset: true when the rendered rows
   * are not a prefix of the next list (a different session loaded, or the
   * list shrank); the renderer then clears and `append` holds the full list.
   */
  function diff(prevList, nextList) {
    var prev = Array.isArray(prevList) ? prevList : [];
    var next = Array.isArray(nextList) ? nextList : [];
    var reset = prev.length > next.length;
    for (var i = 0; !reset && i < prev.length; i += 1) {
      if (labelOf(prev[i]) !== labelOf(next[i])) reset = true;
    }
    return { append: reset ? next.slice() : next.slice(prev.length), reset: reset };
  }

  ns.keypoints = { diff: diff, EMPTY_TEXT: EMPTY_TEXT };

  if (typeof document === 'undefined') return;

  // ----------------------------------------------------------------- DOM

  var panel = document.getElementById('ch-keypoints');
  if (!panel) return;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  var title = el('h2', 'ch-kp-title ch-eyebrow', 'KEY POINTS');
  title.id = 'ch-keypoints-title';
  var list = el('ol', 'ch-kp-list');
  list.setAttribute('aria-labelledby', 'ch-keypoints-title');
  list.setAttribute('aria-live', 'polite');
  list.setAttribute('aria-relevant', 'additions');
  var empty = el('p', 'ch-kp-empty', EMPTY_TEXT);
  panel.classList.add('ch-kp');
  panel.appendChild(title);
  panel.appendChild(list);
  panel.appendChild(empty);

  function detailOf(point) {
    return point && typeof point.detail === 'string' ? point.detail : '';
  }

  // Add, update or remove the detail paragraph inside an existing row.
  function setDetail(row, detail) {
    if (!detail) {
      if (row.detailEl) row.item.removeChild(row.detailEl);
      row.detailEl = null;
    } else if (row.detailEl) {
      row.detailEl.textContent = detail;
    } else {
      row.detailEl = el('p', 'ch-kp-detail', detail);
      row.item.appendChild(row.detailEl);
    }
    row.detail = detail;
  }

  function buildRow(point) {
    var item = el('li', 'ch-kp-item');
    var line = el('div', 'ch-kp-row');
    line.appendChild(el('span', 'ch-kp-label', labelOf(point)));
    var rule = el('span', 'ch-kp-rule');
    rule.setAttribute('aria-hidden', 'true');
    line.appendChild(rule);
    item.appendChild(line);
    var row = { item: item, detailEl: null, detail: '' };
    setDetail(row, detailOf(point));
    return row;
  }

  var rows = [];
  var renderedSession = null;

  function render(view) {
    var session = view && view.session ? view.session : null;
    var next = session && Array.isArray(session.keyPoints) ? session.keyPoints : [];
    var sessionId = session ? session.id : null;
    var change = diff(rows.map(function (r) { return r.point; }), next);
    // Every session starts with the same first label, so a new id also resets.
    if (sessionId !== renderedSession && rows.length > 0) change = { append: next.slice(), reset: true };
    if (change.reset) {
      while (list.firstChild) list.removeChild(list.firstChild);
      rows = [];
    }
    // Details arrive after a row is drawn: update in place, keep node identity.
    rows.forEach(function (row, i) {
      var detail = detailOf(next[i]);
      if (detail !== row.detail) setDetail(row, detail);
    });
    change.append.forEach(function (point) {
      var row = buildRow(point);
      row.point = point;
      list.appendChild(row.item);
      rows.push(row);
    });
    renderedSession = sessionId;
    empty.hidden = rows.length > 0;
  }

  render(null);
  if (ns.live && typeof ns.live.subscribe === 'function') ns.live.subscribe(render);
})(typeof globalThis !== 'undefined' ? globalThis : this);
