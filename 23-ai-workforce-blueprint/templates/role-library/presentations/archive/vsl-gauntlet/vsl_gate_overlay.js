/*
 * vsl_gate_overlay.js
 * ============================================================================
 * The VSL email/phone GATE controller — inline, self-contained, brand-colored.
 * (Presentation Collateral Gauntlet, Wave 3 — DESIGN-OPUS §6.)
 *
 * WHAT IT DOES
 *   (a) When the video's currentTime reaches the adaptive gate_time
 *       (clamp(R + 20s, 3:00, 8:00) — see gate_time_model.py), the controller
 *       PAUSES the video and SHOWS the gate overlay.
 *   (b) The overlay carries the REAL GHL Skill-44 form embed (verbatim, no SRI)
 *       with three REQUIRED fields: email, first name, cell phone.
 *   (c) On form submit success the controller RESUMES the video, hides the
 *       overlay, and un-scopes seeking.
 *   (d) SEEK-SCOPE: while the gate is armed the controller clamps seeking to
 *       [3:00, gate_time] — the viewer can neither rewind before the gate
 *       window nor skip past the gate without submitting, and the controller
 *       never seeks the video outside the [3:00, 8:00] gate window.
 *   (e) BRAND-COLORED: all styles are injected under ONE scoped <style> block
 *       that targets only elements carrying [data-zhc-vsl-gate] inside the gate
 *       container. No global stylesheet is touched.
 *
 * ISOLATION CONTRACT (never touches any other element on the page)
 *   * All DOM queries are scoped to ONE container element found by
 *     document.getElementById('zhc-vsl-gate-<slug>'). No other getElementById
 *     and no document.querySelectorAll is called against the page.
 *   * The injected stylesheet is scoped under '#<containerId> [data-zhc-vsl-gate]'.
 *   * The only window objects used are the namespaced, this-snippet-owned
 *     window.__zhcVslGateConfig (read) and window.__zhcVslGate (written).
 *   * No MutationObserver on the document, no window resize/scroll listeners.
 *
 * INTEGRATION CONTRACT (how the HTML page wires it)
 *   1. HTML structure the page must provide (the JS only toggles/animates):
 *
 *        <div id="zhc-vsl-gate-<slug>"           <- container (JS root)
 *             data-zhc-gate-time="420"            <- optional override, seconds
 *             data-zhc-success-class="is-success" <- optional: release when this
 *                                                    class appears on the overlay
 *             data-zhc-slug="<slug>">
 *           <video data-zhc-vsl-gate="video" src="..."></video>
 *           <div data-zhc-vsl-gate="overlay" role="dialog" aria-modal="true">
 *             <div data-zhc-vsl-gate="card">
 *               <!-- GHL Skill-44 form embed snippet: VERBATIM, NO SRI -->
 *               <script src="https://.../form_embed.js"></script>
 *             </div>
 *           </div>
 *        </div>
 *
 *      The video element and overlay must be descendants of the container and
 *      carry the data-zhc-vsl-gate="video" / ="overlay" markers.
 *
 *   2. Config: set window.__zhcVslGateConfig BEFORE this script runs, OR put
 *      data-zhc-gate-time on the container (the data attribute wins).
 *      Recognised keys:
 *        gateTime  : number (seconds). Default 480 (8:00, fail-closed).
 *        minWindow : number (seconds). Default 180 (3:00).
 *        maxWindow : number (seconds). Default 480 (8:00).
 *        slug      : string used to namespace ids (default "vsl").
 *        brand     : { primary, accent, surface, text, muted, border, focus }.
 *
 *   3. Submit success: when the GHL form submits successfully the page MUST
 *      dispatch a CustomEvent on the container:
 *
 *        container.dispatchEvent(new CustomEvent('zhc:vsl:gate:submit-success'));
 *
 *      GHL's own form embed fires its success state; the page relays it to the
 *      controller (the controller is decoupled from GHL's iframe DOM). As a
 *      convenience the controller ALSO releases when the class named in
 *      data-zhc-success-class appears on the overlay (MutationObserver scoped
 *      to the overlay only). Use one or the other; the CustomEvent is canonical.
 *
 *   4. Public handle: after init, window.__zhcVslGate exposes
 *      { ready, container, video, isArmed, isSubmitted, fire, release, destroy }.
 *
 * ============================================================================
 */
