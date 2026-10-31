/*
 * Results cue (CTR-144). Dependency-free, same-origin, textContent only.
 *
 * The compact bar that sits under the council room and above the results.
 * It answers one question the page never answered on its own: is there more
 * below, is it ready, or is there none because the sitting stopped.
 *
 * Every word comes from the view the live store publishes. The cue reads
 * session.status (and session.state for the two stopping states) and invents
 * no verdict, no option, no count and no event.
 *
 * States (pure, exported for the unexecuted regression):
 *   no session              -> nothing at all (no bar on the idle page)
 *   preparing, running      -> "Your results will appear below." + arrow
 *   paused                  -> the paused wording, arrow, no link
 *   complete                -> "Your results are ready." + link to the results
 *   blocked, failed         -> "no verdict" wording + link to the room record
 *   cancelled               -> the cancelled wording + link to the room record
 *
 * Two guards on the link: it exists only when its target is really rendered
 * (no dead anchor), and the whole bar steps aside while the results are on
 * screen (one IntersectionObserver; without it the bar simply stays).
 *
 * API: ns.cue = {model, isShown, targetOf}
 */
(function (root) {
  'use strict';
  var ns = (root.councilChamber = root.councilChamber || {});

  // ---------------------------------------------------------------- pure

  var RESULTS_TARGETS = ['ch-advisory', 'ch-options'];
  var RECORD_TARGETS = ['ch-room'];

  function plain(session) {
    var status = session && typeof session.status === 'string' ? session.status : '';
    var state = session && typeof session.state === 'string' ? session.state : '';
    if (!status) return null;
    if (status === 'complete') {
      return {
        kind: 'ready',
        text: 'Your results are ready.',
        linkText: 'Read your results',
        targets: RESULTS_TARGETS,
        arrow: false
      };
    }
    if (status === 'blocked') {
      return {
        kind: 'blocked',
        text: 'The council is blocked, so there is no verdict to show.',
        linkText: 'Read what happened',
        targets: RECORD_TARGETS,
        arrow: false
      };
    }
    if (status === 'failed') {
      return {
        kind: 'failed',
        text: 'The council stopped before a verdict.',
        linkText: 'Read what happened',
        targets: RECORD_TARGETS,
        arrow: false
      };
    }
    if (status === 'cancelled') {
      return {
        kind: 'cancelled',
        text: state === 'CANCEL_REQUESTED'
          ? 'The council is stopping. No verdict will be produced.'
          : 'The council was cancelled. No verdict was produced.',
        linkText: 'Read the record',
        targets: RECORD_TARGETS,
        arrow: false
      };
    }
    if (status === 'paused') {
      return {
        kind: 'paused',
        text: state === 'PAUSE_REQUESTED'
          ? 'The council is pausing. Your results will appear below when it finishes.'
          : 'The council is paused. Your results will appear below when it resumes.',
        linkText: null,
        targets: [],
        arrow: true
      };
    }
    // preparing and running: the council is working, results are still to come.
    return {
      kind: 'active',
      text: 'Your results will appear below.',
      linkText: null,
      targets: [],
      arrow: true
    };
  }

  /** True only when the node is on the page and actually rendered. */
  function isShown(node) {
    if (!node || node.hidden) return false;
    if (typeof node.getClientRects === 'function') {
      var rects = node.getClientRects();
      if (rects && rects.length > 0) return true;
    }
    return node.offsetParent != null;
  }

  /** The first target in the list that is rendered, or null. */
  function targetOf(list, doc) {
    var d = doc || (typeof document !== 'undefined' ? document : null);
    if (!d || !list) return null;
    for (var i = 0; i < list.length; i += 1) {
      var node = d.getElementById(list[i]);
      if (isShown(node)) return node;
    }
    return null;
  }

  ns.cue = { model: plain, isShown: isShown, targetOf: targetOf };

  if (typeof document === 'undefined') return;

  // ----------------------------------------------------------------- DOM

  var els = {
    root: document.getElementById('ch-results-cue'),
    text: document.getElementById('ch-cue-text'),
    link: document.getElementById('ch-cue-link'),
    arrow: document.getElementById('ch-cue-arrow')
  };
  if (!els.root || !els.text || !els.link || !els.arrow) return;

  var observer = typeof root.IntersectionObserver === 'function'
    ? new root.IntersectionObserver(onIntersect, { threshold: 0 })
    : null;
  var watched = null;
  var lastText = null;
  var lastLink = null;

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }

  function setHidden(node, hidden) {
    if (node.hidden !== hidden) node.hidden = hidden;
  }

  function showCue(show) { setHidden(els.root, !show); }

  // Only the target we are currently watching may move the bar; a late
  // callback from a previous session or a previous target is ignored.
  function onIntersect(entries) {
    for (var i = 0; i < entries.length; i += 1) {
      if (entries[i].target !== watched) continue;
      // Results on screen: the bar has nothing left to point at.
      showCue(!entries[i].isIntersecting);
    }
  }

  // Re-observing the same target on every tick would overrule the observer and
  // make the bar reappear once a second, so an unchanged target is left alone.
  function watch(target) {
    if (target === watched && target !== null) return;
    if (watched && observer) observer.unobserve(watched);
    watched = target;
    if (!target || !observer) {
      showCue(true); // no observer support (or nothing to watch): never hide
      return;
    }
    showCue(true); // a newly available result starts visible until measured
    observer.observe(target);
  }

  function render(view) {
    var model = plain(view && view.session ? view.session : null);
    if (!model) {
      setHidden(els.link, true);
      setHidden(els.arrow, true);
      watch(null);
      showCue(false);
      return;
    }

    var target = model.targets.length ? targetOf(model.targets) : null;

    if (lastText !== model.text) {
      lastText = model.text;
      setText(els.text, model.text);
    }
    setHidden(els.arrow, !model.arrow);

    // The link appears only when it has somewhere real to go.
    if (model.linkText && target) {
      var href = '#' + target.id;
      var label = model.linkText;
      if (lastLink !== href + '|' + label) {
        lastLink = href + '|' + label;
        els.link.setAttribute('href', href);
        setText(els.link, label);
      }
      setHidden(els.link, false);
    } else {
      lastLink = null;
      setHidden(els.link, true);
    }

    // While a ready result is already being watched, the observer owns the
    // bar's visibility; only a new target starts visible again.
    if (model.kind === 'ready' && target && target !== watched) showCue(true);
    watch(model.kind === 'ready' ? target : null);
  }

  function init() {
    render(ns.live && typeof ns.live.getView === 'function' ? ns.live.getView() : null);
    if (ns.live && typeof ns.live.subscribe === 'function') ns.live.subscribe(render);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(typeof globalThis !== 'undefined' ? globalThis : this);
