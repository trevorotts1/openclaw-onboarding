/*
 * Branded interest popup behavior (component: interest-popup, owner S71).
 * Implements doc 07 section 4 behavior for the markup rendered by
 * interest_popup.py:
 *
 * - Any element with [data-sl-popup-open="<id_prefix>"] opens the popup;
 *   focus moves into the dialog and returns to that element on close.
 * - Escape, the visible close control, or an overlay click closes it.
 * - On submit the component validates the four fields and the required
 *   consent boxes, then emits ONE CustomEvent "sl:interest-capture"
 *   whose detail is the interest-capture payload (same shape as
 *   interest_popup.build_interest_capture, including
 *   component_version). It performs NO network submission itself and
 *   knows no form ID or endpoint.
 * - The email rule below mirrors interest_popup.validate_capture
 *   exactly (a present email with no "@", or one starting or ending
 *   with "@", is invalid). The Python module is canonical; keep the
 *   two in step.
 * - A validation failure shows validation copy in the error region
 *   ("Nothing was sent. Please fix ..."), listing the problems. The
 *   rendered error text (config error_text) describes a SEND failure
 *   and is shown only when the consumer reports one through
 *   markFailed(). Nothing was sent in the validation case and the
 *   copy says so.
 * - While a submission is pending the submit control is disabled and
 *   further submits are ignored, so one visitor action emits at most
 *   one sl:interest-capture. markFailed() re-enables the control;
 *   markVerified() leaves it disabled (the flow is settled).
 * - After emitting, the popup shows the pending-verification state. It
 *   does NOT claim success and does NOT route anywhere. The consumer
 *   (S06 delivery adapter) performs the native submission and then
 *   calls window.slInterestPopup.markVerified(prefix, receipt) or
 *   markFailed(prefix, message). On failure the entered values are
 *   retained and the error region is shown.
 */
