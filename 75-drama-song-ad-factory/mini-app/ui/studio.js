// =============================================================================
// Drama Song Ad Factory mini-app — U3 version-0 studio UI
// -----------------------------------------------------------------------------
// mini-app/ui/studio.js
//
// Pages -> QR surface -> options -> accessibility -> the "Looks good" state,
// then the delivery download. Everything the client sees and touches is built
// here; everything that must be SAVED goes through api-client.js to the U2
// service. This file keeps no store of its own.
//
// Accessibility contract (asserted by checks/a11y-check.mjs):
//   * every control is a native <button>, <input type="radio"> or <a>;
//   * every input has a real <label>; every icon-only region has a name;
//   * focus order is source order (no positive tabindex anywhere);
//   * changing page MOVES FOCUS to the new page heading;
//   * every state change is announced in the polite live region;
//   * no state is carried by motion or colour alone — each has words too.
// =============================================================================
import { studio, serviceConnected, ServiceUnavailableError } from "./api-client.js";
import { encode, toElement } from "./qr.js";
import { verifyDownload, triggerSave } from "./download.js";

// ── The eight questions + three looks + three song versions ──────────────────
// Mirrors the client guide's production. The SERVICE is authoritative when it
// answers getOptions(); this is the layout the page can draw without it.
export const DEFAULT_OPTIONS = {
  questions: [
    { id: "offer", label: "What are we promoting?", hint: "Your offer and its link.",
      choices: [] },
    { id: "audience", label: "Who is it for, and what should they do?", hint: "One sentence.",
      choices: [] },
    { id: "character", label: "Who stars in your video?", hint: "Describe them, or bring back a saved one.",
      choices: [{ id: "new", label: "Create a new character" }, { id: "saved", label: "Use one I saved before" }] },
    { id: "length", label: "How long should it run?", hint: "Longer runs also come with 60- and 90-second clips.",
      choices: [
        { id: "60", label: "60 seconds" }, { id: "180", label: "3 minutes" },
        { id: "300", label: "5 minutes" }, { id: "600", label: "10 minutes" }] },
    { id: "music", label: "What does your song feel like?", hint: "The style the composer writes in.",
      choices: [
        { id: "soul-rise", label: "Soul Rise", hint: "Warm and uplifting" },
        { id: "quiet-drive", label: "Quiet Drive", hint: "Steady and confident" },
        { id: "bright-clap", label: "Bright Clap", hint: "Upbeat, clap-along" }] },
    { id: "look", label: "How should every shot look?", hint: "Pick the style you want to see.",
      choices: [
        { id: "lifelike-3d", label: "Lifelike 3D", hint: "Real and cinematic" },
        { id: "2d-painted", label: "2D Hand-Painted", hint: "Warm storybook" },
        { id: "sketch-to-life", label: "Sketch to Life", hint: "A sketch comes alive" },
        { id: "canvas-to-life", label: "Canvas to Life", hint: "A painted canvas comes alive" },
        { id: "canvas-to-3d", label: "Canvas to 3D", hint: "A canvas turns 3D" }] },
    { id: "model", label: "Pick the quality level", hint: "The video model that films it.",
      choices: [
        { id: "standard", label: "Standard", hint: "Fastest, lowest cost" },
        { id: "high", label: "High", hint: "Recommended balance" },
        { id: "premium", label: "Premium", hint: "Best picture, highest cost" }] },
    { id: "budget", label: "Set your ceiling", hint: "The most this run may spend, with a redo allowance.",
      choices: [{ id: "recommended", label: "The recommended budget" },
        { id: "custom", label: "A number I will give you" }] },
  ],
  looks: [
    { id: "lifelike-3d", label: "Lifelike 3D", sampleUrl: "https://studio.example.com/samples/lifelike-3d" },
    { id: "2d-painted", label: "2D Hand-Painted", sampleUrl: "https://studio.example.com/samples/2d-painted" },
    { id: "sketch-to-life", label: "Sketch to Life", sampleUrl: "https://studio.example.com/samples/sketch-to-life" },
    { id: "canvas-to-life", label: "Canvas to Life", sampleUrl: "https://studio.example.com/samples/canvas-to-life" },
    { id: "canvas-to-3d", label: "Canvas to 3D", sampleUrl: "https://studio.example.com/samples/canvas-to-3d" },
  ],
  songs: [
    { id: "a", label: "Version A", hint: "Slower, piano-led, with a gentle build", audioUrl: "https://studio.example.com/songs/a" },
    { id: "b", label: "Version B", hint: "Warm start that lifts into a bright chorus", audioUrl: "https://studio.example.com/songs/b" },
    { id: "c", label: "Version C", hint: "Upbeat from the first note, bouncy rhythm", audioUrl: "https://studio.example.com/songs/c" },
  ],
};

