/* =============================================================================
 * DRAMA STUDIO MINI-APP :: U12 — PAIRING / ADMIN  ::  lib/admin_page.js
 * -----------------------------------------------------------------------------
 * The page wiring, moved out of index.html. The studio service serves every
 * page with `Content-Security-Policy: script-src 'self'`, so an inline <script>
 * block is refused by the browser and the page never runs; the wiring lives in
 * this file instead and the page loads it with an absolute <script src>.
 *
 * All judgement lives in lib/admin_client.js; this file only moves values
 * between the DOM and that module, and renders what came back.
 * ========================================================================== */

(function () {
  'use strict';
  var A = globalThis.DSAdmin;
  var Q = globalThis.DSQR;

  var studioMeta = document.querySelector('meta[name="studio-origin"]');
  var STUDIO = (studioMeta && studioMeta.content) || '';

  function el(id) { return document.getElementById(id); }
  function say(statusId, errorId, text, isError) {
    el(statusId).textContent = isError ? '' : text;
    el(errorId).textContent = isError ? text : '';
  }
  /** POST a JSON body. The key is inside the body, never the URL. */
  function sendPost(path, body) {
    return fetch(STUDIO + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'omit',
      cache: 'no-store',
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (json) {
        return A.readReply(res.status, json);
      });
    });
  }

  /** GET with the key in the x-ds-key header. Never a query string. */
  function sendKeyedGet(path, key) {
    return fetch(STUDIO + path, {
      method: 'GET',
      headers: { 'x-ds-key': key },
      credentials: 'omit',
      cache: 'no-store',
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (json) {
        return A.readReply(res.status, json);
      });
    });
  }

  // ---- 1. pairing -------------------------------------------------------
  var countdown = null;

  function stopCountdown() {
    if (countdown) { clearInterval(countdown); countdown = null; }
  }

  el('mint').addEventListener('click', function () {
    stopCountdown();
    var built = A.mintPairingCodeRequest(el('admin-key').value, el('pair-client').value);
    if (!built.ok) {
      el('pairing-result').hidden = true;
      say('mint-status', 'mint-error', built.code + ' — ' + built.message, true);
      return;
    }
    say('mint-status', 'mint-error', 'Asking the studio…', false);
    sendPost(built.path, built.body).then(function (reply) {
      if (!reply.ok) {
        el('pairing-result').hidden = true;
        say('mint-status', 'mint-error', reply.code + ' — ' + reply.message, true);
        return;
      }
      showCode(reply.data.code, reply.data.expires_in);
      say('mint-status', 'mint-error', 'Code minted for ' + built.body.client_id + '.', false);
    }).catch(function () {
      el('pairing-result').hidden = true;
      say('mint-status', 'mint-error', 'The studio could not be reached, so no code was minted.', true);
    });
  });

  function showCode(code, expiresIn) {
    var checked = A.checkCode(code);
    if (!checked.ok) {
      el('pairing-result').hidden = true;
      say('mint-status', 'mint-error', checked.code + ' — the studio returned a code this page does not recognise.', true);
      return;
    }
    el('code-text').textContent = checked.code;
    var qr = Q.encode(checked.code, { level: 'M' });
    if (!qr.ok) {
      el('qr-holder').innerHTML = '';
      el('qr-holder').textContent = 'The square could not be drawn; read the code out instead.';
    } else {
      el('qr-holder').innerHTML = Q.toSvg(qr, { label: 'Pairing code ' + checked.code, width: '168', height: '168' });
    }
    el('pairing-result').hidden = false;

    var left = typeof expiresIn === 'number' ? expiresIn : A.PAIRING_TTL_SECONDS;
    var tick = function () {
      if (left <= 0) {
        el('code-expiry').textContent = 'This code has expired. Mint another one.';
        stopCountdown();
        return;
      }
      var m = Math.floor(left / 60);
      var s = left % 60;
      el('code-expiry').textContent = 'Expires in ' + m + ':' + (s < 10 ? '0' : '') + s + ', or when it is used once.';
      left -= 1;
    };
    tick();
    countdown = setInterval(tick, 1000);
  }

  // ---- 2. key surface ---------------------------------------------------
  el('check').addEventListener('click', function () {
    var built = A.checkKeyRequest(el('check-key').value);
    if (!built.ok) {
      say('key-status', 'key-error', built.code + ' — ' + built.message, true);
      return;
    }
    say('key-status', 'key-error', 'Asking the studio…', false);
    sendKeyedGet(built.path, built.header['x-ds-key']).then(function (reply) {
      if (!reply.ok) {
        say('key-status', 'key-error', reply.code + ' — ' + reply.message, true);
        return;
      }
      say('key-status', 'key-error', 'Accepted. ' + A.keyLabel(built.header['x-ds-key']) + '. Option ' + reply.data.option + ': ' + reply.data.line, false);
    }).catch(function () {
      say('key-status', 'key-error', 'The studio could not be reached.', true);
    });
  });

  // ---- 2b. cutting a key off (U-Z12) ------------------------------------
  // The studio names a client and a kind, never a key. Two buttons, one per
  // kind, so the operator cannot cut a computer's key by picking the wrong
  // word from a list.
  function cutOffKey(kind) {
    var built = A.revokeKeyRequest(el('admin-key').value, el('revoke-client').value, kind);
    if (!built.ok) {
      say('revoke-status', 'revoke-error', built.code + ' — ' + built.message, true);
      return;
    }
    say('revoke-status', 'revoke-error', 'Asking the studio…', false);
    sendPost(built.path, built.body).then(function (reply) {
      if (!reply.ok) {
        say('revoke-status', 'revoke-error', reply.code + ' — ' + reply.message, true);
        return;
      }
      var cut = typeof reply.data.revoked === 'number' ? reply.data.revoked : 0;
      say('revoke-status', 'revoke-error', cut === 0
        ? 'No ' + kind + ' key of ' + built.body.client_id + ' was active, so nothing was cut off.'
        : cut + ' ' + kind + ' key' + (cut === 1 ? '' : 's') + ' of ' + built.body.client_id
          + ' cut off. It cannot check in again.', false);
    }).catch(function () {
      say('revoke-status', 'revoke-error', 'The studio could not be reached, so no key was cut off.', true);
    });
  }

  el('revoke-machine').addEventListener('click', function () { cutOffKey('machine'); });
  el('revoke-box').addEventListener('click', function () { cutOffKey('box'); });

  // ---- 3. options -------------------------------------------------------
  function optionValue() {
    var picked = document.querySelector('input[name="option"]:checked');
    return picked ? parseInt(picked.value, 10) : null;
  }

  function syncApproval() {
    var isThree = optionValue() === 3;
    el('approval-block').hidden = !isThree;
    el('opt-3').setAttribute('aria-expanded', isThree ? 'true' : 'false');
  }
  for (var i = 0; i < 3; i++) document.querySelectorAll('input[name="option"]')[i].addEventListener('change', syncApproval);
  syncApproval();

  el('set-option').addEventListener('click', function () {
    var option = optionValue();
    var approval = option === 3
      ? { option3: el('approval-given').checked, client_name: el('approval-name').value }
      : undefined;
    var built = A.setOptionRequest(el('admin-key').value, el('option-client').value, option, approval);
    if (!built.ok) {
      say('option-status', 'option-error', built.code + ' — ' + built.message, true);
      return;
    }
    say('option-status', 'option-error', 'Asking the studio…', false);
    sendPost(built.path, built.body).then(function (reply) {
      if (!reply.ok) {
        say('option-status', 'option-error', reply.code + ' — ' + reply.message, true);
        return;
      }
      say('option-status', 'option-error', 'Option ' + reply.data.option + ' is set. ' + reply.data.line, false);
    }).catch(function () {
      say('option-status', 'option-error', 'The studio could not be reached, so nothing was changed.', true);
    });
  });

  // ---- 4. cutoff --------------------------------------------------------
  function cutoffMinutes() {
    var raw = el('cutoff-time').value;
    if (!/^\d{2}:\d{2}$/.test(raw)) return NaN;
    return parseInt(raw.slice(0, 2), 10) * 60 + parseInt(raw.slice(3, 5), 10);
  }

  el('compute-cutoff').addEventListener('click', function () {
    var verdict = A.cutoffVerdict(cutoffMinutes(), el('cutoff-zone').value.trim(), Date.now());
    if (!verdict.ok) {
      say('cutoff-status', 'cutoff-error', verdict.code + ' — ' + verdict.message, true);
      return;
    }
    say('cutoff-status', 'cutoff-error',
      verdict.line + ' Right now the studio is ' + (verdict.before ? 'before' : 'past') + ' that cutoff.', false);
  });

  el('save-cutoff').addEventListener('click', function () {
    var saved = A.setCutoffRequest(cutoffMinutes(), el('cutoff-zone').value.trim());
    say('cutoff-status', 'cutoff-error', saved.code + ' — ' + saved.message, true);
  });

  // ---- 5. personal link --------------------------------------------------
  el('make-link').addEventListener('click', function () {
    var built = A.makeLinkRequest(el('admin-key').value, el('link-client').value);
    if (!built.ok) {
      el('link-result').hidden = true;
      say('link-status', 'link-error', built.code + ' — ' + built.message, true);
      return;
    }
    say('link-status', 'link-error', 'Asking the studio…', false);
    sendPost(built.path, built.body).then(function (reply) {
      var link = reply.ok && typeof reply.data.link === 'string' ? reply.data.link : '';
      if (link === '') {
        el('link-result').hidden = true;
        say('link-status', 'link-error', reply.ok
          ? A.AF_REPLY_UNREADABLE + ' — the studio made no link, so nothing is shown.'
          : reply.code + ' — ' + reply.message, true);
        return;
      }
      showLink(link);
      say('link-status', 'link-error', 'A personal link was made for ' + built.body.client_id + '.', false);
    }).catch(function () {
      el('link-result').hidden = true;
      say('link-status', 'link-error', 'The studio could not be reached, so no link was made.', true);
    });
  });

  function showLink(link) {
    el('link-text').textContent = link;
    // A link is long, so the encoder gets the level with the most room (L).
    var qr = Q.encode(link, { level: 'L' });
    if (!qr.ok) {
      el('link-qr-holder').innerHTML = '';
      el('link-qr-holder').textContent = 'The square could not be drawn; copy the link instead.';
    } else {
      el('link-qr-holder').innerHTML = Q.toSvg(qr, { label: 'Personal link', width: '168', height: '168' });
    }
    el('link-result').hidden = false;
  }
})();
