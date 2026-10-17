/*
 * Node harness for interest_popup.js (used by test_interest_popup.py).
 *
 * Executes the REAL component script against a minimal DOM stub that
 * implements only the surface interest_popup.js touches, then drives
 * the popup through its submit lifecycle and reports behavioral
 * checks as one JSON line on stdout. Exit code 0 only when every
 * check passes.
 *
 * Usage: node js_harness.js <path-to-interest_popup.js>
 *
 * Checks: trailing-"@" email rejected with nothing emitted (D2);
 * validation failure shows "Nothing was sent" copy, not the send
 * copy (D4); the emitted payload carries component_version and the
 * documented field set (D1); a second submit while pending emits
 * nothing and the submit control is disabled (D7); markFailed
 * restores the send-failure copy and re-enables submit; markVerified
 * settles the flow.
 */
"use strict";

const fs = require("fs");

const SEND_TEXT =
  "Something went wrong sending your details. " +
  "Your entries are still here; please try again.";
const PREFIX = "sl-interest";

function matches(el, sel) {
  if (sel === "[data-sl-popup-close]") {
    return el.getAttribute("data-sl-popup-close") !== null;
  }
  if (sel === "[data-sl-popup-open]") {
    return el.getAttribute("data-sl-popup-open") !== null;
  }
  if (sel === ".sl-popup-submit") {
    return (el.attrs.class || "").split(/\s+/).indexOf("sl-popup-submit") >= 0;
  }
  let m = sel.match(/^input\[name='([^']+)'\]$/);
  if (m) return el.tagName === "INPUT" && el.name === m[1];
  if (sel === "input[type='checkbox'][name^='consent_']") {
    return (
      el.tagName === "INPUT" &&
      el.attrs.type === "checkbox" &&
      el.name.indexOf("consent_") === 0
    );
  }
  if (sel === "button[type='submit']") {
    return el.tagName === "BUTTON" && el.attrs.type === "submit";
  }
  throw new Error("harness: unsupported selector " + sel);
}

class El {
  constructor(tag, attrs) {
    this.tagName = String(tag).toUpperCase();
    this.attrs = attrs || {};
    this.children = [];
    this.listeners = {};
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.required = false;
    this.value = "";
    this.textContent = "";
    this.focused = false;
  }
  get name() {
    return this.attrs.name || "";
  }
  getAttribute(k) {
    return Object.prototype.hasOwnProperty.call(this.attrs, k)
      ? this.attrs[k]
      : null;
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
  }
  addEventListener(t, f) {
    (this.listeners[t] = this.listeners[t] || []).push(f);
  }
  fire(t) {
    const ev = { preventDefault() {}, target: this };
    (this.listeners[t] || []).slice().forEach((f) => f(ev));
  }
  focus() {
    this.focused = true;
  }
  append(c) {
    this.children.push(c);
    return c;
  }
  querySelector(sel) {
    const all = this.querySelectorAll(sel);
    return all.length ? all[0] : null;
  }
  querySelectorAll(sel) {
    const out = [];
    const walk = (el) => {
      el.children.forEach((c) => {
        if (matches(c, sel)) out.push(c);
        walk(c);
      });
    };
    walk(this);
    return out;
  }
}

/* ----- build the DOM the Python renderer would produce ----- */

const byId = {};
function register(el) {
  if (el.attrs.id) byId[el.attrs.id] = el;
  return el;
}

const trigger = new El("button", { "data-sl-popup-open": PREFIX });
const overlay = register(
  new El("div", { id: PREFIX + "-overlay", "data-state": "closed" })
);
overlay.hidden = true;
const closeBtn = new El("button", { "data-sl-popup-close": "" });
const form = register(new El("form", { id: PREFIX + "-form" }));
const inputs = {};
["first_name", "last_name", "email", "phone"].forEach((f) => {
  inputs[f] = form.append(new El("input", { name: f, type: "text" }));
});
const consentBoxes = {};
["email", "sms"].forEach((id) => {
  const box = form.append(
    new El("input", { name: "consent_" + id, type: "checkbox" })
  );
  box.required = true;
  consentBoxes[id] = box;
});
const errorEl = register(new El("p", { id: PREFIX + "-error" }));
errorEl.textContent = SEND_TEXT;
const pendingEl = register(new El("p", { id: PREFIX + "-pending" }));
const verifiedEl = register(new El("p", { id: PREFIX + "-verified" }));
const submitBtn = form.append(
  new El("button", { class: "sl-popup-submit", type: "submit" })
);
form.append(errorEl);
form.append(pendingEl);
form.append(verifiedEl);
overlay.append(closeBtn);
overlay.append(form);

