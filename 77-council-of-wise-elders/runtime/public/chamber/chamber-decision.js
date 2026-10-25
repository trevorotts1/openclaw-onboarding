/*
 * Council chamber decision header (W29 unit B). Dependency-free, same-origin.
 *
 * Renders into section#ch-decision only: the question as the page title, the
 * options A-D with a letter chip, label, thin bar and trailing value, and the
 * verdict badge / recommended mark. Every number comes from the view the live
 * store publishes; nothing here invents a position. DOM text uses textContent
 * and only nodes whose text changed are touched.
 */
(function (root) {
  'use strict';
  var ns = (root.councilChamber = root.councilChamber || {});

  // ---------------------------------------------------------------- pure

  function pct(share) {
    var n = typeof share === 'number' && isFinite(share) ? Math.max(0, Math.min(1, share)) : 0;
    return Math.round(n * 1000) / 10;
  }

  function srText(letter, label, votes, voters, round) {
    var head = 'Option ' + letter + ', ' + label + ': ';
    if (votes === null || votes === undefined) return head + 'no positions yet.';
    var of = typeof voters === 'number' && voters > 0 ? ' of ' + voters : '';
    var inRound = typeof round === 'number' && round > 0 ? ' in round ' + round : '';
    return head + votes + of + ' advisors prefer this' + inRound + '.';
  }

  /** Pure: one row per option, in option order. */
  function rowsModel(session) {
    var opts = (session && session.options) || [];
    var verdictId = session && session.verdict ? session.verdict.recommendedOptionId : null;
    var voters = session ? session.voters : null;
    var out = [];
    for (var i = 0; i < opts.length; i++) {
      var o = opts[i] || {};
      var hasVotes = typeof o.votes === 'number';
      var share = typeof o.share === 'number' ? o.share : hasVotes && voters > 0 ? o.votes / voters : 0;
      var letter = o.letter || String.fromCharCode(65 + i);
      var label = String(o.label == null ? '' : o.label);
      out.push({
        letter: letter,
        label: label,
        valueText: hasVotes ? String(o.votes) : '–',
        widthPct: hasVotes ? pct(share) : 0,
        recommended: !!o.recommended || (verdictId != null && verdictId === o.id),
        srText: srText(letter, label, hasVotes ? o.votes : null, voters, session ? session.votesRound : null)
      });
    }
    return out;
  }

  /** Pure: badges shown beside the title. */
  function badgesModel(session) {
    var out = [];
    if (!session) return out;
    if (session.sample && !session.demo) out.push({ kind: 'sample', text: 'Sample decision' });
    if (session.verdict) out.push({ kind: 'verdict', text: 'Verdict: ' + (session.verdict.labelText || '') });
    return out;
  }

  // The format caption never hard-codes one round count: light, medium and
  // heavy each say their own, and the empty state names the range.
  var EMPTY_SUB = 'Light, medium or heavy: three advisors and two rounds, up to nine advisors and ten rounds. One verdict.';
  var MODE_SUB = {
    light: 'Light council: three advisors, two rounds, one verdict.',
    medium: 'Medium council: nine advisors, up to four rounds, one verdict.',
    heavy: 'Heavy council: nine advisors, up to ten rounds, one verdict.'
  };

  /** Pure: the one-line format caption for a mode, or null when it adds nothing. */
  function subText(mode) {
    return typeof mode === 'string' && Object.prototype.hasOwnProperty.call(MODE_SUB, mode) ? MODE_SUB[mode] : null;
  }

  ns.decision = { rowsModel: rowsModel, badgesModel: badgesModel, subText: subText };

  if (typeof document === 'undefined') return;

  // ----------------------------------------------------------------- DOM

  var host = document.getElementById('ch-decision');
  if (!host) return;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }
  function setHidden(node, hidden) {
    if (node.hidden !== hidden) node.hidden = hidden;
  }
  function button(cls, text, onClick) {
    var b = el('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  host.classList.add('ch-dec');
  host.setAttribute('aria-labelledby', 'ch-decision-title');

  var titleCol = el('div', 'ch-dec-titlecol');
  var title = el('h1', 'ch-dec-title');
  title.id = 'ch-decision-title';
  var badges = el('div', 'ch-dec-badges');
  var sub = el('p', 'ch-dec-sub');
  var actions = el('div', 'ch-dec-actions');
  actions.appendChild(
    button('ch-btn ch-btn--primary ch-dec-new', 'New question', function () {
      document.dispatchEvent(new CustomEvent('chamber:open-composer', { detail: { opener: title } }));
    })
  );
  actions.appendChild(
    button('ch-btn ch-dec-demo', 'Watch a demo replay', function () {
      if (ns.live && ns.live.startDemo) ns.live.startDemo();
    })
  );
  titleCol.appendChild(title);
  titleCol.appendChild(badges);
  titleCol.appendChild(sub);
  titleCol.appendChild(actions);

  var list = el('ul', 'ch-dec-options');
  list.setAttribute('aria-label', 'Options');
  host.appendChild(titleCol);
  host.appendChild(list);

  var rows = []; // [{li, chip, label, reco, fill, value, sr}]
  var badgeNodes = []; // [{kind, node}]

  function buildRow() {
    var li = el('li', 'ch-dec-row');
    var sr = el('span', 'ch-sr-only');
    var chip = el('span', 'ch-dec-chip');
    var main = el('div', 'ch-dec-main');
    var labelLine = el('div', 'ch-dec-labelline');
    var label = el('span', 'ch-dec-label');
    var reco = el('span', 'ch-dec-reco', 'Recommended');
    var track = el('div', 'ch-dec-track');
    var fill = el('div', 'ch-dec-fill');
    var value = el('span', 'ch-dec-value');
    [chip, main, value].forEach(function (n) {
      n.setAttribute('aria-hidden', 'true');
    });
    labelLine.appendChild(label);
    labelLine.appendChild(reco);
    track.appendChild(fill);
    main.appendChild(labelLine);
    main.appendChild(track);
    li.appendChild(sr);
    li.appendChild(chip);
    li.appendChild(main);
    li.appendChild(value);
    list.appendChild(li);
    return { li: li, sr: sr, chip: chip, label: label, reco: reco, fill: fill, value: value };
  }

  function renderBadges(model) {
    var same = model.length === badgeNodes.length;
    for (var i = 0; same && i < model.length; i++) same = model[i].kind === badgeNodes[i].kind;
    if (!same) {
      while (badges.firstChild) badges.removeChild(badges.firstChild);
      badgeNodes = model.map(function (b) {
        var n = el('span', 'ch-dec-badge ch-dec-badge--' + b.kind);
        badges.appendChild(n);
        return { kind: b.kind, node: n };
      });
    }
    model.forEach(function (b, i) {
      setText(badgeNodes[i].node, b.text);
    });
    setHidden(badges, model.length === 0);
  }

  function render(view) {
    var session = view ? view.session : null;
    var model = rowsModel(session);
    var empty = !session;
    var caption = empty ? EMPTY_SUB : subText(session && session.mode);

    host.classList.toggle('ch-dec--empty', empty);
    setText(title, empty ? 'Ask the council a question' : session.question || 'Council question');
    setText(sub, caption || '');
    setHidden(sub, !caption);
    // Hiding the focused empty-state button would drop focus to <body> (WCAG 2.4.3): park it on the title.
    if (!empty && actions.contains(document.activeElement)) {
      title.tabIndex = -1;
      title.focus();
    }
    setHidden(actions, !empty);
    setHidden(list, model.length === 0);
    renderBadges(badgesModel(session));

    while (rows.length < model.length) rows.push(buildRow());
    while (rows.length > model.length) list.removeChild(rows.pop().li);

    model.forEach(function (m, i) {
      var r = rows[i];
      setText(r.chip, m.letter);
      setText(r.label, m.label);
      setText(r.value, m.valueText);
      setText(r.sr, m.srText + (m.recommended ? ' Recommended.' : ''));
      var w = m.widthPct + '%';
      if (r.fill.style.width !== w) r.fill.style.width = w;
      r.li.classList.toggle('ch-dec-row--reco', m.recommended);
      setHidden(r.reco, !m.recommended);
    });
  }

  if (ns.live && typeof ns.live.subscribe === 'function') ns.live.subscribe(render);
  else render(null);
})(typeof globalThis !== 'undefined' ? globalThis : this);