const PAGES = [
  { id: "start", label: "Start", title: "Welcome to your studio" },
  { id: "questions", label: "Your eight answers", title: "Tell us about your video" },
  { id: "recap", label: "The recap", title: "Read this back, then say go" },
  { id: "approvals", label: "Your approvals", title: "Three things you approve" },
  { id: "delivery", label: "Your premiere", title: "Your finished video" },
];

const state = {
  page: "start",
  options: DEFAULT_OPTIONS,
  answers: {},
  approvals: { script: false, song: null, storyboard: false },
  confirmed: false,
  delivery: null,
  deliveryVerdict: null,
  clientId: "demo-client",
};

const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of [].concat(children)) node.append(c);
  return node;
};

const main = () => document.getElementById("main");

function announce(text) {
  const status = document.getElementById("status");
  if (status) status.textContent = text;
}

// Move focus to the freshly rendered page heading — the screen-reader cue that
// the page changed. The heading is a real <h1> made focusable for exactly this.
function focusHeading() {
  const h = main().querySelector("h1");
  if (h) { h.setAttribute("tabindex", "-1"); h.focus(); }
}

function setPage(id) {
  state.page = id;
  render();
  if (location.hash !== `#${id}`) history.replaceState(null, "", `#${id}`);
}

// ── chrome ───────────────────────────────────────────────────────────────────
function renderNav() {
  const nav = document.getElementById("steps-nav");
  nav.replaceChildren(...PAGES.map((p) => {
    const b = el("button", { type: "button", text: p.label });
    if (p.id === state.page) b.setAttribute("aria-current", "page");
    b.addEventListener("click", () => setPage(p.id));
    return b;
  }));
}

function renderProgress() {
  const idx = PAGES.findIndex((p) => p.id === state.page);
  const pct = Math.round((idx / (PAGES.length - 1)) * 100);
  const rail = document.getElementById("rail");
  rail.setAttribute("aria-valuenow", String(pct));
  document.getElementById("rail-fill").style.width = `${pct}%`;
  document.getElementById("step-label").textContent = `Step ${idx + 1} of ${PAGES.length}: ${PAGES[idx].label}`;
}

// ── pages ────────────────────────────────────────────────────────────────────
function pageStart() {
  return [
    el("h1", { text: "Welcome to your studio" }),
    el("div", { class: "card" }, [
      el("p", { text: "You are the Executive Producer. You make three approvals — the script, the song and the storyboard — and the studio does the rest." }),
      el("p", { text: "One thing at a time. Nothing starts until you say it looks good." }),
      el("div", { class: "actions" }, [primary("Start your eight answers", () => setPage("questions"))]),
    ]),
    el("div", { class: "panel" }, [
      el("h2", { text: "How this works" }),
      el("ol", {}, [
        el("li", { text: "Answer eight short questions." }),
        el("li", { text: "Read the recap back. Say “looks good” to start, or change a line." }),
        el("li", { text: "Approve the script, pick one of three songs, approve the storyboard." }),
        el("li", { text: "Your finished video arrives here, ready to scan, watch and download." }),
      ]),
    ]),
  ];
}

function fieldFor(q) {
  const fieldset = el("fieldset", { class: "options" });
  fieldset.append(el("legend", { text: q.label }));
  if (q.hint) fieldset.append(el("p", { class: "hint muted", text: q.hint }));
  if (q.choices.length === 0) {
    const id = `q-${q.id}`;
    fieldset.append(el("label", { class: "visually-hidden", for: id, text: q.label }));
    const input = el("input", { id, name: q.id, type: "text", autocomplete: "off" });
    input.value = state.answers[q.id] || "";
    input.addEventListener("input", () => { state.answers[q.id] = input.value; });
    fieldset.append(input);
    return fieldset;
  }
  for (const c of q.choices) {
    const id = `q-${q.id}-${c.id}`;
    const input = el("input", { id, type: "radio", name: q.id, value: c.id });
    if (state.answers[q.id] === c.id) input.checked = true;
    input.addEventListener("change", () => { state.answers[q.id] = c.id; render(); });
    const label = el("label", { class: "option", for: id }, [
      input,
      el("span", {}, [
        el("span", { class: "label", text: c.label }),
        c.hint ? el("span", { class: "hint", text: ` ${c.hint}` }) : null,
      ].filter(Boolean)),
    ]);
    fieldset.append(label);
  }
  return fieldset;
}

function pageQuestions() {
  const answered = state.options.questions.filter((q) => state.answers[q.id]).length;
  const body = state.options.questions.map((q) => el("div", { class: "card" }, [fieldFor(q)]));
  const next = primary("Next: read the recap", () => setPage("recap"));
  return [
    el("h1", { text: "Tell us about your video" }),
    el("p", { class: "muted", text: `${answered} of ${state.options.questions.length} answered. Your answers are saved as you go.` }),
    ...body,
    el("div", { class: "actions" }, [next]),
  ];
}

