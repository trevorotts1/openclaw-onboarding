/*
 * ZHC Pixel (Feature 49) — per-client visitor-signal pixel.
 * ----------------------------------------------------------------------------
 * TEMPLATE. This file ships with placeholders. The generator
 * scripts/27-render-pixel-js.sh renders a per-client copy by substituting:
 *
 *   __ZHC_PIXEL_ENDPOINT__   the client's OWN tunnel ingest URL, e.g.
 *                            https://pixel.<CLIENT_DOMAIN>/hooks/pixel-visitor-signal
 *   __ZHC_PIXEL_SITE_ID__    a per-client unique site id, e.g. <SITE_ID>
 *   __ZHC_PIXEL_AGENT_ID__   the Pixel Concierge agent id, e.g. <AGENT_ID>
 *
 * The hooks bearer TOKEN is deliberately NOT a placeholder here — it is never baked
 * into the browser bundle. The edge worker attaches it server-side, or the gateway
 * requires it at ingress (see protocols/zhc-pixel-protocol.md "Token handling").
 *
 * ARCHITECTURE: every client gets THEIR OWN private pixel that POSTs visitor
 * signals to THEIR OpenClaw via THEIR existing Cloudflare tunnel. There is NO
 * shared collector service and NO third-party analytics endpoint.
 *
 * PRIVACY (non-negotiable, all enforced below):
 *   - Respects Do-Not-Track: if navigator.doNotTrack=='1' (or msDoNotTrack/
 *     window.doNotTrack), NO fingerprint is computed and NO cookie is set.
 *   - GDPR: nothing is sent until consent is granted (banner deferral). The host
 *     page (or this script's built-in banner) calls window.ZHCPixel.grantConsent().
 *   - CCPA: window.ZHCPixel.optOut() permanently disables + clears local state.
 *   - Data deletion: optOut() also POSTs a `delete_request` event so the client's
 *     OpenClaw can purge stored signals for this visitor id.
 *
 * The pixel is anonymous-but-persistent: it assigns a random first-party visitor
 * id (NOT a name, NOT an email). Identity is resolved server-side ONLY by
 * first-party form linkage — see protocols/zhc-pixel-protocol.md "Identification".
 *
 * NO personal data is hardcoded in this template (UNIVERSAL skill).
 */