(function () {
  "use strict";

  /* Keep in step with interest_popup.py COMPONENT_NAME /
     COMPONENT_VERSION and component.json: the emitted payload is the
     documented contract and carries both fields. */
  var COMPONENT_NAME = "interest-popup";
  var COMPONENT_VERSION = "1.0.0";
  var FIELDS = ["first_name", "last_name", "email", "phone"];
  var VALIDATION_ERROR_INTRO =
    "Nothing was sent. Please fix the following and try again: ";
  var lastTrigger = null;
  var sendErrorText = {}; /* per prefix: the rendered send-failure copy */
  var submissionLocked = {}; /* per prefix: a submission is pending */

  function overlay(prefix) {
    return document.getElementById(prefix + "-overlay");
  }

  function setState(prefix, state) {
    var root = overlay(prefix);
    if (!root) return;
    root.setAttribute("data-state", state);
    var error = document.getElementById(prefix + "-error");
    var pending = document.getElementById(prefix + "-pending");
    var verified = document.getElementById(prefix + "-verified");
    if (error) error.hidden = state !== "error";
    if (pending) pending.hidden = state !== "pending";
    if (verified) verified.hidden = state !== "verified";
  }

  function open(prefix, trigger) {
    var root = overlay(prefix);
    if (!root) return;
    lastTrigger = trigger || document.activeElement;
    root.hidden = false;
    setState(prefix, "open");
    var first = root.querySelector("input[name='first_name']");
    if (first) first.focus();
  }

  function close(prefix) {
    var root = overlay(prefix);
    if (!root) return;
    root.hidden = true;
    setState(prefix, "closed");
    if (lastTrigger && typeof lastTrigger.focus === "function") {
      lastTrigger.focus();
    }
  }

  function gather(form) {
    var values = {};
    FIELDS.forEach(function (field) {
      var input = form.querySelector("input[name='" + field + "']");
      values[field] = input ? input.value.trim() : "";
    });
    var consent = {};
    var requiredMissing = [];
    form
      .querySelectorAll("input[type='checkbox'][name^='consent_']")
      .forEach(function (box) {
        var id = box.name.slice("consent_".length);
        consent[id] = box.checked;
        if (box.required && !box.checked) requiredMissing.push(id);
      });
    return { values: values, consent: consent, requiredMissing: requiredMissing };
  }

  function emailLooksValid(email) {
    /* Mirrors interest_popup.validate_capture exactly: a present
       email is invalid when it has no "@", starts with "@", or ends
       with "@". Emptiness is reported separately as "required". */
    if (!email) return true;
    return (
      email.indexOf("@") >= 0 &&
      email.charAt(0) !== "@" &&
      email.charAt(email.length - 1) !== "@"
    );
  }

  function validate(values, requiredMissing) {
    var errors = [];
    FIELDS.forEach(function (field) {
      if (!values[field]) errors.push(field + " is required");
    });
    if (values.email && !emailLooksValid(values.email)) {
      errors.push("email does not look like an email address");
    }
    requiredMissing.forEach(function (id) {
      errors.push("consent required: " + id);
    });
    return errors;
  }

  function submitButton(prefix) {
    var form = document.getElementById(prefix + "-form");
    if (!form) return null;
    return (
      form.querySelector(".sl-popup-submit") ||
      form.querySelector("button[type='submit']")
    );
  }

  function setSubmissionLocked(prefix, locked) {
    submissionLocked[prefix] = locked;
    var button = submitButton(prefix);
    if (button) button.disabled = locked;
  }

  function showValidationError(prefix, errors) {
    var error = document.getElementById(prefix + "-error");
    if (error) {
      error.textContent = VALIDATION_ERROR_INTRO + errors.join("; ") + ".";
    }
    setState(prefix, "error");
  }

  function restoreSendErrorText(prefix) {
    var error = document.getElementById(prefix + "-error");
    if (error && sendErrorText[prefix]) {
      error.textContent = sendErrorText[prefix];
    }
  }

  function onSubmit(prefix, form, event) {
    event.preventDefault();
    if (submissionLocked[prefix]) return; /* one emission per action */
    var data = gather(form);
    var errors = validate(data.values, data.requiredMissing);
    if (errors.length) {
      showValidationError(prefix, errors);
      return;
    }
    var payload = {
      event: "interest_capture",
      component: COMPONENT_NAME,
      component_version: COMPONENT_VERSION,
      fields: data.values,
      native_field_map: {
        first_name: "first_name",
        last_name: "last_name",
        email: "email",
        phone: "phone"
      },
      consent: data.consent,
      valid: true,
      validation_errors: []
    };
    restoreSendErrorText(prefix);
    setSubmissionLocked(prefix, true);
    setState(prefix, "pending");
    document.dispatchEvent(
      new CustomEvent("sl:interest-capture", { detail: payload })
    );
  }

  function wire(prefix) {
    var root = overlay(prefix);
    if (!root || root.getAttribute("data-sl-wired") === "yes") return;
    root.setAttribute("data-sl-wired", "yes");
    var error = document.getElementById(prefix + "-error");
    if (error) sendErrorText[prefix] = error.textContent;
    var form = document.getElementById(prefix + "-form");
    if (form) {
      form.addEventListener("submit", function (event) {
        onSubmit(prefix, form, event);
      });
    }
    root
      .querySelectorAll("[data-sl-popup-close]")
      .forEach(function (button) {
        button.addEventListener("click", function () {
          close(prefix);
        });
      });
    root.addEventListener("click", function (event) {
      if (event.target === root) close(prefix);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !root.hidden) close(prefix);
    });
  }

  document
    .querySelectorAll("[data-sl-popup-open]")
    .forEach(function (trigger) {
      var prefix = trigger.getAttribute("data-sl-popup-open");
      wire(prefix);
      trigger.addEventListener("click", function () {
        open(prefix, trigger);
      });
    });

  window.slInterestPopup = {
    open: open,
    close: close,
    /* Called by the delivery adapter ONLY with a verified native
       submission result or approved API receipt. The submit control
       stays disabled: the capture is settled and must not re-emit. */
    markVerified: function (prefix, receipt) {
      setSubmissionLocked(prefix, true);
      setState(prefix, "verified");
      document.dispatchEvent(
        new CustomEvent("sl:interest-verified", { detail: receipt || {} })
      );
    },
    /* Called by the delivery adapter when the native submission
       failed; entered values are retained and the error is shown.
       The error copy is the adapter's message when given, otherwise
       the rendered send-failure text (never the validation copy).
       The submit control is re-enabled so the visitor can retry. */
    markFailed: function (prefix, message) {
      var error = document.getElementById(prefix + "-error");
      if (error) {
        error.textContent = message || sendErrorText[prefix] || error.textContent;
      }
      setSubmissionLocked(prefix, false);
      setState(prefix, "error");
    }
  };
})();
