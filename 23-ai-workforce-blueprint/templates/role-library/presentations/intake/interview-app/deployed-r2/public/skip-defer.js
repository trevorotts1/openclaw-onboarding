/**
 * U057: Interview skip/defer bypass module.
 * Node.js require() support exports cookie helpers via _jarStr.
 */
(function () {
  "use strict";

  var COOKIE_NAME = "intake_skip_defer";
  var COOKIE_TTL_SECONDS = 3600;
  var _jarStr = "";

  function cookieGet() {
    var raw;
    if (typeof document !== "undefined" && document.cookie !== undefined) {
      raw = document.cookie || "";
    } else {
      raw = _jarStr;
    }
    var cookies = raw.split(";");
    for (var i = 0; i < cookies.length; i++) {
      var part = cookies[i].trim();
      if (part.indexOf(COOKIE_NAME + "=") === 0) {
        return part.substring(COOKIE_NAME.length + 1) === "1";
      }
    }
    return false;
  }

  function cookieSet() {
    var val = COOKIE_NAME + "=1; max-age=" + COOKIE_TTL_SECONDS + "; path=/; SameSite=Lax";
    if (typeof document !== "undefined" && document.cookie !== undefined) {
      document.cookie = val;
    } else {
      var parts = _jarStr.split(";").filter(function (s) { return s.trim(); });
      parts = parts.filter(function (s) { return s.trim().indexOf(COOKIE_NAME + "=") !== 0; });
      parts.push(COOKIE_NAME + "=1");
      _jarStr = parts.join(";");
    }
  }

  function cookieClear() {
    var val = COOKIE_NAME + "=0; max-age=0; path=/; SameSite=Lax";
    if (typeof document !== "undefined" && document.cookie !== undefined) {
      document.cookie = val;
    } else {
      var parts = _jarStr.split(";").filter(function (s) { return s.trim(); });
      parts = parts.filter(function (s) { return s.trim().indexOf(COOKIE_NAME + "=") !== 0; });
      _jarStr = parts.join(";");
    }
  }

  // Node.js exports (BEFORE any browser-only code)
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      COOKIE_NAME: COOKIE_NAME,
      COOKIE_TTL_SECONDS: COOKIE_TTL_SECONDS,
      cookieGet: cookieGet,
      cookieSet: cookieSet,
      cookieClear: cookieClear,
    };
    Object.defineProperty(module.exports, "_jarStr", {
      get: function () { return _jarStr; },
      set: function (v) { _jarStr = v; },
      enumerable: true,
      configurable: true,
    });
    return;
  }

  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === "class") e.className = attrs[k];
      else if (k === "text") e.textContent = attrs[k];
      else if (k === "html") e.innerHTML = attrs[k];
      else if (k === "style") e.setAttribute("style", attrs[k]);
      else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) {
      if (c) e.appendChild(c);
    });
    return e;
  }

  function buildBanner() {
    var banner = el("div", { class: "skip-banner" });
    banner.appendChild(el("span", {
      text: "Interview not complete. Dashboard access is limited — finish your interview to unlock everything.",
    }));
    var dismissBtn = el("button", { "aria-label": "Dismiss banner" });
    dismissBtn.textContent = "\u00d7";
    dismissBtn.onclick = function () { banner.style.display = "none"; };
    banner.appendChild(dismissBtn);
    return banner;
  }

  function buildTile(title, subtitle) {
    var tile = el("div", { class: "dash-tile" });
    tile.appendChild(el("div", { class: "dash-tile-title", text: title }));
    tile.appendChild(el("div", { class: "dash-tile-subtitle", text: subtitle }));
    return tile;
  }

  function renderDashboard() {
    var app = document.getElementById("app");
    var bar = document.getElementById("progress");
    if (!app) return;
    while (app.firstChild) app.removeChild(app.firstChild);
    if (bar) bar.style.width = "100%";
    var banner = buildBanner();
    app.appendChild(banner);
    var card = el("div", { class: "card center" });
    card.appendChild(el("div", { class: "big", text: "Dashboard (Limited Access)" }));
    card.appendChild(el("p", { class: "help", text: "You skipped the interview. Access expires in 1 hour." }));
    var row = el("div", { class: "row", style: "justify-content:center; gap:12px; margin-top:20px" });
    var startBtn = el("button", { class: "primary", text: "Start interview" });
    startBtn.onclick = function () { cookieClear(); window.location.reload(); };
    row.appendChild(startBtn);
    card.appendChild(row);
    app.appendChild(card);
    var stub = el("div", { style: "max-width:640px; margin:20px auto" });
    stub.appendChild(el("h2", { text: "Available panels" }));
    var tilesRow = el("div", { style: "display:flex; flex-wrap:wrap; gap:12px" });
    tilesRow.appendChild(buildTile("System status", "All systems operational"));
    tilesRow.appendChild(buildTile("Recent activity", "No recent activity"));
    tilesRow.appendChild(buildTile("Message center", "No new messages"));
    stub.appendChild(tilesRow);
    app.appendChild(stub);
  }

  var injected = false;

  function injectSkipButton() {
    if (injected) return;
    var cards = document.querySelectorAll("#app .card.center");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var heading = card.querySelector(".big");
      if (!heading || heading.textContent !== "Hmm.") continue;
      if (card.querySelector(".skip-bypass-row")) return;
      var row = el("div", { class: "row skip-bypass-row", style: "justify-content:center; gap:12px" });
      var skipBtn = el("button", { class: "primary", text: "Skip for now" });
      skipBtn.onclick = function () { cookieSet(); renderDashboard(); };
      row.appendChild(skipBtn);
      card.appendChild(row);
      card.appendChild(el("p", { class: "help", text: "Skip lets you access the dashboard for 1 hour." }));
      injected = true;
      return;
    }
  }

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent = ".skip-banner{background:var(--accent,#f2b134);color:var(--accent-ink,#1c1c22);text-align:center;padding:12px 16px;font-size:14px;font-weight:600}.skip-banner button{margin-left:12px;background:transparent;color:inherit;border:1px solid currentColor;border-radius:50%;width:22px;height:22px;cursor:pointer;font-weight:700}.dash-tile{flex:1;min-width:150px;background:var(--card,#fff);border:1px solid var(--line,#e6e6ee);border-radius:12px;padding:16px}.dash-tile-title{font-weight:650;font-size:14px;margin-bottom:4px}.dash-tile-subtitle{color:var(--muted,#6b6b78);font-size:13px}";
    document.head.appendChild(style);
  }

  injectStyles();

  if (cookieGet()) {
    setTimeout(function () { var app = document.getElementById("app"); if (app) renderDashboard(); }, 200);
  }

  var app = document.getElementById("app");
  if (app) {
    var observer = new MutationObserver(function () { setTimeout(injectSkipButton, 100); });
    observer.observe(app, { childList: true, subtree: true });
  }

  setTimeout(injectSkipButton, 600);
})();