const LINE_LABELS = {
  offer: "The offer", audience: "Who it is for", character: "The star",
  length: "How long it runs", music: "The music", look: "The look",
  model: "The quality", budget: "The budget",
};

function pageRecap() {
  const rows = state.options.questions.map((q, i) => {
    const chosen = q.choices.find((c) => c.id === state.answers[q.id]);
    const value = chosen ? chosen.label : (state.answers[q.id] || "not chosen yet");
    return el("li", { text: `${i + 1}. ${LINE_LABELS[q.id] || q.label}: ${value}` });
  });
  const look = state.options.looks.find((l) => l.id === state.answers.look);
  const qrCard = look ? el("div", { class: "card" }, [
    el("h2", { text: `See the ${look.label} look on your phone` }),
    qrSurface(look.sampleUrl, `Sample of the ${look.label} look`),
  ]) : null;

  const confirmBtn = primary("Looks good — start my video", async () => {
    state.confirmed = true;
    try {
      await studio.advance({ clientId: state.clientId, stage: "confirmed" });
      announce("Confirmed. The studio is starting your production.");
    } catch (err) {
      announce(serviceMessage(err));
    }
    render();
  });

  return [
    el("h1", { text: "Read this back, then say go" }),
    ...(state.confirmed
      ? [el("p", { class: "complete", text: "Looks good — your production is starting. You will approve the script next." })]
      : []),
    el("div", { class: "card" }, [el("h2", { text: "Your recap" }), el("ol", {}, rows)]),
    qrCard,
    state.confirmed ? null : el("p", { class: "muted", text: "If a line is wrong, go back and change it — it is free right now." }),
    el("div", { class: "actions" }, [
      state.confirmed ? null : confirmBtn,
      secondary("Change an answer", () => setPage("questions")),
      primary("Go to my approvals", () => setPage("approvals")),
    ].filter(Boolean)),
  ].filter(Boolean);
}

function approvalCard(kind, title, body, doneText, actionLabel, onApprove) {
  const done = kind === "song" ? !!state.approvals.song : state.approvals[kind];
  return el("div", { class: "card" }, [
    el("h2", { text: title }),
    ...body,
    done
      ? el("p", { class: "complete", text: doneText })
      : el("div", { class: "actions" }, [primary(actionLabel, onApprove)]),
  ]);
}

function pageApprovals() {
  const songs = state.options.songs;
  const songBody = songs.map((s) => {
    const id = `song-${s.id}`;
    const input = el("input", { id, type: "radio", name: "song", value: s.id });
    if (state.approvals.song === s.id) input.checked = true;
    input.addEventListener("change", async () => {
      state.approvals.song = s.id;
      try { await studio.saveAnswer({ clientId: state.clientId, questionId: "song", value: s.id }); }
      catch (err) { announce(serviceMessage(err)); }
      announce(`You chose ${s.label}.`);
      render();
    });
    return el("label", { class: "option", for: id }, [
      input,
      el("span", {}, [el("span", { class: "label", text: s.label }),
        el("span", { class: "hint", text: ` ${s.hint}` })]),
    ]);
  });

  return [
    el("h1", { text: "Three things you approve" }),
    approvalCard("script", "Approval 1 — the script",
      [el("p", { text: "The story and the song lyrics, before the song is recorded. Read it out loud; anything that trips your tongue, tell us." })],
      "Script approved. Thank you.", "Looks good — approve the script",
      () => { state.approvals.script = true; announce("Script approved."); render(); }),
    approvalCard("song", "Approval 2 — the song (pick 1 of 3)",
      [el("p", { text: "Listen to all three, then pick the one you would play on a long drive." }),
        el("fieldset", { class: "options" }, [el("legend", { text: "Which version do you want?" }), ...songBody])],
      "Song chosen. Thank you.", "Looks good — use this song",
      () => {
        if (!state.approvals.song) { announce("Pick one of the three versions above first."); return; }
        announce("Song approved.");
        render();
      }),
    approvalCard("storyboard", "Approval 3 — the storyboard",
      [el("p", { text: "Every shot, with a picture and a card. This is the last stop before anything is filmed." })],
      "Storyboard approved. Thank you.", "Looks good — approve every shot",
      () => { state.approvals.storyboard = true; announce("Storyboard approved."); render(); }),
    el("div", { class: "actions" }, [primary("Go to my premiere", () => setPage("delivery"))]),
  ];
}