const triggers = [trigger];
const documentStub = {
  listeners: {},
  dispatched: [],
  activeElement: null,
  getElementById(id) {
    return byId[id] || null;
  },
  querySelectorAll(sel) {
    return sel === "[data-sl-popup-open]" ? triggers.slice() : [];
  },
  addEventListener(t, f) {
    (this.listeners[t] = this.listeners[t] || []).push(f);
  },
  dispatchEvent(ev) {
    this.dispatched.push(ev);
    return true;
  },
};
class CustomEventStub {
  constructor(type, opts) {
    this.type = type;
    this.detail = (opts && opts.detail) || null;
  }
}

global.document = documentStub;
global.window = {};
global.CustomEvent = CustomEventStub;

/* ----- run the scenario ----- */

const checks = {};
function check(name, cond) {
  checks[name] = !!cond;
}
function captures() {
  return documentStub.dispatched.filter(
    (e) => e.type === "sl:interest-capture"
  );
}

try {
  const code = fs.readFileSync(process.argv[2], "utf8");
  eval(code);

  check("api exposed", typeof global.window.slInterestPopup === "object");

  trigger.fire("click");
  check("opens on trigger", overlay.hidden === false);
  check("focus moves to first field", inputs.first_name.focused === true);

  inputs.first_name.value = "Ada";
  inputs.last_name.value = "Example";
  inputs.email.value = "a@"; /* D2: trailing @ must be rejected */
  inputs.phone.value = "+15551234567";
  consentBoxes.email.checked = true;
  consentBoxes.sms.checked = true;
  form.fire("submit");
  check("trailing-at email emits nothing", captures().length === 0);
  check("state is error after bad email", overlay.getAttribute("data-state") === "error");
  check(
    "validation copy says nothing was sent (D4)",
    errorEl.textContent.indexOf("Nothing was sent.") === 0
  );
  check(
    "validation copy is not the send copy (D4)",
    errorEl.textContent.indexOf("went wrong sending") === -1
  );

  inputs.email.value = "ada@example.com";
  form.fire("submit");
  check("valid submit emits exactly once", captures().length === 1);
  const payload = captures()[0].detail;
  check("payload component_version present (D1)", payload.component_version === "1.0.0");
  check("payload component name", payload.component === "interest-popup");
  check(
    "payload field set is the documented set (D1)",
    JSON.stringify(Object.keys(payload).sort()) ===
      JSON.stringify(
        [
          "component",
          "component_version",
          "consent",
          "event",
          "fields",
          "native_field_map",
          "valid",
          "validation_errors",
        ].sort()
      )
  );
  check("payload fields carried", payload.fields.email === "ada@example.com");
  check("payload valid flag", payload.valid === true);
  check("state pending after submit", overlay.getAttribute("data-state") === "pending");
  check("submit disabled while pending (D7)", submitBtn.disabled === true);

  form.fire("submit");
  check("second submit while pending emits nothing (D7)", captures().length === 1);

  global.window.slInterestPopup.markFailed(PREFIX);
  check("markFailed shows error state", overlay.getAttribute("data-state") === "error");
  check(
    "markFailed restores send-failure copy (D4)",
    errorEl.textContent === SEND_TEXT
  );
  check("markFailed re-enables submit (D7)", submitBtn.disabled === false);

  form.fire("submit");
  check("retry after failure emits again", captures().length === 2);
  global.window.slInterestPopup.markVerified(PREFIX, { receipt: "test" });
  check("markVerified settles state", overlay.getAttribute("data-state") === "verified");
  check(
    "verified event dispatched",
    documentStub.dispatched.some((e) => e.type === "sl:interest-verified")
  );
  check("submit stays disabled after verified (D7)", submitBtn.disabled === true);
} catch (err) {
  console.log(JSON.stringify({ error: String(err && err.stack || err), checks }));
  process.exit(2);
}

console.log(JSON.stringify({ checks }));
process.exit(Object.keys(checks).every((k) => checks[k]) ? 0 : 1);