(function () {
  'use strict';

  // ---- config -------------------------------------------------------------
  var DEFAULTS = {
    gateTime: 480,   // 8:00 — fail-closed default (matches gate_time_model.py)
    minWindow: 180,  // 3:00 — floor of the gate window
    maxWindow: 480,  // 8:00 — ceiling of the gate window
    slug: 'vsl',
    brand: {
      primary: '#12263A',   // deep navy — ZHC fallback brand primary
      accent:  '#F5821F',   // amber/orange accent — fallback
      surface: '#FFFFFF',
      text:    '#12263A',
      muted:   '#5B6B7C',
      border:  '#CBD5E1',
      focus:   '#F5821F'
    }
  };

  function merge(base, over) {
    var out = {};
    var k;
    for (k in base) {
      if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = base[k];
    }
    if (over && typeof over === 'object') {
      for (k in over) {
        if (Object.prototype.hasOwnProperty.call(over, k)) out[k] = over[k];
      }
    }
    return out;
  }

  function num(v, fallback) {
    var n = Number(v);
    return isFinite(n) && n >= 0 ? n : fallback;
  }

  function resolveConfig() {
    var cfg = merge({}, DEFAULTS);
    var globalCfg = (typeof window !== 'undefined') ? window.__zhcVslGateConfig : null;
    if (globalCfg && typeof globalCfg === 'object') {
      if (globalCfg.gateTime != null) cfg.gateTime = num(globalCfg.gateTime, cfg.gateTime);
      if (globalCfg.minWindow != null) cfg.minWindow = num(globalCfg.minWindow, cfg.minWindow);
      if (globalCfg.maxWindow != null) cfg.maxWindow = num(globalCfg.maxWindow, cfg.maxWindow);
      if (globalCfg.slug) cfg.slug = String(globalCfg.slug);
      if (globalCfg.brand && typeof globalCfg.brand === 'object') {
        cfg.brand = merge(cfg.brand, globalCfg.brand);
      }
    }
    return cfg;
  }

  function clampToWindow(t, cfg) {
    return Math.min(cfg.maxWindow, Math.max(cfg.minWindow, t));
  }

  function init() {
    var cfg = resolveConfig();
    if (typeof document === 'undefined') return;

    var container = document.getElementById('zhc-vsl-gate-' + cfg.slug);

    // Fail-closed: without the container we do nothing and touch nothing.
    if (!container) {
      if (typeof window !== 'undefined') {
        window.__zhcVslGate = { ready: false, error: 'container not found: #zhc-vsl-gate-' + cfg.slug };
      }
      return;
    }

    // The data attribute on the container wins over the config object.
    var dataGate = container.getAttribute('data-zhc-gate-time');
    if (dataGate) cfg.gateTime = num(dataGate, cfg.gateTime);

    // Clamp the gate time itself into the legal [3:00, 8:00] window.
    cfg.gateTime = clampToWindow(cfg.gateTime, cfg);
    var successClass = container.getAttribute('data-zhc-success-class') || '';

    var video = container.querySelector('[data-zhc-vsl-gate="video"]');
    var overlay = container.querySelector('[data-zhc-vsl-gate="overlay"]');
    if (!video || !overlay) {
      if (typeof window !== 'undefined') {
        window.__zhcVslGate = { ready: false, error: 'video or overlay element missing' };
      }
      return;
    }

    injectStyles(container, cfg);

    var state = { fired: false, submitted: false, armed: false };
    var observer = null;

    // ---- seek-scope --------------------------------------------------------
    // While armed: clamp currentTime to [minWindow, gateTime] so the viewer
    // can neither rewind before the gate window nor skip past the gate. This
    // never seeks the video outside [3:00, 8:00].
    function scopeSeek() {
      if (!state.armed) return;
      var t = video.currentTime;
      var lo = cfg.minWindow;
      var hi = cfg.gateTime;
      var clamped = Math.min(hi, Math.max(lo, t));
      if (Math.abs(clamped - t) > 0.05) {
        video.currentTime = clamped;
      }
    }

    // ---- gate firing -------------------------------------------------------
    function fireGate() {
      if (state.fired || state.submitted) return;
      state.fired = true;
      state.armed = true;
      try { video.pause(); } catch (e) { /* noop */ }
      overlay.style.display = 'flex';
      container.setAttribute('data-zhc-vsl-gate-state', 'armed');
      startSuccessWatcher();
    }

    function release() {
      if (!state.armed && state.submitted) return;
      state.submitted = true;
      state.armed = false;
      overlay.style.display = 'none';
      container.setAttribute('data-zhc-vsl-gate-state', 'submitted');
      stopSuccessWatcher();
      try {
        var p = video.play();
        if (p && typeof p.catch === 'function') p.catch(function () { /* noop */ });
      } catch (e) { /* noop */ }
    }

    function onTimeUpdate() {
      if (state.submitted) return;
      if (!state.fired && video.currentTime >= cfg.gateTime) {
        fireGate();
        return;
      }
      if (state.armed) scopeSeek();
    }

    function onSeek() {
      if (state.armed) scopeSeek();
    }

    // ---- success watchers (submit relay) -----------------------------------
    function startSuccessWatcher() {
      if (!successClass) return;
      if (typeof MutationObserver === 'undefined') return;
      observer = new MutationObserver(function () {
        if (overlay.className.indexOf(successClass) !== -1) release();
      });
      observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });
    }

    function stopSuccessWatcher() {
      if (observer) {
        observer.disconnect();
        observer = null;
      }
    }

    // ---- wiring ------------------------------------------------------------
    video.addEventListener('timeupdate', onTimeUpdate);
    video.addEventListener('seeking', onSeek);
    video.addEventListener('seeked', onSeek);
    container.addEventListener('zhc:vsl:gate:submit-success', release);

    // If the video is already past the gate when this script initialises
    // (autoplay / resumed session), fire immediately.
    if (video.readyState >= 1 && video.currentTime >= cfg.gateTime && !state.submitted) {
      fireGate();
    }

    // Public handle.
    if (typeof window !== 'undefined') {
      window.__zhcVslGate = {
        ready: true,
        container: container,
        video: video,
        get isArmed() { return state.armed; },
        get isSubmitted() { return state.submitted; },
        fire: fireGate,
        release: release,
        destroy: function () {
          video.removeEventListener('timeupdate', onTimeUpdate);
          video.removeEventListener('seeking', onSeek);
          video.removeEventListener('seeked', onSeek);
          container.removeEventListener('zhc:vsl:gate:submit-success', release);
          stopSuccessWatcher();
        }
      };
    }
  }

  // ---- scoped, brand-colored styles ---------------------------------------
  function injectStyles(container, cfg) {
    var b = cfg.brand;
    var styleId = 'zhc-vsl-gate-style-' + cfg.slug;
    if (document.getElementById(styleId)) return; // idempotent

    var css = [
      '#' + container.id + '{position:relative;width:100%;aspect-ratio:16/9;background:' + b.primary + ';}',
      '#' + container.id + ' [data-zhc-vsl-gate="video"]{display:block;width:100%;height:100%;object-fit:contain;background:' + b.primary + ';}',
      '#' + container.id + ' [data-zhc-vsl-gate="overlay"]{position:absolute;top:0;left:0;right:0;bottom:0;z-index:20;display:none;align-items:center;justify-content:center;padding:24px;box-sizing:border-box;background:rgba(18,38,58,0.82);}',
      '#' + container.id + ' [data-zhc-vsl-gate="card"]{background:' + b.surface + ';color:' + b.text + ';border:1px solid ' + b.border + ';border-top:6px solid ' + b.accent + ';border-radius:12px;max-width:420px;width:100%;padding:28px;box-shadow:0 18px 48px rgba(18,38,58,0.35);box-sizing:border-box;font-family:inherit;}',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] input[type="email"],',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] input[type="text"],',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] input[type="tel"],',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] input{width:100%;padding:12px 14px;margin:6px 0 12px;border:1px solid ' + b.border + ';border-radius:8px;font-size:15px;color:' + b.text + ';background:' + b.surface + ';box-sizing:border-box;outline:none;}',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] input:focus{border-color:' + b.focus + ';box-shadow:0 0 0 3px rgba(245,130,31,0.18);}',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] button,',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] [type="submit"]{width:100%;padding:14px 16px;border:0;border-radius:8px;background:' + b.accent + ';color:#FFFFFF;font-size:16px;font-weight:700;cursor:pointer;margin-top:8px;}',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] button:hover,',
      '#' + container.id + ' [data-zhc-vsl-gate="card"] [type="submit"]:hover{filter:brightness(1.06);}',
      '#' + container.id + ' [data-zhc-vsl-gate="privacy"]{margin-top:12px;font-size:12px;color:' + b.muted + ';text-align:center;}'
    ].join('\n');

    var styleEl = document.createElement('style');
    styleEl.id = styleId;
    styleEl.setAttribute('data-zhc-vsl-gate', 'style');
    styleEl.appendChild(document.createTextNode(css));
    container.appendChild(styleEl);
  }

  // ---- boot ---------------------------------------------------------------
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