(function () {
  "use strict";

  // --------------------------------------------------------------------------
  // Rendered config (placeholders replaced by 27-render-pixel-js.sh)
  // --------------------------------------------------------------------------
  var ENDPOINT = "__ZHC_PIXEL_ENDPOINT__";
  var SITE_ID = "__ZHC_PIXEL_SITE_ID__";
  var AGENT_ID = "__ZHC_PIXEL_AGENT_ID__";

  // Tunables (safe defaults; the generator may override via a second pass).
  var BATCH_INTERVAL_MS = 5000; // flush buffered events every 5s
  var MAX_BATCH = 25; // hard cap on events per POST
  var SCROLL_THROTTLE_MS = 750;
  var COOKIE_NAME = "zhc_vid";
  var COOKIE_DAYS = 365;
  var CONSENT_KEY = "zhc_consent"; // localStorage: "granted" | "denied"
  var STORAGE_PREFIX = "zhc_";

  // --------------------------------------------------------------------------
  // Do-Not-Track gate — the FIRST thing we check. If DNT is on we do nothing
  // that could fingerprint or persist. We still expose the public API so a
  // consent banner can call it, but every send is a no-op.
  // --------------------------------------------------------------------------
  function dntEnabled() {
    var dnt =
      navigator.doNotTrack ||
      window.doNotTrack ||
      navigator.msDoNotTrack;
    return dnt === "1" || dnt === "yes" || dnt === true;
  }
  var DNT = dntEnabled();

  // --------------------------------------------------------------------------
  // Consent state (GDPR). Default is NOT granted — nothing leaves the browser
  // until grantConsent() is called (by the host page's CMP or our banner).
  // --------------------------------------------------------------------------
  function readConsent() {
    try {
      return window.localStorage.getItem(CONSENT_KEY);
    } catch (e) {
      return null;
    }
  }
  function writeConsent(v) {
    try {
      window.localStorage.setItem(CONSENT_KEY, v);
    } catch (e) {
      /* storage blocked — treat as not granted */
    }
  }
  function consentGranted() {
    return readConsent() === "granted";
  }

  // --------------------------------------------------------------------------
  // First-party cookie + visitor id (anonymous-but-persistent).
  // --------------------------------------------------------------------------
  function readCookie(name) {
    var m = document.cookie.match(
      "(?:^|; )" + name.replace(/([.$?*|{}()\[\]\\\/+^])/g, "\\$1") + "=([^;]*)"
    );
    return m ? decodeURIComponent(m[1]) : null;
  }
  function writeCookie(name, value, days) {
    var d = new Date();
    d.setTime(d.getTime() + days * 864e5);
    document.cookie =
      name +
      "=" +
      encodeURIComponent(value) +
      "; expires=" +
      d.toUTCString() +
      "; path=/; SameSite=Lax";
  }
  function randomId() {
    // Anonymous: random, NOT derived from any personal attribute.
    if (window.crypto && window.crypto.getRandomValues) {
      var a = new Uint8Array(16);
      window.crypto.getRandomValues(a);
      return Array.prototype.map
        .call(a, function (b) {
          return ("0" + b.toString(16)).slice(-2);
        })
        .join("");
    }
    return (
      Date.now().toString(36) + Math.random().toString(36).slice(2, 12)
    );
  }
  function getVisitorId() {
    if (DNT) return null; // never persist under DNT
    var vid = readCookie(COOKIE_NAME);
    if (!vid) {
      vid = randomId();
      writeCookie(COOKIE_NAME, vid, COOKIE_DAYS);
    }
    return vid;
  }

  // --------------------------------------------------------------------------
  // Lightweight, privacy-bounded browser fingerprint. NOT a precise tracker;
  // a stability hint to help the cookie survive clears. Skipped entirely under
  // DNT. Never includes IP (that is resolved server-side at the edge if at all).
  // --------------------------------------------------------------------------
  function softFingerprint() {
    if (DNT) return null;
    try {
      var parts = [
        navigator.userAgent || "",
        navigator.language || "",
        (window.screen ? screen.width + "x" + screen.height : ""),
        (window.screen ? screen.colorDepth : ""),
        new Date().getTimezoneOffset(),
        navigator.hardwareConcurrency || "",
        navigator.platform || ""
      ].join("|");
      // djb2 hash → short, non-reversible.
      var h = 5381;
      for (var i = 0; i < parts.length; i++) {
        h = (h * 33) ^ parts.charCodeAt(i);
      }
      return (h >>> 0).toString(36);
    } catch (e) {
      return null;
    }
  }

  // --------------------------------------------------------------------------
  // Return-visit counter (first-party, persisted).
  // --------------------------------------------------------------------------
  function bumpVisitCount() {
    try {
      var k = STORAGE_PREFIX + "visits";
      var n = parseInt(window.localStorage.getItem(k) || "0", 10) + 1;
      window.localStorage.setItem(k, String(n));
      return n;
    } catch (e) {
      return 1;
    }
  }
  function firstVisitDate() {
    try {
      var k = STORAGE_PREFIX + "first_visit";
      var v = window.localStorage.getItem(k);
      if (!v) {
        v = new Date().toISOString();
        window.localStorage.setItem(k, v);
      }
      return v;
    } catch (e) {
      return new Date().toISOString();
    }
  }

  // --------------------------------------------------------------------------
  // Event buffer + batched POST.
  // --------------------------------------------------------------------------
  var buffer = [];
  var sessionStart = Date.now();
  var enabled = false; // flipped on once consent is granted (and DNT off)

  function nowISO() {
    return new Date().toISOString();
  }

  function enqueue(eventType, data) {
    if (DNT || !enabled || !consentGranted()) return;
    buffer.push({
      timestamp: nowISO(),
      event_type: eventType,
      data: data || {}
    });
    if (buffer.length >= MAX_BATCH) flush();
  }

  function envelope(events) {
    return {
      site_id: SITE_ID,
      agent_id: AGENT_ID,
      visitor_id: getVisitorId(),
      fingerprint: softFingerprint(),
      page: {
        url: location.href,
        path: location.pathname,
        title: document.title,
        referrer: document.referrer || null
      },
      session: {
        started_at: new Date(sessionStart).toISOString(),
        seconds_on_page: Math.round((Date.now() - sessionStart) / 1000),
        total_visits: parseInt(
          (function () {
            try {
              return window.localStorage.getItem(STORAGE_PREFIX + "visits") || "1";
            } catch (e) {
              return "1";
            }
          })(),
          10
        ),
        first_visit_date: firstVisitDate()
      },
      events: events
    };
  }

  function send(payload, useBeacon) {
    var body = JSON.stringify(payload);
    // The bearer token is NOT in the browser bundle. The edge worker (optional)
    // or the tunnel ingress attaches Authorization. The browser POSTs the
    // signal envelope only. See protocols/zhc-pixel-protocol.md "Token handling".
    if (useBeacon && navigator.sendBeacon) {
      try {
        navigator.sendBeacon(
          ENDPOINT,
          new Blob([body], { type: "application/json" })
        );
        return;
      } catch (e) {
        /* fall through to fetch */
      }
    }
    try {
      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body,
        keepalive: true,
        // Anonymous-but-persistent: we do NOT send credentials cross-site.
        credentials: "omit",
        mode: "cors"
      }).catch(function () {});
    } catch (e) {
      /* network failure — drop silently, never block the page */
    }
  }

  function flush(useBeacon) {
    if (DNT || !enabled || !consentGranted()) {
      buffer = [];
      return;
    }
    if (buffer.length === 0) return;
    var batch = buffer.splice(0, MAX_BATCH);
    send(envelope(batch), useBeacon === true);
  }

  // --------------------------------------------------------------------------
  // Behavior watchers — pages, time, scroll, clicks, return visits.
  // --------------------------------------------------------------------------
  var lastScroll = 0;
  function onScroll() {
    var t = Date.now();
    if (t - lastScroll < SCROLL_THROTTLE_MS) return;
    lastScroll = t;
    var doc = document.documentElement;
    var max = (doc.scrollHeight - doc.clientHeight) || 1;
    var pct = Math.min(100, Math.round((window.pageYOffset / max) * 100));
    enqueue("scroll", { depth_pct: pct });
  }

  function onClick(e) {
    var el = e.target && e.target.closest ? e.target.closest("a,button,[role=button]") : null;
    if (!el) return;
    enqueue("click", {
      tag: el.tagName ? el.tagName.toLowerCase() : null,
      text: (el.textContent || "").trim().slice(0, 80),
      href: el.getAttribute ? el.getAttribute("href") : null,
      // a coarse intent hint: does the click target look like contact/checkout?
      intent_hint: classifyClick(el)
    });
  }

  function classifyClick(el) {
    var hay = (
      (el.getAttribute && el.getAttribute("href") ? el.getAttribute("href") : "") +
      " " +
      (el.textContent || "")
    ).toLowerCase();
    if (/contact|book|appointment|schedule|demo|call|quote/.test(hay)) return "contact";
    if (/cart|checkout|buy|purchase|order|payment/.test(hay)) return "checkout";
    if (/pricing|plans|cost/.test(hay)) return "pricing";
    return null;
  }

  function onVisibilityChange() {
    if (document.visibilityState === "hidden") {
      enqueue("page_hidden", {
        seconds_on_page: Math.round((Date.now() - sessionStart) / 1000)
      });
      flush(true); // use beacon — page may be unloading
    }
  }

  // --------------------------------------------------------------------------
  // Public API (window.ZHCPixel)
  // --------------------------------------------------------------------------
  function start() {
    if (DNT) return; // hard stop under Do-Not-Track
    if (enabled) return;
    enabled = true;

    bumpVisitCount();
    firstVisitDate();

    enqueue("pageview", {
      path: location.pathname,
      title: document.title,
      referrer: document.referrer || null
    });

    window.addEventListener("scroll", onScroll, { passive: true });
    document.addEventListener("click", onClick, true);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", function () {
      flush(true);
    });

    // periodic flush
    setInterval(flush, BATCH_INTERVAL_MS);
  }

  function grantConsent() {
    writeConsent("granted");
    hideBanner();
    if (!DNT) start();
  }

  function denyConsent() {
    writeConsent("denied");
    hideBanner();
    // no tracking, no cookie
  }

  function optOut() {
    // CCPA opt-out + data-deletion request.
    var vid = readCookie(COOKIE_NAME);
    writeConsent("denied");
    enabled = false;
    buffer = [];
    if (vid) {
      // one-shot deletion request (bypasses the enabled/consent gate by design —
      // a deletion request must be honored even after opt-out).
      try {
        send(
          {
            site_id: SITE_ID,
            agent_id: AGENT_ID,
            visitor_id: vid,
            events: [{ timestamp: nowISO(), event_type: "delete_request", data: {} }]
          },
          true
        );
      } catch (e) {}
    }
    // clear local state
    try {
      writeCookie(COOKIE_NAME, "", -1);
      window.localStorage.removeItem(CONSENT_KEY);
      window.localStorage.removeItem(STORAGE_PREFIX + "visits");
      window.localStorage.removeItem(STORAGE_PREFIX + "first_visit");
    } catch (e) {}
  }

  // --------------------------------------------------------------------------
  // Built-in GDPR consent banner (used only if the host page has no CMP and
  // window.ZHCPixel.autoBanner !== false). Defers the pixel until consent.
  // --------------------------------------------------------------------------
  function showBannerIfNeeded() {
    if (DNT) return; // DNT users never see a tracking banner
    if (readConsent() === "granted") {
      start();
      return;
    }
    if (readConsent() === "denied") return;
    if (window.ZHCPixel && window.ZHCPixel.autoBanner === false) return;
    renderBanner();
  }

  function renderBanner() {
    if (document.getElementById("zhc-consent-banner")) return;
    var bar = document.createElement("div");
    bar.id = "zhc-consent-banner";
    bar.setAttribute("role", "dialog");
    bar.setAttribute("aria-label", "Cookie consent");
    bar.style.cssText =
      "position:fixed;left:0;right:0;bottom:0;z-index:2147483647;" +
      "background:#111;color:#fff;padding:14px 18px;font:14px/1.4 system-ui,sans-serif;" +
      "display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:center;";
    var msg = document.createElement("span");
    msg.textContent =
      "We use first-party cookies to improve your experience. " +
      "See our privacy policy for details.";
    var accept = document.createElement("button");
    accept.textContent = "Accept";
    accept.style.cssText =
      "background:#22c55e;color:#062;border:0;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600;";
    accept.onclick = grantConsent;
    var decline = document.createElement("button");
    decline.textContent = "Decline";
    decline.style.cssText =
      "background:transparent;color:#fff;border:1px solid #666;padding:8px 16px;border-radius:6px;cursor:pointer;";
    decline.onclick = denyConsent;
    bar.appendChild(msg);
    bar.appendChild(accept);
    bar.appendChild(decline);
    (document.body || document.documentElement).appendChild(bar);
  }

  function hideBanner() {
    var b = document.getElementById("zhc-consent-banner");
    if (b && b.parentNode) b.parentNode.removeChild(b);
  }

  // Expose the API (merge so a host page can pre-set autoBanner before load).
  window.ZHCPixel = window.ZHCPixel || {};
  window.ZHCPixel.grantConsent = grantConsent;
  window.ZHCPixel.denyConsent = denyConsent;
  window.ZHCPixel.optOut = optOut;
  window.ZHCPixel.flush = function () {
    flush(false);
  };
  window.ZHCPixel.siteId = SITE_ID;
  window.ZHCPixel.version = "1"; // ZHC Pixel protocol version

  // --------------------------------------------------------------------------
  // Boot
  // --------------------------------------------------------------------------
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showBannerIfNeeded);
  } else {
    showBannerIfNeeded();
  }
})();
