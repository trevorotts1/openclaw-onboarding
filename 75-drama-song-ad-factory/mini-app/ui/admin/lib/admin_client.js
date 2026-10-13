/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN  ::  lib/admin_client.js
 * -----------------------------------------------------------------------------
 * The admin side of the pairing surface, as PURE functions: request builders,
 * local fail-closed gates, and a reader for the studio service's reply shape.
 *
 * It is a plain classic script (no imports, no bundler) that attaches one
 * object, `globalThis.DSAdmin`. The page wires it to the DOM; the test and the
 * prover call it directly.
 *
 * WHAT IT TALKS TO — U2's measured contract, 75-drama-song-ad-factory/mini-app/
 * service/README.md at 8f344a1:
 *
 *   POST /api/studio/admin/pairing-code  { admin_key, client_id }
 *        -> 201 { ok, code: "ABCD-2345", expires_in: 900 }
 *   POST /api/studio/pair                (U13's studio.py; this surface shows
 *        -> 201 { ok, client_id, key, tools }   the code, it does not call it)
 *   GET  /api/studio/options             header x-ds-key
 *        -> 200 { ok, option, line }
 *   POST /api/studio/options             { admin_key, target_client_id, option,
 *                                          approval? }
 *        -> 200 { ok, option, line };  Option 3 needs
 *           approval: { option3: true, client_name }
 *   POST /api/studio/admin/link          { admin_key, client_id }
 *        -> 200 { ok, link: "https://…/#k=…" }   (always rotates; W1-U1 link.js)
 *
 * THE ONE RULE ABOUT SECRETS: the presented key ALWAYS travels in the `x-ds-key`
 * header and NEVER in a query string, so it cannot land in a URL log. The admin
 * key goes in a POST body, which the service already accepts. No function here
 * returns a key, logs a key, or puts one in a URL — and `keyLabel` is the only
 * way the page is allowed to render one, as a character COUNT.
 * ========================================================================== */

'use strict';

