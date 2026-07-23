/**
 * U057: Interview skip/defer bypass module.
 *
 * Provides a "Skip for now" button on the interview fatal/lock screen that sets
 * a 1-hour bypass cookie and shows a limited dashboard. On subsequent page loads
 * within the cookie window, the limited dashboard is shown instead of the
 * interview, with a persistent reminder banner until the interview is completed.
 *
 * Include: <script src="skip-defer.js" defer></script>
 */
(function () {
  "use strict";

  var COOKIE_NAME = "intake_skip_defer";
  var COOKIE_TTL_SECONDS = 3600; // 1 hour

  // ---- Cookie helpers -------------------------------------------------------

  function cookieGet() {
    var cookies = (document.cookie || "").split(";");
    for (var i = 0; i < cookies.length; i++) {
      var part = cookies[i].trim();
      if (part.indexOf(COOKIE_NAME + "=") === 0) {
        return part.substring(COOKIE_NAME.length + 1) === "1";
      }
    }
    return false;
  }

  function cookieSet() {
    document.cookie =
      COOKIE_NAME + "=1; max-age=" + COOKIE_TTL_SECONDS + "; path=/; SameSite=Lax";
  }

  function cookieClear() {
    document.cookie =
      COOKIE_NAME + "=0; max-age=0; path=/; SameSite=Lax";
  }

  // ---- Element factory ------------------------------------------------------

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

  // ---- Reminder banner ------------------------------------------------------

  function buildBanner() {
    var banner = el("div", { class: "skip-banner" });
    banner.appendChild(
      el("span", {
        text: "Interview not complete. Dashboard access is limited — finish your interview to unlock everything.",
      })
    );
    var dismissBtn = el("button", { "aria-label": "Dismiss banner" });
    dismissBtn.textContent = "×";
    dismissBtn.onclick = function () {
      banner.style.display = "none";
    };
    banner.appendChild(dismissBtn);
    return banner;
  }

  // ---- Dashboard tile -------------------------------------------------------

  function buildTile(title, subtitle) {
    var tile = el("div", { class: "dash-tile" });
    tile.appendChild(el("div", { class: "dash-tile-title", text: title }));
    tile.appendChild(el("div", { class: "dash-tile-subtitle", text: subtitle }));
    return tile;
  }

  // ---- Limited dashboard renderer -------------------------------------------

  function renderDashboard() {
    var app = document.getElementById("app");
    var bar = document.getElementById("progress");
    if (!app) return;

    while (app.firstChild) app.removeChild(app.firstChild);
    if (bar) bar.style.width = "100%";

    var banner = buildBanner();
    app.appendChild(banner);

    var card = el("div", { class: "card center" });
    card.appendChild(
      el("div", { class: "big", text: "Dashboard (Limited Access)" })
    );
    card.appendChild(
      el("p", {
        class: "help",
        text: "You skipped the interview. Access expires in 1 hour. When you're ready, complete your interview for full access.",
      })
    );

    var row = el("div", {
      class: "row",
      style: "justify-content:center; gap:12px; margin-top:20px;",
    });
    var startBtn = el("button", { class: "primary", text: "Start interview" });
    startBtn.onclick = function () {
      cookieClear();
      window.location.reload();
    };
    row.appendChild(startBtn);
    var dismissBtn = el("button", { class: "ghost", text: "Dismiss for now" });
    dismissBtn.onclick = function () {
      banner.style.display = "none";
    };
    row.appendChild(dismissBtn);
    card.appendChild(row);
    app.appendChild(card);

    var stub = el("div", {
      style: "max-width:640px; margin:20px auto; padding:0 18px;",
    });
    stub.appendChild(
      el("h2", {
        style: "font-size:18px; font-weight:650; color:var(--muted); margin-bottom:10px;",
        text: "Available panels",
      })
    );
    var tilesRow = el("div", {
      style: "display:flex; flex-wrap:wrap; gap:12px;",
    });
    tilesRow.appendChild(buildTile("System status", "All systems operational"));
    tilesRow.appendChild(buildTile("Recent activity", "No recent activity"));
    tilesRow.appendChild(buildTile("Message center", "No new messages"));
    stub.appendChild(tilesRow);
    app.appendChild(stub);
  }

  // ---- Inject "Skip for now" button into fatal screen -----------------------

  var injected = false;

  function injectSkipButton() {
    if (injected) return;

    var cards = document.querySelectorAll("#app .card.center");
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var heading = card.querySelector(".big");
      if (!heading || heading.textContent !== "Hmm.") continue;
      if (card.querySelector(".skip-bypass-row")) return;

      var row = el("div", {
        class: "row skip-bypass-row",
        style: "justify-content:center; gap:12px;",
      });
      var skipBtn = el("button", { class: "primary", text: "Skip for now" });
      skipBtn.onclick = function () {
        cookieSet();
        renderDashboard();
      };
      row.appendChild(skipBtn);
      var retryBtn = el("button", { class: "ghost", text: "Try again" });
      retryBtn.onclick = function () {
        window.location.reload();
      };
      row.appendChild(retryBtn);
      card.appendChild(row);
      card.appendChild(
        el("p", {
          class: "help",
          style: "font-size:13px;",
          text: "Skip lets you access the dashboard for 1 hour. A reminder banner will stay until your interview is complete.",
        })
      );
      injected = true;
      return;
    }
  }

  // ---- Styles ---------------------------------------------------------------

  function injectStyles() {
    var style = document.createElement("style");
    style.textContent =
      ".skip-banner{" +
      "background:var(--accent,#f2b134);color:var(--accent-ink,#1c1c22);" +
      "text-align:center;padding:12px 16px;font-size:14px;font-weight:600;" +
      "}" +
      ".skip-banner button{" +
      "margin-left:12px;background:transparent;color:inherit;" +
      "border:1px solid currentColor;border-radius:50%;width:22px;height:22px;" +
      "cursor:pointer;font-weight:700;line-height:1;vertical-align:middle;" +
      "font-size:16px;" +
      "}" +
      ".dash-tile{" +
      "flex:1;min-width:150px;background:var(--card,#fff);" +
      "border:1px solid var(--line,#e6e6ee);border-radius:12px;padding:16px;" +
      "}" +
      ".dash-tile-title{" +
      "font-weight:650;font-size:14px;margin-bottom:4px;" +
      "}" +
      ".dash-tile-subtitle{" +
      "color:var(--muted,#6b6b78);font-size:13px;" +
      "}";
    document.head.appendChild(style);
  }

  // ---- Init -----------------------------------------------------------------

  injectStyles();

  if (cookieGet()) {
    var pollAttempts = 0;
    var MAX_POLLS = 40;

    function pollForRender() {
      pollAttempts++;
      var app = document.getElementById("app");
      if (!app && pollAttempts < MAX_POLLS) {
        setTimeout(pollForRender, 150);
        return;
      }
      if (!app) return;
      var hasSpinner = app.querySelector(".spin");
      if (hasSpinner && pollAttempts < MAX_POLLS) {
        setTimeout(pollForRender, 150);
        return;
      }
      if (!app.children.length && pollAttempts < MAX_POLLS) {
        setTimeout(pollForRender, 150);
        return;
      }
      renderDashboard();
    }

    setTimeout(pollForRender, 200);
  }

  var app = document.getElementById("app");
  if (app) {
    var observer = new MutationObserver(function () {
      setTimeout(injectSkipButton, 100);
    });
    observer.observe(app, { childList: true, subtree: true });
  }

  setTimeout(injectSkipButton, 600);
})();
