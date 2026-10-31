/*
 * Council chamber advisory panel.
 *
 * The finished state used to show only the stage narrator and a bare option
 * row. This panel renders what the validated verdict already carries: the
 * recommendation in plain language, the reasons, the conditions, the strongest
 * dissent, the proposed next steps and the unknowns. Every string comes from
 * the session read the store already fetched (GET /council/<id>); nothing is
 * inferred, scored or invented here.
 *
 * Advisory only: this file never posts. Its one action hands a follow-up
 * question to the existing "New question" composer, which convenes a SEPARATE
 * council session behind its own approval (POST /api/council/convene). Option
 * selection is a highlight saved in this browser only: the service exposes no
 * endpoint that records an owner choice, so none is faked.
 *
 * Pure API for tests: councilChamber.advisory.model / .optionsModel /
 * .optionBadges / .isStandIn / .labelText / .unique / .requestText.
 */
(function (root) {
  'use strict';
  var ns = (root.councilChamber = root.councilChamber || {});

  // ---------------------------------------------------------------- pure

  // The council's own generated stand-in when no options were supplied. It is
  // the brief's literal label, not a semantic guess about the owner's wording.
  var STAND_IN = ['no option has been chosen yet'];

  var LABELS = {
    GO: 'Go',
    GO_WITH_CONDITIONS: 'Go, with conditions',
    RESHAPE: 'Reshape',
    DONT_DO_IT: "Don't do it",
    WAIT: 'Wait',
    INSUFFICIENT_EVIDENCE: 'Not enough evidence'
  };

  function txt(v) {
    return typeof v === 'string' && v.trim() ? v.trim() : null;
  }
  function arr(v) {
    return Array.isArray(v) ? v : [];
  }
  function obj(v) {
    return v && typeof v === 'object' ? v : {};
  }
  function letterAt(i) {
    return String.fromCharCode(65 + i);
  }

  /** True when this option label is the council's generated placeholder. */
  function isStandIn(label) {
    var t = typeof label === 'string' ? label.toLowerCase() : '';
    if (!t) return true;
    for (var i = 0; i < STAND_IN.length; i += 1) {
      if (t.indexOf(STAND_IN[i]) !== -1) return true;
    }
    return false;
  }

  function labelText(raw) {
    if (!raw) return null;
    return Object.prototype.hasOwnProperty.call(LABELS, raw) ? LABELS[raw] : String(raw);
  }

  /** Exact-duplicate removal that keeps the first occurrence and its order. */
  function unique(list) {
    var seen = {};
    var out = [];
    arr(list).forEach(function (item) {
      var value = txt(item);
      if (!value || seen[value]) return;
      seen[value] = true;
      out.push(value);
    });
    return out;
  }

  /**
   * Options the council actually weighed. The session view carries letters,
   * vote counts, scores and the recommended mark; the brief is the fallback
   * when the view has not folded an option in yet.
   */
  function optionsModel(record, session) {
    var rec = obj(record);
    var brief = arr(obj(rec.brief).options);
    var view = arr(session && session.options);
    var voters = session && typeof session.voters === 'number' ? session.voters : null;
    var recommendedId = txt(obj(rec.verdict).recommended_option_id);
    var rows = view.length
      ? view
      : brief.map(function (o, i) {
          return { id: o && o.id, letter: letterAt(i), label: o && o.label, votes: null, score: null };
        });
    return rows.map(function (o, i) {
      var row = obj(o);
      var label = txt(row.label) || '';
      var id = txt(row.id) || '';
      return {
        id: id,
        letter: txt(row.letter) || letterAt(i),
        label: label,
        substantial: !!label && !isStandIn(label),
        votes: typeof row.votes === 'number' ? row.votes : null,
        voters: voters,
        score: typeof row.score === 'number' && isFinite(row.score) ? row.score : null,
        recommended: row.recommended === true || (!!recommendedId && recommendedId === id)
      };
    });
  }

  /**
   * The chips one option card may show. An older record can carry a vote count,
   * a score and a recommended mark for the council's generated placeholder; that
   * is historical metadata, not a measured result, so only a substantial option
   * gets the success badges and a placeholder says what it is instead.
   */
  function optionBadges(option) {
    var o = obj(option);
    if (o.substantial !== true) {
      return { recommended: false, votes: null, score: null, note: 'Placeholder, not a weighed option' };
    }
    return {
      recommended: o.recommended === true,
      votes:
        typeof o.votes === 'number' && typeof o.voters === 'number' && o.voters > 0
          ? o.votes + ' of ' + o.voters + ' advisors'
          : null,
      score: typeof o.score === 'number' ? 'Scored ' + o.score + ' out of 10' : null,
      note: null
    };
  }

  function scoreFor(verdict, optionId) {
    var found = null;
    arr(obj(verdict).option_scores).forEach(function (s) {
      if (found !== null || !s || s.option_id !== optionId) return;
      if (typeof s.display_score === 'number' && isFinite(s.display_score)) found = s.display_score;
    });
    return found;
  }

  function numOrNull(v) {
    return typeof v === 'number' && isFinite(v) ? v : null;
  }

  /**
   * CTR-156: readiness read from the shared projection only. The verdict word
   * and readiness are different facts: DONT_DO_IT, RESHAPE, WAIT and
   * INSUFFICIENT_EVIDENCE never become ready, and an unresolved or failed
   * hard constraint or a blocking ratification state is stated explicitly.
   * Nothing is derived here; the projection already decided it.
   */
  function readinessModel(raw) {
    var r = obj(raw);
    var rat = obj(r.ratification);
    function rows(list) {
      return arr(list)
        .map(function (item) {
          var row = obj(item);
          return {
            text: txt(row.text) || txt(row.constraint_id) || '',
            advisor: txt(row.advisor),
            kind: txt(row.kind_text),
            status: txt(row.status_text),
            resultText: txt(row.result_text),
            checker: txt(row.checker)
          };
        })
        .filter(function (row) {
          return row.text;
        });
    }
    return {
      status: txt(r.status),
      headline: txt(r.headline),
      reasons: unique(r.status_reasons),
      blockers: rows(r.blockers),
      safeguards: rows(r.safeguards),
      hardFindings: rows(r.hard_constraint_findings),
      ratification: txt(rat.status)
        ? {
            status: txt(rat.status),
            text: txt(rat.status_text),
            blocks: rat.blocks_readiness === true
          }
        : null,
      note: txt(r.note),
      blockerCount: numOrNull(r.blocker_count) || 0,
      safeguardCount: numOrNull(r.safeguard_count) || 0
    };
  }

  /**
   * Everything the panel shows, derived only from the session record and the
   * session view. `actionable` is false when the council had no real choice to
   * weigh, so no green light is presented for a placeholder option.
   *
   * CTR-156: when the session read carries `reader_projection` (the one shared
   * projection the report renderer also uses), the panel reads readiness, the
   * canonical information-needed list, the plan's first recorded action and
   * the exact per-step acceptance text from it. When it does not, the panel
   * keeps its historical verdict-only rendering and says readiness was not
   * recorded; it never invents readiness from the verdict word.
   */
  function model(record, session) {
    var rec = obj(record);
    var verdict = rec.verdict && typeof rec.verdict === 'object' ? rec.verdict : null;
    var options = optionsModel(rec, session);
    var projection = rec.reader_projection && typeof rec.reader_projection === 'object'
      ? rec.reader_projection
      : null;
    var summary = projection ? obj(projection.summary) : null;
    var plan = projection ? obj(projection.plan) : null;
    var dvr = projection ? obj(projection.decision_vs_readiness) : null;
    var readiness = dvr ? obj(dvr.readiness) : null;
    var out = {
      present: !!verdict,
      kind: 'none',
      actionable: false,
      demo: rec.demo === true,
      sample: rec.sample === true,
      title: '',
      sub: '',
      // Plain wording for the screen. `title`/`sub` stay the model's stable
      // fields; these two are what the panel paints.
      headline: '',
      subLine: '',
      explanation: '',
      optionChip: null,
      decisionChip: null,
      preferenceNote: null,
      scoreNote: null,
      startHere: null,
      label: null,
      score: null,
      matches: null,
      recommendedId: null,
      recommendedLetter: null,
      reasons: [],
      conditions: [],
      objection: null,
      steps: [],
      unknowns: [],
      options: options,
      canCompare: false,
      consultAnswer: null,
      consultNextStep: null,
      // CTR-156 shared-projection fields.
      projection: projection !== null,
      readiness: null,
      readinessMissing: false,
      informationNeeded: [],
      informationNote: null,
      informationSource: null,
      councilUnknowns: [],
      councilUnknownCount: 0,
      councilUnknownShown: 0,
      councilUnknownRemoved: 0,
      whatWouldChangeRemoved: 0,
      parallelNote: null,
      planNote: null
    };
    if (!verdict) return out;

    if (verdict.result_kind === 'consult') {
      out.kind = 'consult';
      out.consultAnswer = txt(obj(verdict.consult_card).answer);
      out.consultNextStep = txt(verdict.next_step);
      out.title = 'The council answered your question.';
      out.sub = out.consultAnswer || 'The answer was recorded without a summary line.';
      // The answer itself is the headline; the proposed next step follows it.
      out.headline = out.consultAnswer || out.title;
      out.subLine = out.consultNextStep ? 'Next step: ' + out.consultNextStep : '';
      out.canCompare = options.length > 1;
      return out;
    }

    out.kind = 'scored';
    out.reasons = unique(verdict.main_reasons);
    out.conditions = unique(verdict.prerequisites);

    // CTR-156: the canonical "Information needed" list is the brief's own
    // unknowns from the shared projection, with any verdict-only additions.
    // The council's restated critical unknowns stay as their own record, with
    // an explicit total/shown/collapsed count. Nothing is silently cut.
    if (summary) {
      out.informationNeeded = unique(summary.information_needed);
      out.informationNote = txt(summary.information_needed_note);
      out.informationSource = txt(summary.information_needed_source);
      out.councilUnknowns = unique(summary.council_unknowns);
      out.councilUnknownCount =
        numOrNull(summary.council_unknowns_count) || 0;
      out.councilUnknownShown =
        numOrNull(summary.council_unknowns_shown) || out.councilUnknowns.length;
      out.councilUnknownRemoved =
        numOrNull(summary.council_unknowns_removed) || 0;
      out.whatWouldChangeRemoved =
        numOrNull(summary.what_would_change_the_answer_removed) || 0;
      out.unknowns = out.informationNeeded.length
        ? out.informationNeeded
        : unique(verdict.critical_unknowns);
    } else {
      out.unknowns = unique(verdict.critical_unknowns);
      out.informationNeeded = out.unknowns.slice();
    }
    out.objection = txt(verdict.strongest_dissent);

    // Steps come from the shared plan when present, so the screen shows the
    // same recorded first action, acceptance text and approval line as the
    // report. The raw proposals remain the fallback for older records.
    if (plan) {
      out.steps = arr(plan.steps)
        .map(function (s) {
          var step = obj(s);
          return {
            number: numOrNull(step.step_number),
            title: txt(step.title) || '',
            description: txt(step.what_to_do) || '',
            risk: txt(step.risk_text),
            doneWhen: unique(step.done_when),
            doneWhenNote: txt(step.done_when_note),
            approvalText: txt(step.approval_text)
          };
        })
        .filter(function (s) {
          return s.title;
        });
      out.parallelNote = txt(plan.parallel_eligible_note);
      out.planNote = txt(plan.dependency_note);
    } else {
      out.steps = arr(verdict.action_proposals)
        .filter(function (a) {
          return a && txt(a.title);
        })
        .map(function (a) {
          return {
            number: null,
            title: txt(a.title),
            description: txt(a.description),
            risk: txt(a.risk_class),
            doneWhen: [],
            doneWhenNote: null,
            approvalText: null
          };
        });
    }

    if (readiness && txt(readiness.status)) {
      out.readiness = readinessModel(readiness);
    } else {
      // Older saved reads have no projection. Say so rather than infer a
      // readiness state from the verdict word.
      out.readinessMissing = true;
    }

    var recommendedId = txt(verdict.recommended_option_id);
    var recommended = null;
    options.forEach(function (o) {
      if (!recommended && recommendedId && o.id === recommendedId) recommended = o;
    });
    var substantial = options.filter(function (o) {
      return o.substantial;
    });

    out.recommendedId = recommendedId;
    out.recommendedLetter = recommended ? recommended.letter : null;
    out.label = labelText(txt(verdict.label));
    out.score = recommendedId ? scoreFor(verdict, recommendedId) : null;
    out.matches =
      recommended && typeof recommended.votes === 'number' && typeof recommended.voters === 'number' && recommended.voters > 0
        ? recommended.votes + ' of ' + recommended.voters + ' advisors preferred it'
        : null;
    out.canCompare = options.length > 1;

    if (!recommendedId) {
      out.explanation = 'The council did not recommend an option.';
    } else if (!recommended) {
      out.explanation = 'The recorded recommendation names an option that is not in this brief any more.';
    } else if (!recommended.substantial) {
      out.explanation = 'The option it named is a placeholder, not a real choice.';
    } else if (substantial.length < 2) {
      out.explanation = 'Only one real option was supplied, so the council had nothing to compare.';
    }

    out.actionable = !out.explanation;
    if (out.actionable) {
      out.title = 'The council recommends Option ' + recommended.letter + '.';
      out.sub = recommended.label;
      // The owner reads the approach itself first; the letter and the verdict
      // word are context, not the answer.
      out.headline = recommended.label;
      out.optionChip = 'Option ' + recommended.letter;
      out.decisionChip = out.label ? 'Decision: ' + out.label : null;
      out.subLine = 'Option ' + recommended.letter + (out.label ? ' · ' + out.label : '');
      out.preferenceNote = out.matches
        ? out.matches + '. That is how many advisors picked this option, not a probability.'
        : null;
      out.scoreNote = typeof out.score === 'number' ? 'Score ' + out.score + ' out of 10, the council’s own rating, not a probability.' : null;
      // One primary move: the plan's recorded first action when the shared
      // projection names one, else the council's first proposed step, else the
      // condition that must be cleared before anything else. Every other step
      // stays in the full list below. Where more than one step records no
      // dependency, the note says so and the recorded order is kept.
      var startHere = null;
      if (plan && numOrNull(plan.start_here_step_number) !== null) {
        var wanted = numOrNull(plan.start_here_step_number);
        out.steps.forEach(function (s) {
          if (!startHere && s.number === wanted) startHere = s;
        });
      }
      if (!startHere && out.steps.length) startHere = out.steps[0];
      if (!startHere && out.conditions.length) {
        startHere = {
          number: null,
          title: 'Clear this condition first',
          description: out.conditions[0],
          risk: null,
          doneWhen: [],
          doneWhenNote: null,
          approvalText: null
        };
      }
      out.startHere = startHere;
    } else {
      out.title = 'No actionable recommendation';
      out.sub = out.explanation + ' Nothing here is an approval to act.';
      out.headline = out.title;
      // The safety sentence stays visible, not folded into a comment.
      out.subLine = out.explanation + ' Nothing here is an approval to act.';
    }
    return out;
  }

  /** The copyable request an owner hands to their agent. Read-only text. */
  function requestText(session, m) {
    var id = session && session.id ? String(session.id) : '';
    if (!id) return '';
    var head = 'Open council session ' + id + ' in the chamber and discuss its result with me before anything is planned.';
    if (m.kind === 'consult') return head + ' It is a consult, not a vote.';
    if (!m.actionable) {
      return (
        head +
        ' It recorded no actionable recommendation: ' +
        (m.explanation ? m.explanation.replace(/\.$/, '') : 'a placeholder option was named') +
        '.'
      );
    }
    var which = m.recommendedLetter ? ' Option ' + m.recommendedLetter : '';
    return (
      head +
      ' It recommends' +
      which +
      (m.label ? ' (' + m.label + ')' : '') +
      '. Show me the conditions and the proposed steps, and nothing else.'
    );
  }

  ns.advisory = {
    model: model,
    optionsModel: optionsModel,
    optionBadges: optionBadges,
    isStandIn: isStandIn,
    labelText: labelText,
    unique: unique,
    requestText: requestText
  };

  if (typeof document === 'undefined') return;

  // ----------------------------------------------------------------- DOM

  var host = document.getElementById('ch-advisory');
  if (!host) return;

  var PICK_KEY = 'councilChamber.pick.';
  var els = {};
  var renderedKey = null;
  var optionsKey = null;
  var current = null;
  var lastSessionId = null;
  var openFollow = false;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function setText(node, text) {
    var next = text == null ? '' : String(text);
    if (node.textContent !== next) node.textContent = next;
  }
  function setHidden(node, hidden) {
    if (node.hidden !== hidden) node.hidden = hidden;
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  function status(message) {
    setText(els.status, message);
  }

  /*
   * When this panel renders the finished answer it supersedes the decision
   * header's option bars and verdict badge: those show a bare "9" and a
   * "Verdict: Go" chip that read as an approval even when the council had no
   * real option to weigh. The class is presentation only; chamber-decision.js
   * keeps rendering its own model untouched.
   */
  var decision = document.getElementById('ch-decision');
  function markDecision(on) {
    if (decision && decision.classList) decision.classList.toggle('ch-dec--answered', on);
    // The room's one-line explainer repeats the verdict in shorthand ("Verdict:
    // Go. Recommended: Option A"), which is the stage narrator this panel
    // replaces. The room headline and the nine seats stay exactly as they are.
    if (document.body && document.body.classList) document.body.classList.toggle('ch-has-answer', on);
  }

  /*
   * One disclosure block. The summary is a native <summary> so keyboard and
   * screen readers get a real expand control; the count keeps the summary
   * honest about how much detail is folded away. Nothing is truncated: the
   * body always holds every item.
   */
  function block(title, open) {
    var node = el('details', 'ch-adv-block');
    node.open = open === true;
    var summary = el('summary', 'ch-adv-h3');
    var label = el('span', 'ch-adv-h3-text', title);
    var count = el('span', 'ch-adv-count');
    count.hidden = true;
    summary.appendChild(label);
    summary.appendChild(count);
    var body = el('div', 'ch-adv-body');
    node.appendChild(summary);
    node.appendChild(body);
    return { node: node, title: label, count: count, body: body };
  }

  function setBlockCount(part, total) {
    setText(part.count, total > 0 ? String(total) : '');
    setHidden(part.count, total === 0);
  }

  // A small native icon beside a text label. aria-hidden: the label carries
  // the meaning, the icon is never the only cue and no colour is relied on.
  function icon(kind) {
    // The SVG namespace is an inert identifier, never a request: browsers
    // resolve it from the SVG spec and never fetch it.
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('width', '16');
    svg.setAttribute('height', '16');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('class', 'ch-adv-ico');
    var path = document.createElementNS(NS, 'path');
    path.setAttribute('fill', 'currentColor');
    path.setAttribute(
      'd',
      kind === 'download'
        ? 'M7.1 1.5h1.8v6.2l2.3-2.3 1.3 1.3L8 11.2 3.5 6.7l1.3-1.3 2.3 2.3zM2.5 12.5h11V14h-11z'
        : 'M2 2.5h12v8.5H7.4L4 14v-3H2z'
    );
    svg.appendChild(path);
    return svg;
  }

  function buildShell() {
    host.classList.add('ch-adv');
    host.setAttribute('aria-labelledby', 'ch-adv-title');

    var head = el('div', 'ch-adv-head');
    els.kicker = el('p', 'ch-eyebrow ch-adv-kicker', 'The answer');
    els.title = el('h2', 'ch-adv-title');
    els.title.id = 'ch-adv-title';
    els.sub = el('p', 'ch-adv-sub');
    els.meta = el('div', 'ch-adv-meta');
    els.legend = el('p', 'ch-adv-legendline');
    els.note = el('p', 'ch-adv-note');
    head.appendChild(els.kicker);
    head.appendChild(els.title);
    head.appendChild(els.sub);
    head.appendChild(els.meta);
    head.appendChild(els.legend);
    head.appendChild(els.note);

    // Start here: one primary move, above the long detail. The full list of
    // proposed steps stays in its own block below.
    var start = el('div', 'ch-adv-start');
    start.hidden = true;
    els.startLabel = el('p', 'ch-adv-start-label', 'Start here');
    els.startTitle = el('p', 'ch-adv-start-title');
    els.startText = el('p', 'ch-adv-start-text');
    els.startChip = el('p', 'ch-adv-start-chip', 'Needs your approval before anything runs');
    els.startNote = el('p', 'ch-adv-start-note');
    start.appendChild(els.startLabel);
    start.appendChild(els.startTitle);
    start.appendChild(els.startText);
    start.appendChild(els.startChip);
    start.appendChild(els.startNote);
    els.start = start;

    var actions = el('div', 'ch-adv-actions');
    els.discuss = el('button', 'ch-btn ch-btn--primary ch-adv-btn');
    els.discuss.appendChild(icon('follow'));
    els.discussText = el('span', 'ch-adv-btn-text', 'Ask a follow-up');
    els.discuss.appendChild(els.discussText);
    els.discuss.type = 'button';
    els.discuss.setAttribute('aria-expanded', 'false');
    els.discuss.setAttribute('aria-controls', 'ch-adv-follow');
    els.discuss.addEventListener('click', function () {
      openFollow = !openFollow;
      els.discuss.setAttribute('aria-expanded', openFollow ? 'true' : 'false');
      setHidden(els.follow, !openFollow);
      status(openFollow ? 'Follow-up question field opened.' : 'Follow-up question field closed.');
      if (openFollow && els.followInput.focus) els.followInput.focus();
    });
    els.compare = el('button', 'ch-btn ch-adv-btn', 'Compare alternatives');
    els.compare.type = 'button';
    els.compare.setAttribute('aria-expanded', 'false');
    els.compare.setAttribute('aria-controls', 'ch-adv-options');
    els.compare.addEventListener('click', function () {
      els.compare.setAttribute('aria-expanded', 'true');
      els.optionsDetails.open = true;
      var focusable = els.optionsList.querySelector('input');
      if (focusable && focusable.focus) focusable.focus();
      else if (els.optionsWrap.scrollIntoView) els.optionsWrap.scrollIntoView({ block: 'nearest' });
      status('Showing the options the council weighed.');
    });
    actions.appendChild(els.discuss);
    actions.appendChild(els.compare);

    // Follow-up: a draft for a NEW council session, never a post into this one.
    els.follow = el('div', 'ch-adv-follow');
    els.follow.id = 'ch-adv-follow';
    var followLabel = el('label', 'ch-adv-label', 'Your follow-up question');
    followLabel.setAttribute('for', 'ch-adv-follow-input');
    els.followInput = el('textarea', 'ch-adv-input');
    els.followInput.id = 'ch-adv-follow-input';
    els.followInput.rows = 3;
    els.followInput.maxLength = 600;
    els.followInput.setAttribute('aria-describedby', 'ch-adv-follow-hint');
    els.followInput.addEventListener('input', function () {
      els.followGo.disabled = !txt(els.followInput.value);
    });
    els.followGo = el('button', 'ch-btn ch-btn--primary ch-adv-btn', 'Start a new council with this question');
    els.followGo.type = 'button';
    els.followGo.disabled = true;
    els.followGo.addEventListener('click', function () {
      var question = txt(els.followInput.value);
      if (question) handToComposer(question);
    });
    els.followHint = el('p', 'ch-adv-hint');
    els.followHint.id = 'ch-adv-follow-hint';
    els.follow.appendChild(followLabel);
    els.follow.appendChild(els.followInput);
    els.follow.appendChild(els.followHint);
    els.follow.appendChild(els.followGo);

    els.reasons = block('Why the council said this', false);
    els.conditions = block('Conditions it requires', true);
    els.objection = block('Strongest objection', false);
    els.steps = block('What the council proposes you do next', true);
    els.unknowns = block('What it still does not know', false);
    // CTR-156: readiness is its own block, never a second meaning for the
    // verdict chip. The council's restated unknown record is separate from the
    // canonical Information needed list.
    els.readiness = block('Can you act on this yet?', true);
    els.councilUnknowns = block('The council’s unknown record', false);

    els.optionsDetails = el('details', 'ch-adv-options-details');
    els.optionsSummary = el('summary', 'ch-adv-h3');
    els.optionsSummary.appendChild(el('span', 'ch-adv-h3-text', 'Alternatives the council weighed'));
    els.optionsCount = el('span', 'ch-adv-count');
    els.optionsSummary.appendChild(els.optionsCount);
    els.optionsDetails.appendChild(els.optionsSummary);

    els.optionsWrap = el('fieldset', 'ch-adv-options');
    els.optionsWrap.id = 'ch-adv-options';
    els.optionsLegend = el('legend', 'ch-adv-legend', 'Options the council weighed');
    els.optionsList = el('div', 'ch-adv-options-list');
    els.optionsNote = el('p', 'ch-adv-hint');
    els.optionsWrap.appendChild(els.optionsLegend);
    els.optionsWrap.appendChild(els.optionsList);
    els.optionsWrap.appendChild(els.optionsNote);

    var next = el('div', 'ch-adv-next');
    els.nextTitle = el('h3', 'ch-adv-h3', 'What happens next');
    els.nextText = el('p', 'ch-adv-text');
    var reqLabel = el('label', 'ch-adv-label', 'Ask your agent about this session');
    reqLabel.setAttribute('for', 'ch-adv-request');
    els.request = el('textarea', 'ch-adv-input ch-adv-input--mono');
    els.request.id = 'ch-adv-request';
    els.request.rows = 3;
    els.request.readOnly = true;
    els.copy = el('button', 'ch-btn ch-adv-btn', 'Copy request');
    els.copy.type = 'button';
    els.copy.addEventListener('click', copyRequest);
    next.appendChild(els.nextTitle);
    next.appendChild(els.nextText);
    next.appendChild(reqLabel);
    next.appendChild(els.request);
    next.appendChild(els.copy);

    els.status = el('p', 'ch-adv-status');
    els.status.setAttribute('role', 'status');
    els.status.setAttribute('aria-live', 'polite');

    // Council first: the result blocks sit under the room, and the follow-up
    // controls come after the results they act on.
    host.appendChild(head);
    host.appendChild(els.reasons.node);
    host.appendChild(els.conditions.node);
    host.appendChild(els.objection.node);
    host.appendChild(els.steps.node);
    host.appendChild(els.unknowns.node);
    host.appendChild(els.councilUnknowns.node);
    host.appendChild(els.optionsWrap);
    host.appendChild(next);

    // Integration anchor for the CTR-136 PDF lane: mount the PDF control into
    // this empty slot. This file creates no button and calls no endpoint; with
    // nothing mounted the slot takes no space (see chamber-advisory.css).
    els.pdf = el('div', 'ch-adv-pdf');
    els.pdf.id = 'ch-adv-pdf-slot';
    els.pdf.setAttribute('data-integration-anchor', 'ctr136-pdf');

    // Saved-session report: a native same-origin download link mounted into
    // the slot the layout owns, below the answer. It never enters the header
    // actions row. The service refuses every state except a completed sitting
    // with a validated verdict and serves real application/pdf bytes.
    els.report = el('a', 'ch-btn ch-adv-btn ch-adv-download');
    els.report.setAttribute('download', '');
    els.report.setAttribute('aria-label', 'Download this council report as a PDF');
    els.report.href = '#';
    els.report.appendChild(icon('download'));
    els.report.appendChild(el('span', 'ch-adv-btn-text', 'Download report (PDF)'));
    els.pdf.appendChild(els.report);

    host.appendChild(els.pdf);

    host.appendChild(actions);
    host.appendChild(els.follow);
    host.appendChild(els.status);

    // Presentation order: answer, Start here, the controls that act on it,
    // then the full detail. The appends above keep the node set stable; these
    // moves only decide where the same nodes paint, so the PDF and follow-up
    // controls are reachable without scrolling past every reason and condition.
    var early = el('div', 'ch-adv-early');
    early.appendChild(els.pdf);
    early.appendChild(actions);
    early.appendChild(els.follow);
    early.appendChild(els.status);
    host.insertBefore(els.start, els.reasons.node);
    host.insertBefore(early, els.reasons.node);
    // Readiness sits above the long detail and below the early controls, so a
    // blocked GO is visible before anyone reads the reasoning.
    host.insertBefore(els.readiness.node, els.reasons.node);
    // Alternatives fold away until asked for; every option stays in the DOM.
    host.insertBefore(els.optionsDetails, els.optionsWrap);
    els.optionsDetails.appendChild(els.optionsWrap);

    setHidden(els.follow, true);
  }

  // limit === null shows every item; otherwise the rest fold into a <details>.
  function fillList(target, items, tag, limit) {
    clear(target);
    if (!items.length) return;
    var cut = typeof limit === 'number' && limit > 0 && items.length > limit ? limit : items.length;
    var list = el(tag === 'ol' ? 'ol' : 'ul', 'ch-adv-list');
    items.slice(0, cut).forEach(function (item) {
      list.appendChild(el('li', 'ch-adv-item', item));
    });
    target.appendChild(list);
    if (cut < items.length) {
      var details = el('details', 'ch-adv-details');
      details.appendChild(
        el('summary', 'ch-adv-summary', 'Show all ' + items.length + ' (' + (items.length - cut) + ' more)')
      );
      var rest = el(tag === 'ol' ? 'ol' : 'ul', 'ch-adv-list');
      items.slice(cut).forEach(function (item) {
        rest.appendChild(el('li', 'ch-adv-item', item));
      });
      details.appendChild(rest);
      target.appendChild(details);
    }
  }

  function fillSteps(target, steps) {
    clear(target);
    if (!steps.length) return;
    var list = el('ol', 'ch-adv-list ch-adv-steps');
    steps.forEach(function (step) {
      var li = el('li', 'ch-adv-item ch-adv-step');
      li.appendChild(el('p', 'ch-adv-step-title', step.title));
      if (step.description && step.description !== step.title) {
        li.appendChild(el('p', 'ch-adv-step-text', step.description));
      }
      var meta = el('p', 'ch-adv-step-meta');
      if (step.risk) meta.appendChild(el('span', 'ch-adv-chip', step.risk + ' risk'));
      meta.appendChild(el('span', 'ch-adv-chip', 'needs its own approval'));
      li.appendChild(meta);
      // CTR-156: a blank "Done when" is a defect. Show the recorded finish
      // line when there is one, otherwise the model's honest note that the
      // saved record stated none.
      if (step.doneWhen && step.doneWhen.length) {
        li.appendChild(el('p', 'ch-adv-step-done', 'Done when: ' + step.doneWhen.join('; ')));
      } else if (step.doneWhenNote) {
        li.appendChild(el('p', 'ch-adv-step-done', step.doneWhenNote));
      }
      if (step.approvalText) {
        li.appendChild(el('p', 'ch-adv-step-approval', step.approvalText));
      }
      list.appendChild(li);
    });
    target.appendChild(list);
  }

  var READINESS_WORD = {
    ready: 'Ready to act',
    ready_with_conditions: 'Ready with conditions',
    blocked: 'Not ready yet',
    not_ready: 'Not ready to act',
    not_applicable: 'No plan readiness for a consultation'
  };

  function appendItems(body, title, items) {
    if (!items.length) return;
    body.appendChild(el('p', 'ch-adv-readiness-label', title));
    var list = el('ul', 'ch-adv-list');
    items.forEach(function (item) {
      list.appendChild(el('li', 'ch-adv-item', item));
    });
    body.appendChild(list);
  }

  /**
   * CTR-156: readiness is painted from the shared projection only. It is a
   * separate answer from the verdict: a GO can be blocked, and a WAIT or
   * DONT_DO_IT can never be called ready.
   */
  function paintReadiness(part, readiness, missing) {
    clear(part.body);
    setHidden(part.node, false);
    if (missing || !readiness) {
      part.body.appendChild(
        el(
          'p',
          'ch-adv-text',
          'Readiness was not recorded in this saved session read. The verdict on this panel is advice only.'
        )
      );
      setBlockCount(part, 0);
      return;
    }
    part.body.appendChild(
      el('p', 'ch-adv-readiness-status', READINESS_WORD[readiness.status] || readiness.status)
    );
    if (readiness.headline) {
      part.body.appendChild(el('p', 'ch-adv-text', readiness.headline));
    }
    appendItems(part.body, 'Reasons', readiness.reasons);
    appendItems(
      part.body,
      'Open blocking conditions (' + readiness.blockers.length + ')',
      readiness.blockers.map(function (b) {
        return b.text + (b.advisor ? ' — recorded by ' + b.advisor : '');
      })
    );
    appendItems(
      part.body,
      'Recorded safeguards (' + readiness.safeguards.length + ')',
      readiness.safeguards.map(function (s) {
        return s.text + (s.advisor ? ' — recorded by ' + s.advisor : '');
      })
    );
    appendItems(
      part.body,
      'Hard-constraint findings on the recommended option (' + readiness.hardFindings.length + ')',
      readiness.hardFindings.map(function (f) {
        return f.text + (f.resultText ? ': ' + f.resultText : '');
      })
    );
    if (readiness.ratification) {
      part.body.appendChild(
        el(
          'p',
          'ch-adv-text',
          'Ratification: ' +
            (readiness.ratification.text || readiness.ratification.status) +
            (readiness.ratification.blocks
              ? ' (blocks readiness)'
              : ' (does not block readiness)')
        )
      );
    }
    if (readiness.note) part.body.appendChild(el('p', 'ch-adv-hint', readiness.note));
    setBlockCount(part, readiness.blockers.length + readiness.hardFindings.length);
  }

  /**
   * CTR-156: the council's own restated unknown record, distinct from the
   * canonical Information needed list. The count line is transparent: total
   * recorded, collapsed repeats, and distinct rows shown. Every distinct row
   * is kept in the DOM.
   */
  function paintCouncilUnknowns(part, m) {
    clear(part.body);
    var shown = m.councilUnknowns.length;
    if (!shown && !m.councilUnknownCount) {
      setHidden(part.node, true);
      setBlockCount(part, 0);
      return;
    }
    setHidden(part.node, false);
    var line =
      m.councilUnknownCount > shown
        ? m.councilUnknownCount +
          ' recorded council statement(s); ' +
          m.councilUnknownRemoved +
          ' repeated after removing "Unknown:" framing; ' +
          shown +
          ' distinct shown below.'
        : shown + ' distinct council statement(s).';
    part.body.appendChild(el('p', 'ch-adv-hint', line));
    if (shown) {
      var list = el('ul', 'ch-adv-list');
      m.councilUnknowns.forEach(function (item) {
        list.appendChild(el('li', 'ch-adv-item', item));
      });
      part.body.appendChild(list);
    }
    setBlockCount(part, shown);
  }

  function readPick(sessionId) {
    try {
      return root.sessionStorage ? root.sessionStorage.getItem(PICK_KEY + sessionId) : null;
    } catch (e) {
      return null;
    }
  }

  function writePick(sessionId, optionId) {
    try {
      if (root.sessionStorage) root.sessionStorage.setItem(PICK_KEY + sessionId, optionId);
    } catch (e) {
      /* a blocked store only loses the highlight */
    }
  }

  function syncSelection() {
    var cards = els.optionsList.querySelectorAll('.ch-adv-option');
    for (var i = 0; i < cards.length; i += 1) {
      var input = cards[i].querySelector('input');
      cards[i].setAttribute('data-selected', input && input.checked ? 'true' : 'false');
    }
  }

  /**
   * One option card. Only a substantial option in a real comparison gets a
   * radio: a lone placeholder is shown as a plain card so the page never
   * offers a selection that means nothing.
   */
  function optionCard(option, sessionId, picked, selectable) {
    var card = el(selectable ? 'label' : 'div', 'ch-adv-option');
    card.setAttribute('data-selected', selectable && picked === option.id ? 'true' : 'false');
    if (selectable) {
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'ch-adv-option';
      input.value = option.id;
      input.className = 'ch-adv-radio';
      input.checked = picked === option.id;
      input.addEventListener('change', function () {
        writePick(sessionId, option.id);
        syncSelection();
        status('Option ' + option.letter + ' highlighted. This changes nothing in the council.');
      });
      card.appendChild(input);
    }

    var body = el('span', 'ch-adv-option-body');
    var line = el('span', 'ch-adv-option-line');
    var badges = optionBadges(option);
    line.appendChild(el('span', 'ch-adv-letter', option.letter));
    line.appendChild(el('span', 'ch-adv-option-label', option.label));
    if (badges.recommended) line.appendChild(el('span', 'ch-adv-chip ch-adv-chip--reco', 'Recommended'));
    body.appendChild(line);

    var meta = el('span', 'ch-adv-option-meta');
    if (badges.votes) meta.appendChild(el('span', 'ch-adv-chip', badges.votes));
    if (badges.score) meta.appendChild(el('span', 'ch-adv-chip', badges.score));
    if (badges.note) meta.appendChild(el('span', 'ch-adv-chip', badges.note));
    if (meta.firstChild) body.appendChild(meta);
    card.appendChild(body);
    return card;
  }

  function renderOptions(m) {
    var sessionId = current ? current.sessionId : '';
    var key = [sessionId, m.options.map(function (o) { return o.id; }).join('|')].join(':');
    var selectable = m.canCompare;
    if (key !== optionsKey) {
      optionsKey = key;
      clear(els.optionsList);
      if (m.options.length) {
        var picked = readPick(sessionId);
        var group = el('div', 'ch-adv-option-group');
        if (selectable) {
          group.setAttribute('role', 'radiogroup');
          group.setAttribute('aria-label', 'Compare the options the council weighed');
        }
        m.options.forEach(function (option) {
          group.appendChild(optionCard(option, sessionId, picked, selectable && option.substantial));
        });
        els.optionsList.appendChild(group);
      }
    }
    setHidden(els.compare, !m.canCompare);
    els.optionsNote.textContent = m.canCompare
      ? 'Highlighting an option is a view only: it is saved in this browser, it does not change the verdict, and it starts no work.'
      : 'Only one option was supplied, so there is nothing to compare.';
  }

  function copyRequest() {
    var text = els.request.value;
    if (!text) return;
    function fallback() {
      if (els.request.select) els.request.select();
      status('Copy is unavailable in this browser. The request is selected; copy it yourself.');
    }
    try {
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        root.navigator.clipboard.writeText(text).then(function () {
          status('Request copied.');
        }, fallback);
        return;
      }
    } catch (e) {
      /* fall through to the selection fallback */
    }
    fallback();
  }

  /**
   * The only action that leaves this panel, and it leaves as a DRAFT: the
   * existing composer opens with the question filled in, and nothing is sent
   * until the owner picks a route and presses Convene there.
   */
  function handToComposer(question) {
    var sessionId = current && current.sessionId;
    var q = document.getElementById('ch-composer-question');
    var context = document.getElementById('ch-composer-context');
    if (q) q.value = question;
    if (context && sessionId && context.value.indexOf(sessionId) === -1) {
      var line = 'Follow-up to council session ' + sessionId + '.';
      context.value = context.value ? context.value + '\n' + line : line;
    }
    status('Opening New question with your follow-up. Nothing has been sent yet.');
    document.dispatchEvent(new CustomEvent('chamber:open-composer', { detail: { opener: els.followGo } }));
  }

  function render(view) {
    var session = view && view.session ? view.session : null;
    var live = ns.live;
    var record = live && typeof live.getRecord === 'function' ? live.getRecord() : null;

    if (!session || !record || session.status !== 'complete') {
      setHidden(host, true);
      markDecision(false);
      renderedKey = null;
      return;
    }

    var m = model(record, session);
    if (!m.present) {
      setHidden(host, true);
      markDecision(false);
      renderedKey = null;
      return;
    }

    current = { sessionId: session.id, actionable: m.actionable, label: m.label };
    if (lastSessionId !== session.id) {
      lastSessionId = session.id;
      openFollow = false;
      els.discuss.setAttribute('aria-expanded', 'false');
      els.followInput.value = '';
      els.followGo.disabled = true;
      setHidden(els.follow, true);
    }

    var key = [
      session.id,
      m.kind,
      m.actionable,
      m.title,
      m.sub,
      m.reasons.length,
      m.conditions.length,
      m.steps.length,
      m.unknowns.length
    ].join('|');
    var fresh = key !== renderedKey;
    renderedKey = key;

    setHidden(host, false);
    markDecision(true);

    // The report route re-renders from the saved record under the same access
    // boundary as this page; the link exists only on this completed panel.
    els.report.href = '/council/' + encodeURIComponent(session.id) + '/report.pdf';
    els.report.setAttribute('download', 'council-report-' + session.id + '.pdf');

    // The plain approach is the headline; the letter and the verdict word are
    // context. A reader should never have to decode "Option C" to know what the
    // council actually recommended.
    setText(els.title, m.headline || m.title);
    setText(els.sub, m.subLine || m.sub);
    setText(
      els.kicker,
      m.kind === 'consult' ? 'The answer' : m.actionable ? 'The council recommends' : 'The result'
    );

    // Chips: the verdict word, the option letter, the advisor count and the
    // council's own score — each only when the record carries it. None of them
    // is presented as a probability.
    clear(els.meta);
    if (m.actionable) {
      if (m.decisionChip) els.meta.appendChild(el('span', 'ch-adv-chip ch-adv-chip--verdict', m.decisionChip));
      if (m.optionChip) els.meta.appendChild(el('span', 'ch-adv-chip', m.optionChip));
      if (m.matches) els.meta.appendChild(el('span', 'ch-adv-chip', m.matches));
      if (typeof m.score === 'number') {
        els.meta.appendChild(el('span', 'ch-adv-chip', 'Score ' + m.score + ' out of 10'));
      }
    } else if (m.kind === 'scored') {
      els.meta.appendChild(el('span', 'ch-adv-chip ch-adv-chip--warn', 'Not actionable'));
    }
    setHidden(els.meta, !els.meta.firstChild);
    setText(
      els.legend,
      m.actionable
        ? 'An advisor count says how many of the nine picked this option. A score is the council’s own 0–10 rating. Neither is a probability.'
        : ''
    );

    // One advice notice, not three. The controls that authorize real work stay
    // exactly where they are (New question convenes, a step needs approval).
    setText(
      els.note,
      m.demo
        ? 'Demo replay: this recommendation is fictional sample data, not a real council run.'
        : m.sample
          ? 'Sample session: synthetic data, not a real council run.'
          : 'Advice only. Acting on a step needs your own approval.'
    );

    // Start here: the one move to make first, above every long explanation.
    var startHere = m.actionable ? m.startHere : null;
    setHidden(els.start, !startHere);
    if (startHere) {
      setText(els.startTitle, startHere.title);
      setText(els.startText, startHere.description && startHere.description !== startHere.title ? startHere.description : '');
      setHidden(els.startText, !els.startText.textContent);
      setHidden(els.startChip, false);
      // Other independent first steps are named, never reordered.
      setText(els.startNote, m.parallelNote || '');
      setHidden(els.startNote, !m.parallelNote);
    }

    fillList(els.reasons.body, m.reasons, 'ul', null);
    setHidden(els.reasons.node, m.reasons.length === 0);
    setBlockCount(els.reasons, m.reasons.length);

    setText(els.conditions.title, m.actionable ? 'Conditions it requires' : 'Conditions the council would require');
    // No top-N cut: every condition the verdict carries stays in the panel.
    fillList(els.conditions.body, m.conditions, 'ol', null);
    setHidden(els.conditions.node, m.conditions.length === 0);
    setBlockCount(els.conditions, m.conditions.length);

    clear(els.objection.body);
    if (m.objection) els.objection.body.appendChild(el('p', 'ch-adv-text', m.objection));
    setHidden(els.objection.node, !m.objection);

    fillSteps(els.steps.body, m.steps);
    setHidden(els.steps.node, m.steps.length === 0);
    setBlockCount(els.steps, m.steps.length);
    if (m.planNote) els.steps.body.appendChild(el('p', 'ch-adv-hint', m.planNote));

    // CTR-156: the primary list is the canonical Information needed (the
    // brief's own unknowns). The council's restated record is its own block
    // below, with a transparent count.
    setText(
      els.unknowns.title,
      m.kind === 'scored' && m.projection ? 'Information needed' : 'What it still does not know'
    );
    fillList(els.unknowns.body, m.unknowns, 'ul', null);
    if (m.informationNote) {
      els.unknowns.body.appendChild(el('p', 'ch-adv-hint', m.informationNote));
    }
    setHidden(els.unknowns.node, m.unknowns.length === 0);
    setBlockCount(els.unknowns, m.unknowns.length);

    if (m.kind === 'scored') {
      paintReadiness(els.readiness, m.readiness, m.readinessMissing);
      paintCouncilUnknowns(els.councilUnknowns, m);
    } else {
      setHidden(els.readiness.node, true);
      setHidden(els.councilUnknowns.node, true);
    }

    renderOptions(m);
    setHidden(els.optionsDetails, m.options.length === 0);
    setText(els.optionsCount, String(m.options.length));
    setHidden(els.optionsCount, m.options.length === 0);

    els.followHint.textContent =
      'Opens New question as a draft. It convenes a separate council; nothing is sent until you press Convene there.';

    setText(
      els.discussText,
      m.kind === 'consult' ? 'Ask a follow-up' : m.actionable ? 'Ask a follow-up' : 'Ask about this result'
    );

    if (m.actionable) {
      els.nextText.textContent =
        'Take a proposed step to your agent and approve it there. The council advises; it does not execute, and a verdict is not an execution credential.';
    } else {
      els.nextText.textContent =
        'There is no recommendation you can act on yet. Ask a new question with at least two real options, or take the conditions above to your agent and decide deliberately.';
    }
    els.request.value = requestText(session, m);
    els.copy.disabled = !els.request.value;

    if (fresh) {
      status(m.actionable ? 'Recommendation loaded.' : 'This council has no actionable recommendation.');
    }
  }

  // ---------------------------------------------------------------- boot

  function init() {
    buildShell();
    render(ns.live && typeof ns.live.getView === 'function' ? ns.live.getView() : null);
    if (ns.live && typeof ns.live.subscribe === 'function') ns.live.subscribe(render);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})(typeof globalThis !== 'undefined' ? globalThis : this);