(function (root) {
  // The studio's no-look-alike alphabet (service/src/keys.js PAIRING_ALPHABET,
  // table row 3.11). Duplicated here because a classic <script> cannot import
  // an ES module — and the prover re-checks it against codes the LIVE service
  // mints, so the two cannot drift apart silently.
  var PAIRING_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  var PAIRING_LENGTH = 8;
  var PAIRING_TTL_SECONDS = 900;

  // The service's own codes (service/src/*.js) — never re-spelled here.
  var AF_ADMIN_REFUSED = 'AF-DS-ADMIN-REFUSED';
  var AF_ADMIN_INVALID = 'AF-DS-ADMIN-INVALID';
  var AF_OPT_INVALID = 'AF-DS-OPT-INVALID';
  var AF_OPT_APPROVAL = 'AF-DS-OPT-APPROVAL';

  // Codes this surface owns.
  var AF_ADMIN_NOKEY = 'AF-DS-ADMIN-NOKEY';
  var AF_ADMIN_NOCLIENT = 'AF-DS-ADMIN-NOCLIENT';
  var AF_PAIR_SHAPE = 'AF-DS-PAIR-SHAPE';
  var AF_CUTOFF_NO_ROUTE = 'AF-DS-CUTOFF-NO-ROUTE';
  var AF_CUTOFF_INVALID = 'AF-DS-CUTOFF-INVALID';
  var AF_REPLY_UNREADABLE = 'AF-DS-ADMIN-UNREADABLE';

  var OPTIONS = [1, 2, 3];

  // ---------------------------------------------------------------------------
  // Pairing codes
  // ---------------------------------------------------------------------------

  function normalizeCode(input) {
    return String(input === undefined || input === null ? '' : input)
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, '');
  }

  /** "abcd2345" -> "ABCD-2345". */
  function formatCode(input) {
    var c = normalizeCode(input);
    return c.length > 4 ? c.slice(0, 4) + '-' + c.slice(4) : c;
  }

  /** null when the code is well formed, else a named refusal. */
  function pairingCodeProblem(input) {
    var c = normalizeCode(input);
    if (c.length !== PAIRING_LENGTH) {
      return { code: AF_PAIR_SHAPE, message: 'A pairing code is 8 characters, like ABCD-2345.' };
    }
    for (var i = 0; i < c.length; i++) {
      if (PAIRING_ALPHABET.indexOf(c[i]) < 0) {
        return { code: AF_PAIR_SHAPE, message: 'That code has a character the studio never mints (0, O, 1, I and L are never used).' };
      }
    }
    return null;
  }

  function checkCode(input) {
    var problem = pairingCodeProblem(input);
    if (problem) return { ok: false, code: problem.code, message: problem.message };
    return { ok: true, code: formatCode(input) };
  }

  // ---------------------------------------------------------------------------
  // The Option 3 approval gate, mirrored locally so the page can explain the
  // refusal before a round trip. The SERVICE's gate is the authority; the
  // prover proves that by sending a raw request around this function.
  // ---------------------------------------------------------------------------

  function optionApprovalProblem(option, approval) {
    if (OPTIONS.indexOf(option) < 0) {
      return { code: AF_OPT_INVALID, message: 'Option must be 1, 2 or 3.' };
    }
    if (option !== 3) return null;
    var named = approval && typeof approval.client_name === 'string' && approval.client_name.trim() !== '';
    if (!(approval && approval.option3 === true && named)) {
      return {
        code: AF_OPT_APPROVAL,
        message: "Option 3 needs Trevor's recorded approval for this client, by name.",
      };
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // Request builders. Each returns the path, the method and the BODY, so the
  // caller can never be tempted to move a key into a query string.
  // ---------------------------------------------------------------------------

  function missingKey() {
    return { ok: false, code: AF_ADMIN_NOKEY, message: 'Paste the admin key first.' };
  }

  function mintPairingCodeRequest(adminKey, clientId) {
    if (typeof adminKey !== 'string' || adminKey === '') return missingKey();
    if (typeof clientId !== 'string' || clientId.trim() === '') {
      return { ok: false, code: AF_ADMIN_NOCLIENT, message: 'A client id is required to mint a code for.' };
    }
    return {
      ok: true,
      method: 'POST',
      path: '/api/studio/admin/pairing-code',
      body: { admin_key: adminKey, client_id: clientId.trim() },
    };
  }

  /** Mint (or re-mint) a client's personal studio link. Always rotates. */
  function makeLinkRequest(adminKey, clientId) {
    if (typeof adminKey !== 'string' || adminKey === '') return missingKey();
    if (typeof clientId !== 'string' || clientId.trim() === '') {
      return { ok: false, code: AF_ADMIN_NOCLIENT, message: 'A client id is required to make a link for.' };
    }
    return {
      ok: true,
      method: 'POST',
      path: '/api/studio/admin/link',
      body: { admin_key: adminKey, client_id: clientId.trim() },
    };
  }

  function setOptionRequest(adminKey, targetClientId, option, approval) {
    if (typeof adminKey !== 'string' || adminKey === '') return missingKey();
    if (typeof targetClientId !== 'string' || targetClientId.trim() === '') {
      return { ok: false, code: AF_ADMIN_NOCLIENT, message: 'A target client id is required.' };
    }
    var problem = optionApprovalProblem(option, approval);
    if (problem) return { ok: false, code: problem.code, message: problem.message };
    var body = { admin_key: adminKey, target_client_id: targetClientId.trim(), option: option };
    if (option === 3) {
      // Rebuilt, not forwarded: nothing a caller slipped into `approval` rides along.
      body.approval = { option3: true, client_name: approval.client_name.trim() };
    }
    return { ok: true, method: 'POST', path: '/api/studio/options', body: body };
  }

  /** The key surface's probe: does this key open a client's own record? */
  function checkKeyRequest(key) {
    if (typeof key !== 'string' || key.trim() === '') {
      return { ok: false, code: AF_ADMIN_NOKEY, message: 'Paste a key to check.' };
    }
    return { ok: true, method: 'GET', path: '/api/studio/options', header: { 'x-ds-key': key.trim() } };
  }

  /** The ONLY rendering of a key this surface allows: a length, never a value. */
  function keyLabel(key) {
    var s = typeof key === 'string' ? key : '';
    if (s === '') return 'no key held';
    return 'a key is held (' + s.length + ' characters, never shown)';
  }

  // ---------------------------------------------------------------------------
  // Reading the service's reply
  // ---------------------------------------------------------------------------

  function readReply(status, json) {
    if (json && json.ok === true) return { ok: true, status: status, data: json };
    var code = json && typeof json.code === 'string' && json.code ? json.code : AF_REPLY_UNREADABLE;
    var message = json && typeof json.message === 'string' && json.message
      ? json.message
      : 'The studio did not answer, so nothing was changed.';
    return { ok: false, status: status, code: code, message: message };
  }

  // ---------------------------------------------------------------------------
  // The cutoff control
  //
  // U2's service ships NO cutoff route and NO cutoff field on the client record
  // (schema.sql, client records: client_id, created_at, option, option_set_at,
  // option_approval, timezone). So this surface can COMPUTE the cutoff and show
  // it, and it must REFUSE, BY NAME, to claim it was saved. A control that
  // said "Saved" here would be the silent lie the plan forbids.
  // ---------------------------------------------------------------------------

  function cutoffProblem(minutes, timezone) {
    if (typeof minutes !== 'number' || !isFinite(minutes) || minutes < 0 || minutes > 1439 || minutes % 1 !== 0) {
      return { code: AF_CUTOFF_INVALID, message: 'The cutoff is a whole minute of the day, 0 to 1439.' };
    }
    if (typeof timezone !== 'string' || timezone.trim() === '') {
      return { code: AF_CUTOFF_INVALID, message: 'The cutoff needs a timezone name, like America/New_York.' };
    }
    try {
      new Intl.DateTimeFormat('en-US', { timeZone: timezone.trim() }).format(new Date(0));
    } catch (e) {
      return { code: AF_CUTOFF_INVALID, message: 'That is not a timezone name the browser knows.' };
    }
    return null;
  }

  /** "6:30 PM" in the client's own zone. */
  function cutoffClock(minutes, timezone) {
    var h = Math.floor(minutes / 60);
    var m = minutes % 60;
    var stamp = new Date(Date.UTC(2020, 0, 1, h, m, 0));
    try {
      return new Intl.DateTimeFormat('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        timeZone: timezone,
      }).format(stamp);
    } catch (e) {
      return 'an unknown time';
    }
  }

  /** The line the operator reads. Before the cutoff, work starts; after, it waits. */
  function cutoffLine(minutes, timezone) {
    return 'New orders stop starting at ' + cutoffClock(minutes, timezone) + ' (' + timezone + ').';
  }

  /**
   * @returns {{ok:true, before:boolean, line:string, clock:string}}
   *        | {{ok:false, code:string, message:string}}  (a malformed cutoff)
   */
  function cutoffVerdict(minutes, timezone, nowMs) {
    var problem = cutoffProblem(minutes, timezone);
    if (problem) return { ok: false, code: problem.code, message: problem.message };
    var clock = cutoffClock(minutes, timezone);
    var here = localMinutes(minutes, timezone, nowMs);
    return {
      ok: true,
      before: here < minutes,
      clock: clock,
      line: cutoffLine(minutes, timezone),
    };
  }

  /** The minute-of-day it is right now in the client's zone. */
  function localMinutes(minutes, timezone, nowMs) {
    var parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(new Date(nowMs));
    var h = 0;
    var m = 0;
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === 'hour') h = parseInt(parts[i].value, 10) % 24;
      if (parts[i].type === 'minute') m = parseInt(parts[i].value, 10);
    }
    return h * 60 + m;
  }

  /**
   * There is no route to write a cutoff, so this refuses by name. It never
   * returns ok, and it says exactly what is missing and what the upgrade is.
   */
  function setCutoffRequest(minutes, timezone) {
    var problem = cutoffProblem(minutes, timezone);
    if (problem) return { ok: false, code: problem.code, message: problem.message };
    return {
      ok: false,
      code: AF_CUTOFF_NO_ROUTE,
      message: 'Version 0 has no cutoff route on the studio service, so nothing was saved. '
        + 'The upgrade path is POST /api/studio/admin/cutoff { admin_key, client_id, cutoff_minutes, timezone }.',
    };
  }

  /** Cutting a key off needs a revoke route the service does not have yet. */
  function revokeKeyRequest() {
    return {
      ok: false,
      code: AF_CUTOFF_NO_ROUTE,
      message: 'Version 0 has no revoke route on the studio service, so no key was cut off. '
        + 'The upgrade path is POST /api/studio/admin/revoke { admin_key, fingerprint }.',
    };
  }

  root.DSAdmin = {
    PAIRING_ALPHABET: PAIRING_ALPHABET,
    PAIRING_LENGTH: PAIRING_LENGTH,
    PAIRING_TTL_SECONDS: PAIRING_TTL_SECONDS,
    OPTIONS: OPTIONS,
    normalizeCode: normalizeCode,
    formatCode: formatCode,
    pairingCodeProblem: pairingCodeProblem,
    checkCode: checkCode,
    optionApprovalProblem: optionApprovalProblem,
    mintPairingCodeRequest: mintPairingCodeRequest,
    makeLinkRequest: makeLinkRequest,
    setOptionRequest: setOptionRequest,
    checkKeyRequest: checkKeyRequest,
    revokeKeyRequest: revokeKeyRequest,
    keyLabel: keyLabel,
    readReply: readReply,
    cutoffVerdict: cutoffVerdict,
    cutoffLine: cutoffLine,
    cutoffClock: cutoffClock,
    setCutoffRequest: setCutoffRequest,
    AF_ADMIN_REFUSED: AF_ADMIN_REFUSED,
    AF_ADMIN_INVALID: AF_ADMIN_INVALID,
    AF_OPT_INVALID: AF_OPT_INVALID,
    AF_OPT_APPROVAL: AF_OPT_APPROVAL,
    AF_ADMIN_NOKEY: AF_ADMIN_NOKEY,
    AF_ADMIN_NOCLIENT: AF_ADMIN_NOCLIENT,
    AF_PAIR_SHAPE: AF_PAIR_SHAPE,
    AF_CUTOFF_NO_ROUTE: AF_CUTOFF_NO_ROUTE,
    AF_CUTOFF_INVALID: AF_CUTOFF_INVALID,
    AF_REPLY_UNREADABLE: AF_REPLY_UNREADABLE,
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
