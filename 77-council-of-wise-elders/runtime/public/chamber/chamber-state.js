/*
 * Council chamber state engine. Pure and dependency-free: no DOM, no fetch,
 * no timers. Every clock value comes from the nowMs argument.
 *
 * It folds the REAL committed council events (GET /api/council/sessions/<id>/events)
 * plus the session read (GET /council/<id>, which carries cards and verdict)
 * into the SessionView the chamber renders. Nothing here invents an event,
 * a seat, a stance or a line: a field that no frame or record supplied stays
 * absent (null, '–' in the UI, or a pending card).
 *
 * Two frame shapes are handled:
 *  - service path (repository writes): to_state is set at the top level and
 *    payload.state_record carries the state; operation_reserved and
 *    operation_completed carry only a hashed operation_id (ignored);
 *    card_accepted carries only {operation_id, seat_id, round, card_hash}.
 *  - CLI path (engine writes): session_state_changed carries payload.from and
 *    payload.to; crux_identified and resolution_drafted carry chair fields.
 * card_accepted never carries the card text, so a card is "pending" until
 * applyRecord supplies its content from the session read.
 *
 * API: ns.state = {create, apply, applyRecord, view, stepOf}.
 */
(function (root) {
  'use strict';
  var ns = root.councilChamber = root.councilChamber || {};

  var TOTAL_ROUNDS = 3;
  var SPOTLIGHT_MS = 6000;
  var PLAYBACK_MS = 7000;
  var DEFAULT_SEATS = ['simon-sinek', 'td-jakes', 'oprah-winfrey', 'tiffany-aliche', 'russell-brunson',
    'michelle-obama', 'brene-brown', 'dennis-kimbro', 'les-brown'];
  var STEPS = [['brief', 'Brief'], ['openings', 'Openings'], ['fault_lines', 'Fault lines'],
    ['debate', 'Debate'], ['vote', 'Vote'], ['verdict', 'Verdict']];
  var STEP_INDEX = {
    DRAFT: 0, READY: 0, QUEUED: 0, PREPARING: 0,
    ROUND_1: 1, CONSULTING: 1,
    CRUX_REVIEW: 2,
    ROUND_2: 3,
    DRAFT_RESOLUTION: 4, ROUND_3: 4,
    VERIFYING: 5, COMPLETED: 5
  };
  var ROUND_OF = { ROUND_1: 1, ROUND_2: 2, ROUND_3: 3 };
  // The round a state belongs to (rounds in or behind us); control states keep the last one.
  var CONTEXT_ROUND = { CRUX_REVIEW: 1, DRAFT_RESOLUTION: 2, CONSULTING: 1 };
  var TERMINAL = { COMPLETED: true, CANCELLED: true, FAILED: true };
  var PREP = { DRAFT: true, READY: true, QUEUED: true, PREPARING: true };
  var CHAIR = {
    DRAFT: 'the question as it was asked', READY: null, QUEUED: null, PREPARING: null,
    CRUX_REVIEW: 'which disagreements would change the decision',
    DRAFT_RESOLUTION: 'which option to put to the advisors for ratification',
    CONSULTING: 'which sources back the answer',
    VERIFYING: 'whether the verdict can be validated'
  };
  // state -> [key point label, headline, explainer]; round states take the route explainer.
  var COPY = {
    DRAFT: ['CHAIR: READING YOUR QUESTION', 'The chair is reading your question.', 'The advisors start once the chair has framed the decision.'],
    ROUND_1: ['ROUND 1: OPENING POSITIONS', 'The advisors are writing their opening positions.', null],
    CRUX_REVIEW: ['CHAIR: FINDING THE FAULT LINES', 'The chair is finding the fault lines.', 'Round 1 is in. The chair looks for the points that would change the decision.'],
    ROUND_2: ['ROUND 2: DEBATE', 'The advisors are debating the fault lines.', null],
    DRAFT_RESOLUTION: ['CHAIR: DRAFTING THE RESOLUTION', 'The chair is drafting the resolution.', 'Round 2 is in. The chair writes the one resolution the advisors will ratify.'],
    ROUND_3: ['ROUND 3: THE VOTE', 'The advisors are voting on the resolution.', null],
    CONSULTING: ['CHAIR: CONSULTING SOURCES', 'The chair is consulting sources.', 'The chair checks the sources behind the answer.'],
    VERIFYING: ['CHAIR: CHECKING THE VERDICT', 'The chair is checking the verdict.', 'Nothing is final until the verdict has been validated.'],
    COMPLETED: [null, 'The council has reached its verdict.', 'The verdict has been validated.'],
    PAUSE_REQUESTED: ['PAUSE REQUESTED', 'A pause was requested.', 'The council stops at the next safe point.'],
    PAUSED: ['PAUSED', 'The council is paused.', 'It resumes from where it stopped.'],
    RESUMING: ['RESUMING', 'The council is resuming.', 'It picks up from where it stopped.'],
    CANCEL_REQUESTED: ['CANCEL REQUESTED', 'A cancel was requested.', 'The council stops at the next safe point.'],
    CANCELLED: ['CANCELLED', 'The council was cancelled.', 'No verdict will be produced for this session.'],
    BLOCKED: ['BLOCKED', 'The council is blocked.', 'It cannot continue until the blocker is cleared.'],
    FAILED: ['FAILED', 'The council failed.', 'No verdict was produced for this session.']
  };
  COPY.READY = COPY.QUEUED = COPY.PREPARING = COPY.DRAFT;
  var STATUS_OF = {
    PAUSE_REQUESTED: 'paused', PAUSED: 'paused', CANCEL_REQUESTED: 'cancelled', CANCELLED: 'cancelled',
    BLOCKED: 'blocked', FAILED: 'failed', COMPLETED: 'complete'
  };
  var VERDICT_TEXT = {
    GO: 'Go', GO_WITH_CONDITIONS: 'Go, with conditions', RESHAPE: 'Reshape', DONT_DO_IT: "Don't do it",
    WAIT: 'Wait', INSUFFICIENT_EVIDENCE: 'Not enough evidence'
  };
  var STANCE_TEXT = { support: 'Supports', conditional: 'Supports with conditions', conditional_support: 'Supports with conditions', oppose: 'Opposes', abstain: 'Abstains' };

  function text(v) { return typeof v === 'string' && v.trim() ? v.trim() : null; }
  function obj(v) { return v && typeof v === 'object' ? v : {}; }
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }

  /** The state a frame moves the session into, whichever writer produced it. */
  function stateOf(frame) {
    var p = obj(frame.payload);
    var rec = obj(p.state_record).state;
    return text(frame.to_state) || text(p.to_state) || text(p.to) || text(rec);
  }

  function stepOf(state) {
    return has(STEP_INDEX, state) ? STEPS[STEP_INDEX[state]][0] : null;
  }

  function contextRound(state, consult) {
    if (has(ROUND_OF, state)) return ROUND_OF[state];
    if (has(CONTEXT_ROUND, state)) return CONTEXT_ROUND[state];
    if (state === 'VERIFYING' || state === 'COMPLETED') return consult ? 1 : TOTAL_ROUNDS;
    return null;
  }

  function newSeat() { return { accepted: {}, cards: {} }; }

  function addSeat(m, id) {
    if (!has(m.seats, id)) { m.seats[id] = newSeat(); m.seatIds.push(id); }
    return m.seats[id];
  }

  function emptyModel() {
    return {
      sessionId: null, question: null, mode: null, options: [], route: { routeId: null, model: null },
      seatIds: [], seats: {}, sample: false, demo: false,
      state: null, since: NaN, startAt: NaN, endedAt: null, step: 0, round: 0, consult: false, reason: null,
      roundNoted: {}, roundDoneAt: {},
      cruxes: [], draft: null, verdict: null, keyPoints: [], maxSeq: 0, frames: 0
    };
  }

  function seen(m, ms) {
    if (isFinite(ms) && (!isFinite(m.startAt) || ms < m.startAt)) m.startAt = ms;
  }

  function setState(m, state, ms) {
    m.state = state;
    seen(m, ms);
    if (isFinite(ms)) m.since = ms;
    m.endedAt = TERMINAL[state] && isFinite(ms) ? ms : null;
    if (has(STEP_INDEX, state)) m.step = STEP_INDEX[state];
    if (state === 'CONSULTING') m.consult = true;
    var r = contextRound(state, m.consult);
    if (r !== null) m.round = r;
  }

  /** Start a model from the session read, and fold in whatever cards and verdict it carries. */
  function create(record) {
    var m = emptyModel();
    applyRecord(m, record);
    return m;
  }

  /**
   * Fold a session read (or part of one) into the model. Safe to repeat and to
   * call with a partial record such as {cards:[one]} or {verdict}. The state is
   * taken from the record only until the first frame arrives: frames own it after.
   */
  function applyRecord(m, record) {
    var rec = obj(record);
    var brief = obj(rec.brief);
    var spec = obj(rec.spec);
    if (text(rec.session_id)) m.sessionId = rec.session_id;
    if (text(brief.question)) m.question = text(brief.question);
    if (Array.isArray(brief.options)) {
      m.options = brief.options.filter(function (o) { return o && typeof o.id === 'string'; }).map(function (o, i) {
        return { id: o.id, letter: String.fromCharCode(65 + i), label: text(o.label) || text(o.title) || text(o.name) || o.id, kind: text(o.kind) };
      });
    }
    seen(m, Date.parse(spec.created_at));
    if (text(spec.mode)) { m.mode = spec.mode; if (spec.mode === 'consult') m.consult = true; }
    if (spec.model_policy && typeof spec.model_policy === 'object') {
      m.route = { routeId: text(spec.model_policy.route_id), model: text(spec.model_policy.requested_model_id) };
    }
    if (Array.isArray(spec.seat_ids) && spec.seat_ids.length) spec.seat_ids.forEach(function (id) { addSeat(m, id); });
    if (m.seatIds.length === 0) DEFAULT_SEATS.forEach(function (id) { addSeat(m, id); });
    if (rec.sample === true) m.sample = true;
    if (rec.demo === true) m.demo = true;
    var snap = obj(rec.state);
    if (m.frames === 0 && text(snap.state)) {
      setState(m, snap.state, Date.parse(snap.updated_at));
      if (!has(STEP_INDEX, snap.state) && text(snap.resume_phase) && has(STEP_INDEX, snap.resume_phase)) {
        m.step = STEP_INDEX[snap.resume_phase];
        var rr = contextRound(snap.resume_phase, m.consult);
        if (rr !== null) m.round = rr;
      }
    }
    if (Array.isArray(rec.cards)) {
      rec.cards.forEach(function (card) {
        if (!card || typeof card.seat_id !== 'string') return;
        var round = card.card_kind === 'consult' ? 1 : Number(card.round);
        if (!isFinite(round) || round < 1) return;
        addSeat(m, card.seat_id).cards[round] = card;
      });
    }
    if (rec.verdict && typeof rec.verdict === 'object') m.verdict = rec.verdict;
    return m;
  }

  function point(m, label, detail, at) {
    var last = m.keyPoints[m.keyPoints.length - 1];
    if (last && last.label === label) {
      if (!last.detail && detail) last.detail = detail;
      return;
    }
    m.keyPoints.push({ label: label, detail: detail || null, at: at || null });
  }

  function optionText(m, id) {
    for (var i = 0; i < m.options.length; i++) {
      if (m.options[i].id === id) return 'Option ' + m.options[i].letter + ': ' + m.options[i].label;
    }
    return id ? 'Option ' + id : null;
  }

  function allAccepted(m, round) {
    return m.seatIds.length > 0 && m.seatIds.every(function (id) { return m.seats[id].accepted[round] === true; });
  }

  /** Apply one committed frame. Returns false for a duplicate, older or malformed frame. */
  function apply(m, frame) {
    if (!frame || typeof frame.sequence !== 'number' || frame.sequence <= m.maxSeq) return false;
    if (m.frames === 0 && frame.sequence === 1) {
      // The journal replays from the start, so the frames re-derive the phase and its history.
      m.state = null; m.keyPoints = []; m.step = 0; m.round = 0; m.since = NaN; m.endedAt = null;
    }
    m.maxSeq = frame.sequence;
    m.frames += 1;
    var p = obj(frame.payload);
    var ms = Date.parse(frame.created_at);
    var at = text(frame.created_at);

    if (frame.type === 'session_blocked' || frame.type === 'session_failed') {
      m.reason = text(p.reason) || text(p.code) || m.reason;
    }
    var to = stateOf(frame);
    if (to && to !== m.state) {
      setState(m, to, ms);
      var cp = COPY[to];
      if (cp && cp[0]) point(m, cp[0], null, at);
    }
    var tail = m.keyPoints[m.keyPoints.length - 1];
    // The engine writes the state change first and the reason in the next event.
    if (m.reason && tail && (tail.label === 'BLOCKED' || tail.label === 'FAILED') && !tail.detail) tail.detail = m.reason;

    // operation_reserved / operation_completed carry only a hashed operation_id on the service
    // path (no seat), so they say nothing about who is writing and are ignored.
    if (frame.type === 'card_accepted' && typeof p.seat_id === 'string') {
      var n = Number(p.round);
      var r = isFinite(n) && n >= 1 ? n : (m.round || 1);
      var seat = addSeat(m, p.seat_id);
      seat.accepted[r] = true;
      if (!m.consult && r <= TOTAL_ROUNDS && !m.roundNoted[r] && allAccepted(m, r)) {
        m.roundNoted[r] = true;
        m.roundDoneAt[r] = isFinite(ms) ? ms : m.since;
        point(m, 'ROUND ' + r + ': ALL ' + m.seatIds.length + ' POSITIONS IN', null, at);
      }
    } else if (frame.type === 'crux_identified') {
      m.cruxes.push(text(p.needed_evidence) || (Array.isArray(p.competing_claims) ? text(p.competing_claims[0]) : null) || text(p.type));
      var found = m.cruxes.filter(Boolean);
      var crux = found.length ? found[0] + (found.length > 1 ? ' (+' + (found.length - 1) + ' more)' : '') : null;
      var cr = m.keyPoints.filter(function (k) { return k.label === COPY.CRUX_REVIEW[0]; })[0];
      if (cr && crux) cr.detail = crux;
    } else if (frame.type === 'resolution_drafted') {
      m.draft = text(p.recommended_option_id);
      var dr = m.keyPoints.filter(function (k) { return k.label === COPY.DRAFT_RESOLUTION[0]; })[0];
      if (dr && m.draft) dr.detail = 'Recommended: ' + optionText(m, m.draft);
    }
    return true;
  }

  // ------------------------------------------------------------------ view

  function clock(ms) {
    if (!isFinite(ms) || ms < 0) ms = 0;
    var s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  function letterOf(m, id) {
    for (var i = 0; i < m.options.length; i++) if (m.options[i].id === id) return m.options[i].letter;
    return null;
  }

  function firstText(list) {
    if (!Array.isArray(list)) return null;
    for (var i = 0; i < list.length; i++) if (text(list[i])) return text(list[i]);
    return null;
  }

  function cardView(m, round, card, accepted) {
    if (!card) {
      return { round: round, kind: round === 3 && !m.consult ? 'ratification' : m.consult ? 'consult' : 'advisor', stance: null, stanceText: null,
        preferredOptionId: null, preferredLetter: null, line: null, resolutionStance: null, pending: accepted === true };
    }
    var kind = card.card_kind === 'ratification' ? 'ratification' : card.card_kind === 'consult' ? 'consult' : 'advisor';
    var line = null;
    if (kind === 'advisor') line = firstText(card.decisive_arguments);
    else if (kind === 'ratification') {
      line = firstText(card.unresolved_objections);
      if (!line && Array.isArray(card.amendments) && card.amendments[0]) line = text(card.amendments[0].statement);
    } else line = text(card.answer);
    var pref = text(card.preferred_option_id);
    return {
      round: round, kind: kind,
      stance: text(card.stance), stanceText: has(STANCE_TEXT, card.stance) ? STANCE_TEXT[card.stance] : null,
      preferredOptionId: pref, preferredLetter: pref ? letterOf(m, pref) : null,
      line: line, resolutionStance: text(card.resolution_stance), pending: false
    };
  }

  function seatCards(m, id) {
    var s = m.seats[id];
    var out = {};
    [1, 2, 3].forEach(function (r) {
      if (s.cards[r]) out[r] = cardView(m, r, s.cards[r], true);
      else if (s.accepted[r]) out[r] = cardView(m, r, null, true);
    });
    return out;
  }

  function steps(m) {
    var cur = m.state === 'COMPLETED' ? STEPS.length : m.step;
    return STEPS.map(function (s, i) {
      var status = i < cur ? 'done' : i === cur ? 'current' : 'todo';
      if (m.consult && i >= 2 && i <= 4) status = 'skipped';
      return { key: s[0], label: s[1], status: status };
    });
  }

  function verdictView(m) {
    var v = m.verdict;
    if (!v) return null;
    if (v.result_kind === 'consult') {
      return { label: null, labelText: 'Consult answer', recommendedOptionId: null, reasons: [], kind: 'consult' };
    }
    var label = text(v.label);
    return {
      label: label, labelText: label && has(VERDICT_TEXT, label) ? VERDICT_TEXT[label] : (label || 'Verdict'),
      recommendedOptionId: text(v.recommended_option_id),
      reasons: Array.isArray(v.main_reasons) ? v.main_reasons.slice() : [],
      kind: text(v.result_kind) || 'scored'
    };
  }

  function roundLabel(m) {
    var s = m.state;
    if (!s || PREP[s]) return 'GETTING READY';
    if (has(ROUND_OF, s)) return 'ROUND ' + ROUND_OF[s] + ' OF ' + TOTAL_ROUNDS;
    if (s === 'CRUX_REVIEW') return 'AFTER ROUND 1 OF ' + TOTAL_ROUNDS;
    if (s === 'DRAFT_RESOLUTION') return 'AFTER ROUND 2 OF ' + TOTAL_ROUNDS;
    if (s === 'VERIFYING') return 'FINAL CHECKS';
    if (s === 'COMPLETED') return 'VERDICT';
    if (s === 'CONSULTING') return 'CONSULT';
    return s.replace(/_/g, ' ');
  }

  function explainer(m) {
    var route = m.route.routeId ? ' on ' + m.route.routeId + (m.route.model ? ' (' + m.route.model + ')' : '') : '';
    return 'Each advisor writes an independent position' + route + '. Their lines play here as soon as the round is in.';
  }

  /** The render-ready SessionView at wall-clock time nowMs. */
  function view(m, nowMs) {
    var state = m.state;
    var inRound = has(ROUND_OF, state) ? ROUND_OF[state] : state === 'CONSULTING' ? 1 : 0;
    var ctx = inRound || (state && !PREP[state] ? m.round : 0);
    var copy = (state && COPY[state]) || COPY.DRAFT;
    var elapsed = Math.max(0, nowMs - (isFinite(m.since) ? m.since : nowMs));

    var done = 0;
    var writers = [];
    var rows = m.seatIds.map(function (id) {
      var s = m.seats[id];
      var status = 'idle';
      if (ctx && (s.accepted[ctx] || s.cards[ctx])) { status = 'done'; done += 1; }
      else if (inRound) { status = 'writing'; writers.push(id); }
      return { id: id, status: status, spotlight: false, bubble: { kind: 'none', text: '' }, latest: null, cards: seatCards(m, id) };
    });
    var total = m.seatIds.length;
    var complete = inRound > 0 && total > 0 && done === total;

    // Lines play back once a round is in and through the chair phase that follows it.
    var playRound = complete ? inRound : state === 'CRUX_REVIEW' ? 1 : state === 'DRAFT_RESOLUTION' ? 2 : state === 'VERIFYING' ? contextRound(state, m.consult) : 0;
    var playable = [];
    if (playRound) {
      rows.forEach(function (row) {
        var c = row.cards[playRound];
        if (c && c.line) playable.push({ id: row.id, line: c.line });
      });
    }

    var weighing = null;
    var spot = null;
    if (playable.length) {
      var start = m.roundDoneAt[playRound];
      if (!isFinite(start)) start = isFinite(m.since) ? m.since : nowMs;
      var pick = playable[Math.floor(Math.max(0, nowMs - start) / PLAYBACK_MS) % playable.length];
      spot = pick.id;
      weighing = { seatId: pick.id, kind: 'said', text: pick.line };
    } else if (writers.length) {
      var lead = writers[Math.floor(elapsed / SPOTLIGHT_MS) % writers.length];
      spot = lead;
      weighing = { seatId: lead, kind: 'weighing', text: '' };
    } else if (state && has(CHAIR, state) && !has(ROUND_OF, state)) {
      weighing = { seatId: null, kind: 'chair', text: state === 'DRAFT' || PREP[state] ? (m.question || CHAIR.DRAFT) : CHAIR[state] };
    }

    rows.forEach(function (row) {
      var rounds = Object.keys(row.cards).map(Number).sort();
      row.latest = rounds.length ? row.cards[rounds[rounds.length - 1]] : null;
      row.spotlight = row.id === spot;
      if (row.status === 'writing') row.bubble = { kind: 'typing', text: '' };
      else if (row.status === 'done') {
        var line = row.spotlight && weighing && weighing.kind === 'said' ? weighing.text : null;
        row.bubble = line ? { kind: 'line', text: line } : { kind: 'done', text: '' };
      }
    });

    // Tallies come from the highest round with any card content.
    var votesRound = 0;
    m.seatIds.forEach(function (id) {
      [1, 2, 3].forEach(function (r) { if (m.seats[id].cards[r] && r > votesRound) votesRound = r; });
    });
    var voters = 0;
    var counts = {};
    if (votesRound) {
      m.seatIds.forEach(function (id) {
        var c = m.seats[id].cards[votesRound];
        if (!c) return;
        voters += 1;
        var pref = text(c.preferred_option_id);
        if (pref) counts[pref] = (counts[pref] || 0) + 1;
      });
    }
    var verdict = verdictView(m);
    var scores = {};
    if (m.verdict && Array.isArray(m.verdict.option_scores)) {
      m.verdict.option_scores.forEach(function (s) { if (s && typeof s.display_score === 'number') scores[s.option_id] = s.display_score; });
    }
    var options = m.options.map(function (o) {
      var votes = votesRound ? (counts[o.id] || 0) : null;
      return {
        id: o.id, letter: o.letter, label: o.label, kind: o.kind, votes: votes,
        share: votes !== null && total ? votes / total : 0,
        recommended: !!(verdict && verdict.recommendedOptionId === o.id),
        score: has(scores, o.id) ? scores[o.id] : null
      };
    });

    var keyPoints = m.keyPoints.map(function (k) { return { label: k.label, detail: k.detail, at: k.at }; });
    if (state === 'COMPLETED' && verdict) {
      var rec = verdict.recommendedOptionId ? optionText(m, verdict.recommendedOptionId) : null;
      keyPoints.push({ label: 'VERDICT: ' + verdict.labelText.toUpperCase(), detail: rec, at: null });
    }

    var status = state && has(STATUS_OF, state) ? STATUS_OF[state] : !state || PREP[state] ? 'preparing' : 'running';
    var statusText = { preparing: 'Getting ready.', running: 'In progress.', paused: state === 'PAUSE_REQUESTED' ? 'Pause requested.' : 'Paused.',
      blocked: m.reason || 'Blocked.', cancelled: state === 'CANCEL_REQUESTED' ? 'Cancel requested.' : 'Cancelled.',
      failed: m.reason || 'Failed.', complete: 'Verdict reached.' }[status];

    var headline = copy[1];
    var explain = copy[2] || explainer(m);
    if (state === 'COMPLETED' && verdict) {
      var named = verdict.recommendedOptionId ? optionText(m, verdict.recommendedOptionId) : null;
      explain = 'Verdict: ' + verdict.labelText + (named ? '. Recommended: ' + named + '.' : '.');
    }
    if ((state === 'BLOCKED' || state === 'FAILED') && m.reason) explain = m.reason;

    var inWork = inRound > 0;
    var progress;
    if (state === 'COMPLETED') progress = { indeterminate: false, value: 1 };
    else if (inWork && done > 0) progress = { indeterminate: false, value: total ? done / total : 0 };
    else progress = { indeterminate: true, value: 0 };
    var progressText = inWork ? done + ' of ' + total + ' advisors in' : state === 'COMPLETED' ? 'Verdict reached' : 'The chair is working';

    var end = m.endedAt !== null ? m.endedAt : nowMs;
    return {
      id: m.sessionId, demo: m.demo, sample: m.sample, mode: m.mode, question: m.question,
      route: { routeId: m.route.routeId, model: m.route.model },
      state: state, status: status, statusText: statusText,
      steps: steps(m), options: options, votesRound: votesRound || null, voters: voters, verdict: verdict,
      round: {
        label: roundLabel(m), number: inRound || null, total: TOTAL_ROUNDS, headline: headline, explain: explain,
        // Running: time in this state. Finished: how long the whole session took (frozen).
        timer: clock(end - (m.endedAt !== null && isFinite(m.startAt) ? m.startAt : isFinite(m.since) ? m.since : end)), progress: progress, progressText: progressText,
        weighing: weighing, complete: complete
      },
      seats: rows, keyPoints: keyPoints
    };
  }

  ns.state = { create: create, apply: apply, applyRecord: applyRecord, view: view, stepOf: stepOf };
})(typeof globalThis !== 'undefined' ? globalThis : this);
