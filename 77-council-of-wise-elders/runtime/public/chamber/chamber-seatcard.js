/*
 * Council chamber seat card (W29-E). Dependency-free, same-origin only.
 *
 * Owns the contents and behaviour of dialog#ch-seatcard. Listens for the
 * document event chamber:open-seat {seatId, opener}, fills the card from
 * ns.seats.get(seatId) and the matching view.session.seats[] entry, then
 * showModal(). While open it stays subscribed to ns.live and re-renders the
 * status line when the view changes. All DOM text is set with textContent.
 */
(function (root) {
  'use strict';
  var ns = (root.councilChamber = root.councilChamber || {});

  // ---------------------------------------------------------------- pure

  var RATIFICATION = {
    support: 'Supports',
    conditional_support: 'Supports with conditions',
    oppose: 'Opposes',
    abstain: 'Abstains'
  };

  function optionLabel(card, options) {
    var list = Array.isArray(options) ? options : [];
    for (var i = 0; i < list.length; i += 1) {
      var o = list[i];
      if (!o) continue;
      if (card.preferredOptionId && o.id === card.preferredOptionId) return o.label || '';
      if (!card.preferredOptionId && card.preferredLetter && o.letter === card.preferredLetter) {
        return o.label || '';
      }
    }
    return '';
  }

  /** {lead, quote|null} for the status area of the seat card. */
  function statusLine(seatView, options) {
    var card = seatView && seatView.latest ? seatView.latest : null;
    if (!card) return { lead: 'This seat has not spoken yet.', quote: null };
    var lead;
    var quote = card.line ? String(card.line) : null;
    if (card.pending) {
      lead = 'Round ' + card.round + ' position is in. Loading its line…';
      quote = null;
    } else if (card.kind === 'ratification') {
      var stance = Object.prototype.hasOwnProperty.call(RATIFICATION, card.resolutionStance)
        ? RATIFICATION[card.resolutionStance]
        : 'Abstains';
      lead = 'Round 3 vote: ' + stance + ' the draft resolution';
    } else if (card.kind === 'consult') {
      lead = 'Consult answer';
    } else {
      var label = optionLabel(card, options);
      lead =
        'Round ' + card.round + ':' +
        (card.stanceText ? ' ' + card.stanceText : '') +
        (card.preferredLetter ? ' ' + card.preferredLetter : '') +
        (label ? ', ' + label : '');
    }
    if (seatView.status === 'writing') {
      lead += ' Writing its round ' + (Number(card.round) + 1) + ' position now.';
    }
    return { lead: lead, quote: quote };
  }

  ns.seatcard = { statusLine: statusLine };

  if (typeof document === 'undefined') return;

  // ----------------------------------------------------------------- DOM

  var dialog = document.getElementById('ch-seatcard');
  if (!dialog) return;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  var body = el('div', 'ch-card-body');
  var head = el('div', 'ch-card-head');
  var portrait = el('div', 'ch-card-portrait');
  var img = el('img', 'ch-card-img');
  img.alt = '';
  img.width = 72;
  img.height = 72;
  portrait.appendChild(img);
  var text = el('div', 'ch-card-text');
  var domainEl = el('p', 'ch-eyebrow ch-card-domain');
  var nameEl = el('h2', 'ch-card-name');
  nameEl.id = 'ch-card-name';
  var ownsEl = el('p', 'ch-card-owns');
  ownsEl.id = 'ch-card-owns';
  text.appendChild(domainEl);
  text.appendChild(nameEl);
  text.appendChild(ownsEl);
  head.appendChild(portrait);
  head.appendChild(text);

  var status = el('div', 'ch-card-status');
  status.setAttribute('aria-live', 'polite');
  var leadEl = el('p', 'ch-card-lead');
  var quoteEl = el('p', 'ch-card-quote');
  status.appendChild(leadEl);
  status.appendChild(quoteEl);
  var disclaimerEl = el('p', 'ch-card-disclaimer');
  var actions = el('div', 'ch-card-actions');
  var closeBtn = el('button', 'ch-btn ch-card-close', 'Close');
  closeBtn.type = 'button';
  actions.appendChild(closeBtn);

  body.appendChild(head);
  body.appendChild(status);
  body.appendChild(disclaimerEl);
  body.appendChild(actions);
  dialog.textContent = '';
  dialog.appendChild(body);
  dialog.classList.add('ch-dialog', 'ch-card');
  dialog.setAttribute('aria-labelledby', 'ch-card-name');
  dialog.setAttribute('aria-describedby', 'ch-card-owns');

  var seatId = null;
  var opener = null;
  var unsubscribe = null;
  var portraitTries = [];

  function seatData(id) {
    var s = ns.seats && ns.seats.get ? ns.seats.get(id) : null;
    return s || { id: id, name: id, domain: '', owns: '', sources: [], disclaimer: '' };
  }

  function loadPortrait(id) {
    portraitTries = ns.seats && ns.seats.portraitSources ? ns.seats.portraitSources(id).slice() : [];
    var next = portraitTries.shift();
    if (next) img.src = next;
    else img.removeAttribute('src');
  }
  img.addEventListener('error', function () {
    var next = portraitTries.shift();
    if (next) img.src = next;
  });

  function seatView(view) {
    var seats = view && view.session && view.session.seats ? view.session.seats : [];
    for (var i = 0; i < seats.length; i += 1) if (seats[i].id === seatId) return seats[i];
    return null;
  }

  function renderStatus(view) {
    var options = view && view.session ? view.session.options : [];
    var sv = seatView(view);
    var s = statusLine(sv, options);
    setText(leadEl, s.lead);
    setText(quoteEl, s.quote ? '“' + s.quote + '”' : '');
    quoteEl.hidden = !s.quote;
  }

  function renderStatic(id) {
    var seat = seatData(id);
    setText(domainEl, seat.domain || '');
    domainEl.hidden = !seat.domain;
    setText(nameEl, seat.name || id);
    setText(ownsEl, seat.owns ? 'Owns the question: ' + seat.owns : '');
    ownsEl.hidden = !seat.owns;
    setText(
      disclaimerEl,
      seat.disclaimer || 'A simulated advisor built from ' + (seat.name || id) + "'s public work. Not the person."
    );
    loadPortrait(id);
  }

  function open(detail) {
    if (!detail || !detail.seatId) return;
    seatId = String(detail.seatId);
    opener = detail.opener || document.activeElement || null;
    renderStatic(seatId);
    renderStatus(ns.live && ns.live.getView ? ns.live.getView() : null);
    if (!dialog.open) dialog.showModal();
    if (!unsubscribe && ns.live && ns.live.subscribe) {
      unsubscribe = ns.live.subscribe(renderStatus);
    }
  }

  function restoreFocus() {
    var target = opener;
    opener = null;
    if (target && !target.isConnected && seatId) {
      // The room re-rendered while the card was open: find the same seat again.
      var name = seatData(seatId).name;
      var buttons = document.querySelectorAll('button[aria-haspopup="dialog"]');
      target = null;
      for (var i = 0; i < buttons.length; i += 1) {
        if ((buttons[i].getAttribute('aria-label') || '').indexOf(name + ',') === 0) target = buttons[i];
      }
    }
    if (target && target.focus) target.focus();
  }

  dialog.addEventListener('close', function () {
    if (unsubscribe) {
      unsubscribe();
      unsubscribe = null;
    }
    restoreFocus();
  });
  closeBtn.addEventListener('click', function () {
    dialog.close();
  });
  dialog.addEventListener('click', function (event) {
    if (event.target !== dialog) return;
    // Padding clicks also target the dialog; only a click outside its box is the backdrop.
    var r = dialog.getBoundingClientRect();
    var outside =
      event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom;
    if (outside) dialog.close();
  });
  document.addEventListener('chamber:open-seat', function (event) {
    open(event.detail);
  });
})(typeof globalThis !== 'undefined' ? globalThis : this);
