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
 * API: ns.state = {create, apply, applyRecord, view, stepOf, routeLabel}.
 */
(function (root) {
  'use strict';
  var ns = root.councilChamber = root.councilChamber || {};

  var TOTAL_ROUNDS = 3;
  // One display denominator per council size. The four older modes keep 3.
  var MODE_ROUNDS = { light: 2, medium: 4, heavy: 10 };
  function totalRounds(mode) {
    return has(MODE_ROUNDS, mode) ? MODE_ROUNDS[mode] : TOTAL_ROUNDS;
  }
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

  function contextRound(state, consult, mode) {
    if (has(ROUND_OF, state)) return ROUND_OF[state];
    if (has(CONTEXT_ROUND, state)) return CONTEXT_ROUND[state];
    if (state === 'VERIFYING' || state === 'COMPLETED') return consult ? 1 : totalRounds(mode);
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
      state: null, since: NaN, startAt: NaN, endedAt: null, step: 0, round: 0, consult: false, reason: null, blocked: null,
      roundNoted: {}, roundDoneAt: {}, playMs: PLAYBACK_MS,
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
    var r = contextRound(state, m.consult, m.mode);
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
    if (typeof rec.playback_ms === 'number' && rec.playback_ms > 0) m.playMs = rec.playback_ms; // demo fits its lines to its own windows
    var snap = obj(rec.state);
    if (m.frames === 0 && text(snap.state)) {
      setState(m, snap.state, Date.parse(snap.updated_at));
      if (!has(STEP_INDEX, snap.state) && text(snap.resume_phase) && has(STEP_INDEX, snap.resume_phase)) {
        m.step = STEP_INDEX[snap.resume_phase];
        var rr = contextRound(snap.resume_phase, m.consult, m.mode);
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
    if (rec.blocked_reason && typeof rec.blocked_reason === 'object') m.blocked = rec.blocked_reason;
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
      if (!m.consult && r <= totalRounds(m.mode) && !m.roundNoted[r] && allAccepted(m, r)) {
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

  // ------------------------------------------------------- blocked reason

  /* An elder's full name, from the seat data when it is loaded; never a pronoun or a raw id. */
  function nameOf(id) {
    var seats = ns.seats;
    var s = seats && typeof seats.get === 'function' ? seats.get(id) : null;
    if (s && text(s.name) && s.name !== id) return s.name;
    return String(id).split('-').map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(' ');
  }

  var ROUND_PLAIN = { 1: 'round 1 (opening positions)', 2: 'round 2 (debate)', 3: 'round 3 (the vote)' };
  function roundPlain(round) {
    if (!isFinite(round)) return '';
    if (has(ROUND_PLAIN, round)) return ROUND_PLAIN[round];
    return 'round ' + round + ' (debate)';
  }

  function listNames(ids) {
    var names = ids.map(nameOf);
    return names.length < 2 ? names.join('') : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
  }

  /*
   * Machine outcome codes the runner writes to the attempt ledger and the job
   * row. A seat is classified ONLY from these typed codes; message text is
   * never parsed. A code this build does not know stays unclassified rather
   * than being guessed into "rejected" or "did not answer".
   */
  var OUTCOME_CLASS = {
    output_validation_failed: 'rejected',
    transport_rejected: 'provider_failed',
    transport_not_accepted: 'provider_failed',
    transport_failed: 'provider_failed',
    provider_completion_unknown: 'no_result',
    completion_unknown: 'no_result'
  };
  var OUTCOME_PLAIN = {
    output_validation_failed: 'response failed validation',
    transport_rejected: 'provider request refused',
    transport_not_accepted: 'provider request not accepted',
    transport_failed: 'provider request failed',
    provider_completion_unknown: 'no result recorded',
    completion_unknown: 'no result recorded'
  };

  function outcomeClass(code) {
    return typeof code === 'string' && has(OUTCOME_CLASS, code) ? OUTCOME_CLASS[code] : null;
  }

  function lastErrorFor(b, seatId) {
    var errors = Array.isArray(b.last_errors) ? b.last_errors : [];
    var found = null;
    errors.forEach(function (e) {
      if (e && e.seat_id === seatId && typeof e.outcome_code === 'string') found = e;
    });
    return found;
  }

  /**
   * One plain sentence for a blocked session, from the service's blocked_reason.
   * Missing seats are grouped by the TYPED outcome code: an output rejected by
   * validation says so, a provider failure says so, and only a seat with no
   * recorded result keeps "has not answered". Unknown codes stay unclassified.
   * Null when the service sent no blocked_reason.
   */
  function blockedText(m) {
    var b = obj(m.blocked);
    var missing = Array.isArray(b.missing_seats) ? b.missing_seats.filter(function (x) { return typeof x === 'string'; }) : [];
    if (!missing.length) return text(b.detail);
    var mr = Number(b.missing_round);
    var where = isFinite(mr) && mr >= 1 ? ' in ' + roundPlain(mr) : '';
    var groups = { rejected: [], provider_failed: [], no_result: [], unclassified: [] };
    missing.forEach(function (seat) {
      var e = lastErrorFor(b, seat);
      var kind = e ? outcomeClass(e.outcome_code) : null;
      (kind ? groups[kind] : groups.unclassified).push(seat);
    });
    var clauses = [];
    if (groups.rejected.length) clauses.push('responses from ' + listNames(groups.rejected) + ' failed validation');
    if (groups.provider_failed.length) clauses.push('the provider request for ' + listNames(groups.provider_failed) + ' failed');
    if (groups.no_result.length) clauses.push(listNames(groups.no_result) + (groups.no_result.length === 1 ? ' has' : ' have') + ' not answered');
    if (groups.unclassified.length) clauses.push('no accepted response was recorded from ' + listNames(groups.unclassified));
    var joined = clauses.length === 1 ? clauses[0]
      : clauses.length === 2 ? clauses[0] + ' and ' + clauses[1]
        : clauses.slice(0, -1).join(', ') + ', and ' + clauses[clauses.length - 1];
    var out = 'The council is blocked because ' + joined + where + '.';
    if (groups.no_result.length) {
      var calls = Array.isArray(b.unfinished_calls) ? b.unfinished_calls : [];
      var minutes = null;
      calls.forEach(function (c) {
        var n = Number(c && c.minutes);
        if (minutes === null && isFinite(n)) minutes = n;
      });
      out += ' The provider call ended with no result recorded' + (minutes !== null ? ' about ' + minutes + ' minutes after it started' : '') + '.';
    }
    return out;
  }

  /**
   * Technical validation detail, kept OUT of the sentence above. The room
   * renders each entry inside a native <details> with textContent only, so a
   * raw schema message is available but never reads as the council's summary
   * and never becomes markup.
   */
  function blockedDetails(m) {
    var b = obj(m.blocked);
    var out = [];
    function push(label, value) {
      var t = text(value);
      if (!t) return;
      for (var i = 0; i < out.length; i += 1) if (out[i].text === t) return;
      out.push({ label: label, text: t });
    }
    push('Service detail', b.detail);
    if (!text(b.detail)) push('Service detail', m.reason);
    (Array.isArray(b.last_errors) ? b.last_errors : []).forEach(function (e) {
      if (!e || typeof e.seat_id !== 'string') return;
      var code = text(e.outcome_code);
      var label = nameOf(e.seat_id) + (code && has(OUTCOME_PLAIN, code) ? ': ' + OUTCOME_PLAIN[code] : code ? ': ' + code.replace(/_/g, ' ') : '');
      if (text(e.message)) push(label, e.message);
      else if (code) push(label, code);
    });
    (Array.isArray(b.unfinished_calls) ? b.unfinished_calls : []).forEach(function (c) {
      if (!c) return;
      var n = Number(c.minutes);
      var op = text(c.operation_id);
      push('Unfinished provider call', (op ? op + ': ' : '') + 'no result recorded' + (isFinite(n) ? ' about ' + n + ' minutes after it started' : '') + '.');
    });
    return out;
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

  // Internal ids (con-1, fact-1, unk-1, asm-1, ev-1, Crux-1) never reach the page: a bracketed id is
  // dropped, a bare one becomes the brief's own plain word for it.
  var ID = '(?:con|fact|unk|asm|ev)-\\d+';
  var ID_BRACKET = new RegExp('\\s*\\((?:(?:the )?brief (?:unknown|assumption|fact|constraint|evidence) )?' + ID + '(?:,\\s*' + ID + ')*[^()]*\\)', 'gi');
  var ID_BARE = new RegExp('\\b(?:(?:the )?brief (?:unknown|assumption|fact|constraint|evidence) )?(con|fact|unk|asm|ev)-\\d+\\b', 'gi');
  var ID_WORD = { con: "the brief's limit", fact: "the brief's fact", unk: "the brief's open question", asm: "the brief's assumption", ev: 'the evidence on file' };
  function plain(t) {
    if (typeof t !== 'string') return t;
    return t.replace(ID_BRACKET, '').replace(ID_BARE, function (_, k) { return ID_WORD[k.toLowerCase()]; })
      .replace(/\bCrux-(\d+)/g, 'Fault line $1').replace(/ {2,}/g, ' ').replace(/ ([,.;:])/g, '$1');
  }

  function firstText(list) {
    if (!Array.isArray(list)) return null;
    for (var i = 0; i < list.length; i++) if (text(list[i])) return text(list[i]);
    return null;
  }

  function cardView(m, round, card, accepted) {
    if (!card) {
      // Round 3 is the ratification pass only for the four older modes; in
      // light/medium/heavy it is another advisor round.
      var vote = round === 3 && !m.consult && !has(MODE_ROUNDS, m.mode);
      return { round: round, kind: vote ? 'ratification' : m.consult ? 'consult' : 'advisor', stance: null, stanceText: null,
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
      line: plain(line), resolutionStance: text(card.resolution_stance), pending: false
    };
  }

  function seatCards(m, id) {
    var s = m.seats[id];
    var out = {};
    var rounds = {};
    Object.keys(s.cards).forEach(function (k) { rounds[k] = true; });
    Object.keys(s.accepted).forEach(function (k) { rounds[k] = true; });
    Object.keys(rounds).map(Number).filter(function (r) { return isFinite(r) && r >= 1; })
      .sort(function (a, b) { return a - b; })
      .forEach(function (r) {
        if (s.cards[r]) out[r] = cardView(m, r, s.cards[r], true);
        else out[r] = cardView(m, r, null, true);
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
      reasons: Array.isArray(v.main_reasons) ? v.main_reasons.map(plain) : [],
      kind: text(v.result_kind) || 'scored'
    };
  }

  function roundLabel(m) {
    var s = m.state;
    if (!s || PREP[s]) return 'GETTING READY';
    var of = ' OF ' + totalRounds(m.mode);
    if (has(ROUND_OF, s)) return 'ROUND ' + ROUND_OF[s] + of;
    if (s === 'CRUX_REVIEW') return 'AFTER ROUND 1' + of;
    if (s === 'DRAFT_RESOLUTION') return 'AFTER ROUND 2' + of;
    if (s === 'VERIFYING') return 'FINAL CHECKS';
    if (s === 'COMPLETED') return 'VERDICT';
    if (s === 'CONSULTING') return 'CONSULT';
    return s.replace(/_/g, ' ');
  }

  /* Friendly names for the model routes: a raw route id never reaches the screen. */
  var ROUTE_LABELS = {
    'demo-replay': 'Sample replay',
    'claude-configured': 'Claude Code',
    'claude-nine-configured': 'Claude Code (Nine)',
    'deepseek-configured': 'DeepSeek',
    'google-configured': 'Google Gemini',
    'ollama-configured': 'Ollama',
    'openrouter-configured': 'OpenRouter',
    'agnes-configured': 'Agnes',
    '9router-configured': '9Router',
    'openai-configured': 'OpenAI'
  };
  var MODEL_LABELS = { latest_deepseek_flash: 'newest DeepSeek Flash', harness_default: '' };

  function routeLabel(routeId, model) {
    if (!routeId) return '';
    var m = has(MODEL_LABELS, model) ? MODEL_LABELS[model] : model || '';
    var name = has(ROUTE_LABELS, routeId) ? ROUTE_LABELS[routeId] : m || 'the selected model';
    return has(ROUTE_LABELS, routeId) && m ? name + ' (' + m + ')' : name;
  }

  function explainer(m) {
    var label = routeLabel(m.route.routeId, m.route.model);
    var route = label ? ' on ' + label : '';
    return 'Each advisor writes an independent position' + route + '. Their lines play here as soon as the round is in.';
  }

  /** The render-ready SessionView at wall-clock time nowMs. */
  function view(m, nowMs) {
    var state = m.state;
    var inRound = has(ROUND_OF, state) ? ROUND_OF[state] : state === 'CONSULTING' ? 1 : 0;
    var ctx = inRound || (state && !PREP[state] ? m.round : 0);
    var copy = (state && COPY[state]) || COPY.DRAFT;
    var elapsed = Math.max(0, nowMs - (isFinite(m.since) ? m.since : nowMs));

    // A blocked session names the seats it is short of. Their seat label says
    // what actually happened (rejected, provider failure, no result) instead
    // of the generic "has not spoken yet".
    var seatBlocked = {};
    if (state === 'BLOCKED') {
      var blockedSeats = Array.isArray(obj(m.blocked).missing_seats)
        ? obj(m.blocked).missing_seats.filter(function (x) { return typeof x === 'string'; })
        : [];
      blockedSeats.forEach(function (id) {
        var e = lastErrorFor(obj(m.blocked), id);
        seatBlocked[id] = e ? (outcomeClass(e.outcome_code) || 'unclassified') : 'unclassified';
      });
    }

    var done = 0;
    var writers = [];
    var rows = m.seatIds.map(function (id) {
      var s = m.seats[id];
      var status = 'idle';
      if (ctx && (s.accepted[ctx] || s.cards[ctx])) { status = 'done'; done += 1; }
      else if (inRound) { status = 'writing'; writers.push(id); }
      if (has(seatBlocked, id)) status = 'blocked';
      return {
        id: id, status: status, spotlight: false, bubble: { kind: 'none', text: '' }, latest: null,
        blockedKind: has(seatBlocked, id) ? seatBlocked[id] : null, cards: seatCards(m, id)
      };
    });
    var total = m.seatIds.length;
    var complete = inRound > 0 && total > 0 && done === total;

    // Lines play back once a round is in and through the chair phase that follows it.
    var playRound = complete ? inRound : state === 'CRUX_REVIEW' ? 1 : state === 'DRAFT_RESOLUTION' ? 2 : state === 'VERIFYING' ? contextRound(state, m.consult, m.mode) : 0;
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
      var pick = playable[Math.floor(Math.max(0, nowMs - start) / m.playMs) % playable.length];
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
      Object.keys(m.seats[id].cards).forEach(function (k) {
        var r = Number(k);
        if (isFinite(r) && r >= 1 && r > votesRound) votesRound = r;
      });
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

    var keyPoints = m.keyPoints.map(function (k) { return { label: k.label, detail: plain(k.detail), at: k.at }; });
    if (state === 'COMPLETED' && verdict) {
      var rec = verdict.recommendedOptionId ? optionText(m, verdict.recommendedOptionId) : null;
      keyPoints.push({ label: 'VERDICT: ' + verdict.labelText.toUpperCase(), detail: rec, at: null });
    }

    var status = state && has(STATUS_OF, state) ? STATUS_OF[state] : !state || PREP[state] ? 'preparing' : 'running';
    var blockedMsg = state === 'BLOCKED' ? blockedText(m) : null;
    var statusText = { preparing: 'Getting ready.', running: 'In progress.', paused: state === 'PAUSE_REQUESTED' ? 'Pause requested.' : 'Paused.',
      blocked: blockedMsg || m.reason || 'Blocked.', cancelled: state === 'CANCEL_REQUESTED' ? 'Cancel requested.' : 'Cancelled.',
      failed: m.reason || 'Failed.', complete: 'Verdict reached.' }[status];

    var headline = copy[1];
    var explain = copy[2] || explainer(m);
    if (state === 'COMPLETED' && verdict) {
      var named = verdict.recommendedOptionId ? optionText(m, verdict.recommendedOptionId) : null;
      explain = 'Verdict: ' + verdict.labelText + (named ? '. Recommended: ' + named + '.' : '.');
    }
    if (blockedMsg) explain = blockedMsg;
    else if ((state === 'BLOCKED' || state === 'FAILED') && m.reason) explain = m.reason;

    var inWork = inRound > 0;
    var progress;
    if (state === 'COMPLETED') progress = { indeterminate: false, value: 1 };
    else if (inWork && done > 0) progress = { indeterminate: false, value: total ? done / total : 0 };
    else progress = { indeterminate: true, value: 0 };
    var progressText = inWork ? done + ' of ' + total + ' advisors in' : state === 'COMPLETED' ? 'Verdict reached' : state === 'BLOCKED' ? 'Blocked' : state === 'FAILED' ? 'Failed' : 'The chair is working';

    var end = m.endedAt !== null ? m.endedAt : nowMs;
    return {
      id: m.sessionId, demo: m.demo, sample: m.sample, mode: m.mode, question: m.question,
      route: { routeId: m.route.routeId, model: m.route.model },
      state: state, status: status, statusText: statusText,
      steps: steps(m), options: options, votesRound: votesRound || null, voters: voters, verdict: verdict,
      round: {
        label: roundLabel(m), number: inRound || null, total: totalRounds(m.mode), headline: headline, explain: explain,
        // Running: time in this state. Finished: how long the whole session took (frozen).
        timer: clock(end - (m.endedAt !== null && isFinite(m.startAt) ? m.startAt : isFinite(m.since) ? m.since : end)), progress: progress, progressText: progressText,
        weighing: weighing, complete: complete,
        // A tallied vote is only final after the verdict is validated; while a
        // session is blocked the count is a partial preference record.
        countsFinal: state === 'COMPLETED',
        // Raw validation detail stays out of headline/explain and is rendered
        // only inside the room's native <details> disclosure.
        blockedDetails: state === 'BLOCKED' ? blockedDetails(m) : []
      },
      seats: rows, keyPoints: keyPoints
    };
  }

  ns.state = { create: create, apply: apply, applyRecord: applyRecord, view: view, stepOf: stepOf, routeLabel: routeLabel };
})(typeof globalThis !== 'undefined' ? globalThis : this);