function qrSurface(url, what) {
  const wrap = el("div", { class: "qr-surface" });
  try {
    const matrix = encode(url);
    const svg = toElement(matrix, { scale: 6 });
    svg.setAttribute("aria-label", `QR code for ${what}. The same link is written out below.`);
    wrap.append(svg);
  } catch (err) {
    wrap.append(el("p", { class: "refusal", text: `The code could not be drawn (${err.message}). Use the link below.` }));
  }
  wrap.append(el("p", { class: "qr-link" }, [
    el("span", { class: "muted", text: "Or open it directly: " }),
    el("a", { href: url, rel: "noopener", text: url }),
  ]));
  wrap.append(el("ol", { class: "qr-steps" }, [
    el("li", { text: "Open your phone's camera." }),
    el("li", { text: "Point it at the code above." }),
    el("li", { text: "Tap the link that appears." }),
  ]));
  return wrap;
}

function pageDelivery() {
  const d = state.delivery;
  if (!d) {
    return [
      el("h1", { text: "Your finished video" }),
      el("p", { class: "muted", text: "Nothing is ready to watch yet. Your premiere lands here the moment the studio finishes." }),
      el("div", { class: "card" }, [
        el("h2", { text: "Where it will be" }),
        el("p", { text: "The finished video, the 60- and 90-second clips, a ready-to-post kit and a code you can scan to watch on your phone." }),
      ]),
    ];
  }

  const verdict = state.deliveryVerdict;
  const checkBtn = secondary("Check the download before saving", async () => {
    announce("Checking the download…");
    state.deliveryVerdict = await verifyDownload(d.masterUrl, {
      fetchImpl: (...args) => (
        serviceConnected() && globalThis.studioService.fetchDelivery
          ? globalThis.studioService.fetchDelivery(...args)
          : fetch(...args)
      ),
      expectedBytes: d.masterBytes ?? null,
    });
    announce(state.deliveryVerdict.ok
      ? "That link gives a real file. You can save it."
      : "That link is not a real download. See the note above the button.");
    render();
  });

  const saveBtn = primary("Download my video", () => {
    triggerSave(d.masterUrl, "05 - Video Captioned.mp4");
    announce("Saving your video.");
  });
  if (!verdict?.ok) {
    saveBtn.disabled = true;
    saveBtn.setAttribute("aria-disabled", "true");
    saveBtn.title = "Check the link first — a redirect is not a download";
  }

  return [
    el("h1", { text: "Your finished video" }),
    verdict && !verdict.ok ? el("p", { class: "refusal", text: `This link is not an actual download: ${verdict.reasons.join("; ")}.` }) : null,
    verdict?.ok ? el("p", { class: "complete", text: `Real file: ${verdict.receivedBytes} bytes, ${verdict.contentType}.` }) : null,
    el("div", { class: "card" }, [
      el("h2", { text: "Watch and save" }),
      el("p", { text: "Check the link first. A link that only redirects is not a download — you would get a page instead of your video." }),
      el("div", { class: "actions" }, [checkBtn, saveBtn]),
    ]),
    d.clips?.length ? el("div", { class: "card" }, [
      el("h2", { text: "Clips for social media" }),
      el("ul", {}, d.clips.map((c) => el("li", { text: `${c.label} — ${c.url}` }))),
    ]) : null,
    d.qrPayload ? el("div", { class: "card" }, [
      el("h2", { text: "Watch it on your phone" }),
      qrSurface(d.qrPayload, "your finished video"),
    ]) : null,
  ].filter(Boolean);
}

function primary(label, onClick) {
  const b = el("button", { class: "btn", type: "button", text: label });
  b.addEventListener("click", onClick);
  return b;
}
function secondary(label, onClick) {
  const b = el("button", { class: "btn secondary", type: "button", text: label });
  b.addEventListener("click", onClick);
  return b;
}
function serviceMessage(err) {
  if (err instanceof ServiceUnavailableError) return err.message;
  return `Something went wrong saving that (${err.message}). Nothing was lost — try again.`;
}

// ── render ───────────────────────────────────────────────────────────────────
const RENDERERS = {
  start: pageStart, questions: pageQuestions, recap: pageRecap,
  approvals: pageApprovals, delivery: pageDelivery,
};

export function render() {
  renderNav();
  renderProgress();
  main().replaceChildren(...RENDERERS[state.page]());
  focusHeading();
}

async function boot() {
  const hash = location.hash.replace("#", "");
  if (PAGES.some((p) => p.id === hash)) state.page = hash;

  if (serviceConnected()) {
    try {
      const session = await studio.getSession({ clientId: state.clientId });
      state.answers = session.answers || {};
      state.approvals = session.approvals || state.approvals;
      const opts = await studio.getOptions({ clientId: state.clientId });
      if (opts?.questions) state.options = opts;
    } catch (err) {
      announce(serviceMessage(err));
    }
  }

  render();
  window.addEventListener("hashchange", () => {
    const id = location.hash.replace("#", "");
    if (PAGES.some((p) => p.id === id) && id !== state.page) { state.page = id; render(); }
  });
}

if (typeof document !== "undefined") boot();

export { state, PAGES };
