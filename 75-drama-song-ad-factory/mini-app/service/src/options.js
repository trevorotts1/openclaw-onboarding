// ============================================================================
// options.js — Drama Studio service: the options surface (U2)
//
// Joint plan section 3.10. The option is chosen PER CLIENT and lives in the
// client's studio record. Option 3 can only be set when Trevor's approval for
// that client is recorded — by name, one client at a time (decision 8).
//
// The studio page always shows the option and the real wait. These four strings
// are copied verbatim from the approved plan; U3 renders them, it does not
// reword them.
//
//   1  "Your crew starts when you open Claude Code on your computer. Last
//       check-in: 3 hours ago."
//   2  "Your crew is watching. Orders start within about 2 minutes while your
//       computer is on. Last check-in: 1 minute ago."
//   3  "Your crew starts automatically within about 2 minutes while your
//       computer is on and awake. Last check-in: 2 minutes ago."
//   stale (any option, 30 minutes with an order waiting)
//      "Your computer has not checked in since 2:14 PM. Your order is safe and
//       starts when it is back." plus ONE quiet line in the operator inbox.
//
// PURE, apart from nothing: no bindings, no I/O, no clock.
// ============================================================================

'use strict';

export const OPTIONS = [1, 2, 3];
export const DEFAULT_OPTION = 1;
export const STALE_AFTER_MS = 30 * 60 * 1000;

export const AF_OPT_INVALID = 'AF-DS-OPT-INVALID';
export const AF_OPT_APPROVAL = 'AF-DS-OPT-APPROVAL';

const PENNY = {
  1: 'Your crew starts when you open Claude Code on your computer.',
  2: 'Your crew is watching. Orders start within about 2 minutes while your computer is on.',
  3: 'Your crew starts automatically within about 2 minutes while your computer is on and awake.',
};

/** "3 hours ago" / "1 minute ago" / "just now" / "not yet". */
export function ageText(nowMs, sinceMs) {
  if (typeof sinceMs !== 'number') return 'not yet';
  const mins = Math.floor((nowMs - sinceMs) / 60000);
  if (mins < 1) return 'just now';
  if (mins === 1) return '1 minute ago';
  if (mins < 60) return `${mins} minutes ago`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return '1 hour ago';
  if (hours < 24) return `${hours} hours ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

/** CLOCK — "2:14 PM". Uses the client's own timezone when the record stores
 *  one, otherwise UTC (api), so the string never implies a local time it does
 *  not know. ponytail: add `timezone` to the client record when U12's admin
 *  page collects it. */
export function clockText(ms, timezone) {
  if (typeof ms !== 'number') return 'unknown';
  try {
    return new Intl.DateTimeFormat('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      timeZone: timezone || 'UTC',
    }).format(new Date(ms));
  } catch {
    return new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(new Date(ms));
  }
}

/** The line the studio page shows under the option. */
export function optionLine(record, nowMs) {
  const option = OPTIONS.includes(record && record.option) ? record.option : DEFAULT_OPTION;
  const last = record ? record.last_check_in : null;
  return `${PENNY[option]} Last check-in: ${ageText(nowMs, last)}.`;
}

/**
 * Option 3 is opt-in per client and needs a recorded approval naming the
 * client. Everything else is refused with a named code, never ignored.
 */
export function setOption(record, option, { nowMs, approval } = {}) {
  if (!OPTIONS.includes(option)) {
    return { ok: false, code: AF_OPT_INVALID, message: 'option must be 1, 2 or 3.' };
  }
  if (option === 3) {
    const approved = approval && approval.option3 === true && typeof approval.client_name === 'string' && approval.client_name;
    if (!approved) {
      return {
        ok: false,
        code: AF_OPT_APPROVAL,
        message: 'Option 3 needs Trevor\'s recorded approval for this client.',
      };
    }
  }
  return {
    ok: true,
    record: { ...record, option, option_set_at: nowMs, option_approval: option === 3 ? approval : null },
  };
}

/**
 * The 30-minute no-check-in rule (section 3.10, item 1 of section 3.10A): with
 * an order waiting, the page gets a quiet explanation and the operator inbox
 * gets ONE line — and that one line is subject to rule 3 (one per client per
 * day), which lifecycle.writeOperatorRecord enforces.
 */
export function staleVerdict({ record, lastCheckMs, hasWaitingOrder, nowMs }) {
  if (!hasWaitingOrder) return { stale: false, page_line: null, operator_line: null };
  if (typeof lastCheckMs === 'number' && nowMs - lastCheckMs < STALE_AFTER_MS) {
    return { stale: false, page_line: null, operator_line: null };
  }
  const clock = clockText(lastCheckMs, record && record.timezone);
  return {
    stale: true,
    page_line: `Your computer has not checked in since ${clock}. Your order is safe and starts when it is back.`,
    operator_line: `Computer has not checked in since ${clock} with an order waiting`,
  };
}
