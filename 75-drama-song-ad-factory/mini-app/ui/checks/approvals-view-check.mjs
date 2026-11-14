// =============================================================================
// RUNNABLE CHECK — the approval cards the phone draws (W1-studio-page-U3)
// -----------------------------------------------------------------------------
// mini-app/ui/checks/approvals-view-check.mjs
//
// Imports the SHIPPED module with a fake `globalThis.studioService` and a
// minimal DOM shim (same idea as checks/a11y-check.mjs: no browser, no
// dependency, exit codes that mean something).
//
// WHAT IT PROVES:
//   * every stage renders a card, in the script -> song -> storyboard order,
//     under the page's own words ("Your script", "Your song — pick 1 of 3",
//     "Your storyboard", with " (revision N)" past the first version);
//   * every button sends the value the plan names:
//       script     "Looks great" -> "approve", "Change something" -> typed text
//       song       three players, "Pick this one" -> "1" / "2" / "3"
//       storyboard "Approve all" -> "GO",
//                  "Send my changes" -> ONE answer, one line per filled box
//   * the script change box is a four-row textarea, not a one-line input;
//   * the storyboard card has no per-shot button: notes on several shots leave
//     in a single answer, and empty boxes send nothing;
//   * an answer the service refuses (HTTP 409 APPROVAL_ANSWER_TAKEN) shows
//     "This was already answered, from your chat or another device. ...";
//   * an answer that lands says what happens next, in one exact sentence;
//   * a file that will not load says so and offers "Try again";
//   * an item that already has an answer shows the answer in words and offers
//     no buttons;
//   * no approval row carries the class `option`;
//   * no `innerHTML` anywhere in the shipped file.
//
// Exit codes:  0 = pass, 2 = at least one rule failed.
//
//   node checks/approvals-view-check.mjs
// =============================================================================
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { renderApprovalsFor } from "../approvals-view.js";

const here = dirname(fileURLToPath(import.meta.url));
const viewSource = readFileSync(join(here, "..", "approvals-view.js"), "utf8");

let failures = 0;
const results = [];
const rule = (name, ok, detail = "") => {
  if (!ok) failures++;
  results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  — ${detail}` : ""}`);
};

// ── the DOM shim ─────────────────────────────────────────────────────────────
function makeElement(tag) {
  return {
    tagName: String(tag).toUpperCase(),
    attrs: Object.create(null),
    children: [],
    listeners: Object.create(null),
    textContent: "",
    value: "",
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null; },
    append(...nodes) { for (const n of nodes) if (n) this.children.push(n); },
    appendChild(n) { this.children.push(n); return n; },
    replaceChildren(...nodes) { this.children = nodes.filter(Boolean); },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    focus() {},
  };
}

const registry = Object.create(null);
globalThis.document = {
  createElement: makeElement,
  getElementById: (id) => registry[id] || null,
};
registry.status = makeElement("p");
registry.main = makeElement("main");

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
};
const textOf = (node) => walk(node).map((n) => n.textContent).filter(Boolean).join(" | ");
const findButton = (root, text) => walk(root).find((n) => n.tagName === "BUTTON" && n.textContent === text);
const findCard = (root, stage) => walk(root)
  .find((n) => n.tagName === "DIV" && n.getAttribute("data-stage") === stage);
const buttonsIn = (node) => walk(node).filter((n) => n.tagName === "BUTTON");
const click = async (node) => {
  for (const fn of node.listeners.click || []) await fn();
};

const ORDER_ID = "order-77";
function fakeService(items, answerImpl) {
  const calls = [];
  return {
    calls,
    list: () => calls.filter((c) => c[0] === "list"),
    sent: () => calls.filter((c) => c[0] === "answer"),
    async listApprovals(orderId) {
      calls.push(["list", orderId]);
      return { ok: true, items: structuredClone(items) };
    },
    async answerApproval(orderId, stage, version, value) {
      calls.push(["answer", orderId, stage, version, value]);
      if (answerImpl) return answerImpl({ orderId, stage, version, value });
      return { ok: true };
    },
  };
}

const SAMPLE = [
  { stage: "storyboard", version: 2, text: "Every shot, with a picture and a card.",
    choices: [], files: [{ name: "shot-1.png", url: "https://cdn.test/shot-1.png" },
      { name: "shot-2.png", url: "https://cdn.test/shot-2.png" }], answer: null },
  { stage: "song", version: 3, text: "Listen to all three.",
    choices: [{ n: 1, label: "Version A" }, { n: 2, label: "Version B" }, { n: 3, label: "Version C" }],
    files: [{ name: "a.mp3", url: "https://cdn.test/a.mp3" },
      { name: "b.mp3", url: "https://cdn.test/b.mp3" },
      { name: "c.mp3", url: "https://cdn.test/c.mp3" }], answer: null },
  { stage: "script", version: 1, text: "The story and the song lyrics.",
    choices: [], files: [], answer: null },
];

async function render(items, answerImpl) {
  const svc = fakeService(items, answerImpl);
  globalThis.studioService = svc;
  const root = makeElement("div");
  const rendered = await renderApprovalsFor({ order_id: ORDER_ID }, root);
  return { svc, root, rendered };
}

// ── 1. what the file must not do ─────────────────────────────────────────────
rule("no innerHTML anywhere in approvals-view.js", !/\.innerHTML\s*=/.test(viewSource));
rule("does not import the unserved approvals/ui.mjs", !/from\s+["'][^"']*approvals\/ui\.mjs/.test(viewSource));

// ── 2. every stage renders, under the page's own headings ────────────────────
const SAMPLE_HEADINGS = {
  script: "Your script",
  song: "Your song — pick 1 of 3 (revision 3)",
  storyboard: "Your storyboard (revision 2)",
};
const first = await render(SAMPLE);
{
  const stages = first.root.children
    .map((c) => c.getAttribute("data-stage"));
  rule("three cards, ordered script, song, storyboard",
    JSON.stringify(stages) === JSON.stringify(["script", "song", "storyboard"]), stages.join(", "));
  rule("the service was asked for this order", first.svc.list()[0]?.[1] === ORDER_ID,
    String(first.svc.list()[0]?.[1]));
  for (const stage of ["script", "song", "storyboard"]) {
    const card = findCard(first.root, stage);
    const heading = card && card.children.find((n) => n.tagName === "H2");
    rule(`heading says the page's own words for ${stage}`,
      !!heading && heading.textContent === SAMPLE_HEADINGS[stage],
      heading ? heading.textContent : "no card");
  }
  rule("a first version names no revision",
    textOf(findCard(first.root, "script")).includes("Your script")
      && !textOf(findCard(first.root, "script")).includes("revision"));
  rule("a later version names its revision",
    textOf(findCard(first.root, "song")).includes("(revision 3)")
      && textOf(findCard(first.root, "storyboard")).includes("(revision 2)"));
  rule("no approval row carries the class option",
    walk(first.root).every((n) => !(n.getAttribute("class") || "").split(/\s+/).includes("option")));
}

// ── 3. script: the two buttons and their values ──────────────────────────────
{
  const a = await render(SAMPLE);
  await click(findButton(findCard(a.root, "script"), "Looks great"));
  rule("script “Looks great” sends approve",
    JSON.stringify(a.svc.sent()[0]) === JSON.stringify(["answer", ORDER_ID, "script", 1, "approve"]),
    JSON.stringify(a.svc.sent()[0]));

  const b = await render(SAMPLE); // a fresh card: the answered one has no boxes left
  const card = findCard(b.root, "script");
  const box = walk(card).find((n) => n.tagName === "TEXTAREA");
  rule("script change box is a four-row textarea", !!box && box.getAttribute("rows") === "4",
    box ? `rows=${box.getAttribute("rows")}` : "no textarea");
  box.value = "  make the opening shorter  ";
  await click(findButton(card, "Change something"));
  rule("script “Change something” sends the typed text",
    b.svc.sent()[0]?.[4] === "make the opening shorter", JSON.stringify(b.svc.sent()[0]));
}

// ── 4. an empty change box sends nothing ─────────────────────────────────────
{
  const { svc, root } = await render(SAMPLE);
  const card = findCard(root, "script");
  const box = walk(card).find((n) => n.tagName === "TEXTAREA");
  box.value = "   ";
  await click(findButton(card, "Change something"));
  rule("empty change box sends nothing", svc.sent().length === 0, `${svc.sent().length} call(s)`);
}

// ── 5. song: each version fetched, playable before it can be picked ──────────
// CONTRACT_EXPECTATION_CHANGE (ST5 song block, dossier ITEM 33 step 2):
//   "Fetch media with the authenticated client, create an object URL, and enable
//    the answer only after actual decode and readiness (audio can play, image loads)."
// The old hot-linked https://cdn.test/<x>.mp3 assertion is replaced, not kept.
// Derivation used here is choice C of ST5-SONG-DETERMINE-r1: NO absolute player
// count ("always three"); the count rule below is fixture-relative — one player
// per LISTED song file — plus the locked-until-playable gate, the revisioned
// route, and the named-reason lock. No player identity/count contract is invented.
{
  const D64 = "c".repeat(64);
  const songRevUrl = (ver, f) => `/api/studio/orders/${ORDER_ID}/approvals/song/${ver}/${D64}/file/${f}`;
  const SONG_ROUTE = /^\/api\/studio\/orders\/[^/]+\/approvals\/song\/[1-9][0-9]*\/[0-9a-f]{64}\/file\/[A-Za-z0-9._-]{1,80}$/;
  const makeSongBlob = (bytes) => {
    if (typeof Blob === "function") {
      try { return new Blob([new Uint8Array(bytes)], { type: "audio/mpeg" }); } catch { /* fall through */ }
    }
    return { size: bytes };
  };
  const songFiles = [
    { name: "a.mp3", url: songRevUrl(3, "a.mp3"), sha256: "1".repeat(64), bytes: 5 },
    { name: "b.mp3", url: songRevUrl(3, "b.mp3"), sha256: "2".repeat(64), bytes: 6 },
    { name: "c.mp3", url: songRevUrl(3, "c.mp3"), sha256: "3".repeat(64), bytes: 7 },
  ];
  const songKnown = new Map(songFiles.map((f) => [f.url, f]));
  const songItems = () => SAMPLE.filter((i) => i.stage === "song")
    .map((i) => ({ ...i, files: songFiles.map((f) => ({ ...f })) }));

  // AUDIO shim: a real <audio> reports readiness through readyState and
  // canplay/canplaythrough. This shim does the same two things the shipped
  // audioReady() reads, so the gate is exercised without a browser engine.
  const origCreateAudio = globalThis.document.createElement;
  let audioFails = false;
  let audioReadyDelay = 60;
  globalThis.document.createElement = function (tag) {
    const n = origCreateAudio(tag);
    if (String(tag).toUpperCase() === "AUDIO") {
      n.readyState = 0;
      n.error = null;
      n.paused = true;
      n.pause = () => { n.paused = true; };
      n.dispatch = (type) => {
        for (const fn of (n.listeners[type] || []).slice()) fn({ type });
      };
      n.removeEventListener = (type, fn) => {
        n.listeners[type] = (n.listeners[type] || []).filter((f) => f !== fn);
      };
      n.load = () => {
        setTimeout(() => {
          if (audioFails) { n.error = { code: 4 }; n.dispatch("error"); return; }
          n.readyState = 3; // HAVE_FUTURE_DATA — first playable state
          n.dispatch("canplaythrough");
        }, audioReadyDelay);
      };
    }
    return n;
  };
  // One song round: own service, request log and playable switch.
  const songRound = async (opts = {}) => {
    audioFails = Boolean(opts.fails);
    audioReadyDelay = Number.isFinite(opts.delay) ? opts.delay : 60;
    const svc = fakeService(songItems());
    const seen = [];
    svc.fetchApprovalMedia = async (url) => {
      seen.push(url);
      const f = songKnown.get(url);
      if (!f) { const e = new Error("That media address is not this studio's approval route."); e.code = "APPROVAL_MEDIA_REFUSED"; throw e; }
      return { blob: makeSongBlob(f.bytes), sha256: f.sha256 };
    };
    globalThis.studioService = svc;
    const root = makeElement("div");
    const rendered = await renderApprovalsFor({ order_id: ORDER_ID }, root);
    const card = findCard(root, "song");
    const read = () => {
      const c = findCard(root, "song");
      const players = c ? walk(c).filter((n) => n.tagName === "AUDIO") : [];
      const picks = c ? walk(c).filter((n) => n.tagName === "BUTTON" && n.textContent === "Pick this one") : [];
      return {
        players, picks,
        srcs: players.map((p) => p.getAttribute("src")),
        lockedAll: picks.length > 0 && picks.every((b) => "disabled" in b.attrs),
        unlockedAll: picks.length > 0 && picks.every((b) => !("disabled" in b.attrs)),
        text: textOf(c || makeElement("div")),
      };
    };
    const pre = read();
    await new Promise((r) => setTimeout(r, 25)); // inside the readiness delay
    const mid = read();
    await new Promise((r) => setTimeout(r, 200)); // after readiness (or the error)
    const post = read();
    return { svc, seen: seen.slice(), rendered, root, pre, mid, post, card };
  };
  try {
    const listed = songFiles.length;
    const routes = songFiles.map((f) => f.url);
    const song = await songRound();
    rule("song lists one player per listed song file",
      song.pre.players.length === listed, `${song.pre.players.length} player(s) for ${listed} file(s)`);
    rule("song players show fetched blob URLs, never the listing address",
      song.post.players.length === listed
        && song.post.srcs.every((s) => typeof s === "string" && s.startsWith("blob:"))
        && song.post.srcs.every((s) => !routes.includes(s)),
      song.post.srcs.join(","));
    rule("song audio is fetched over the exact revisioned route",
      routes.every((u) => song.seen.includes(u))
        && song.seen.every((u) => SONG_ROUTE.test(u)),
      song.seen.join(","));
    rule("song picks stay locked until each version can play",
      song.mid.picks.length === listed && song.mid.lockedAll,
      `${song.mid.picks.length} pick(s) mid-readiness`);
    rule("song picks unlock after their audio can play",
      song.post.picks.length === listed && song.post.unlockedAll,
      `${song.post.picks.length} pick(s) post-readiness`);

    const sent = [];
    for (let i = 1; i <= 3; i++) {
      const fresh = await songRound();
      await click(fresh.post.picks[i - 1]);
      sent.push(fresh.svc.sent()[0]?.[4]);
    }
    rule("song “Pick this one” sends 1, 2, 3", sent.join(",") === "1,2,3", sent.join(","));

    const broken = await songRound({ fails: true });
    rule("a media failure says it plainly and names what to do instead",
      broken.post.text.includes("This file would not load.")
        && broken.post.text.includes("If it still will not load, answer in your chat instead."),
      broken.post.text.slice(-200));
    rule("a song file that cannot play keeps its pick locked",
      broken.post.picks.length === listed
        && broken.post.picks.every((b) => "disabled" in b.attrs),
      broken.post.text.slice(-140));
    rule("a media failure offers Try again",
      !!findButton(findCard(broken.root, "song"), "Try again"));

    // Try again re-runs the load for that card: the file reads this time, so
    // the pick unlocks once its audio can play.
    audioFails = false;
    await click(findButton(findCard(broken.root, "song"), "Try again"));
    await new Promise((r) => setTimeout(r, 250));
    const againCard = findCard(broken.root, "song");
    const againPicks = againCard
      ? walk(againCard).filter((n) => n.tagName === "BUTTON" && n.textContent === "Pick this one")
      : [];
    rule("Try again re-runs the load and unlocks the pick",
      againPicks.length === listed && againPicks.every((b) => !("disabled" in b.attrs)),
      `${againPicks.length} pick(s)`);
    audioFails = true;
  } finally {
    globalThis.document.createElement = origCreateAudio;
    audioFails = false;
  }
}

// ── 6. storyboard: stills, GO, and the shot number ───────────────────────────
// CONTRACT_EXPECTATION_CHANGE (ST4/ST5 revisioned media): the storyboard stills are
// fetched through the client's fetchApprovalMedia over the exact revisioned route
// (stage/version/presentation-digest/file) and shown as blob: object URLs; the answer
// controls unlock only after each still decodes. Dossier ITEM 32 ST4 step 2: "Address
// media by revision or content digest, never by first basename match." Dossier ITEM 33
// ST5 step 2: "Fetch media with the authenticated client, create an object URL, and
// enable the answer only after actual decode and readiness (audio can play, image loads)."
// The old hot-linked https://cdn.test/shot- assertion is replaced, not kept.
// NOTE (render pipe): the shared view module serves one paint at a time and a later
// paint cancels the earlier render's in-flight media jobs; the stills rounds below
// render the storyboard card on its own (storyboard item only) and settle each round
// before reading it, because the listing rule under test is per-card: one still per
// listed file, fetched over the exact revisioned route. (The song card's players would
// mix their requests into the request log through the same fetch path.) Answer rows
// are asserted on the service that drew the answered card: the view reads
// globalThis.studioService both when it paints and when the click handler submits.
{
  // ── in-block media shim (fixture; nothing outside this block changes) ─────────
  const D64 = "d".repeat(64);
  const revUrl = (stage, ver, f) => `/api/studio/orders/${ORDER_ID}/approvals/${stage}/${ver}/${D64}/file/${f}`;
  const REV_ROUTE = /^\/api\/studio\/orders\/[^/]+\/approvals\/[^/]+\/[1-9][0-9]*\/[0-9a-f]{64}\/file\/[A-Za-z0-9._-]{1,80}$/;
  const makeBlob = (bytes) => {
    if (typeof Blob === "function") {
      try { return new Blob([new Uint8Array(bytes)], { type: "image/png" }); } catch { /* fall through */ }
    }
    return { size: bytes };
  };
  const mediaFiles = [
    { name: "shot-1.png", url: revUrl("storyboard", 2, "shot-1.png"), sha256: "a".repeat(64), bytes: 10 },
    { name: "shot-2.png", url: revUrl("storyboard", 2, "shot-2.png"), sha256: "b".repeat(64), bytes: 20 },
    { name: "shot-3.png", url: revUrl("storyboard", 2, "shot-3.png"), sha256: "c".repeat(64), bytes: 30 },
    { name: "shot-4.png", url: revUrl("storyboard", 2, "shot-4.png"), sha256: "e".repeat(64), bytes: 40 },
    { name: "shot-5.png", url: revUrl("storyboard", 2, "shot-5.png"), sha256: "f".repeat(64), bytes: 50 },
  ];
  const knownBlobs = new Map(mediaFiles.map((f) => [f.url, f]));
  const storyItems = () => SAMPLE.filter((i) => i.stage === "storyboard")
    .map((i) => ({ ...i, files: mediaFiles.map((f) => ({ ...f })) }));
  // IMG decode is deferred per render: each IMG node awaits its own render's gate,
  // so the locked state is observable before the release and the unlocked state
  // after — with no cross-render mixing, because the gate lives on the render's
  // own state object and is wired onto the node at creation.
  let activeGate = null;
  const origCreate = globalThis.document.createElement;
  globalThis.document.createElement = function (tag) {
    const n = origCreate(tag);
    if (String(tag).toUpperCase() === "IMG") {
      n.decode = () => (activeGate || Promise.resolve());
      n.complete = true;
      n.naturalWidth = 640;
      n.load = () => {};
    }
    return n;
  };
  // One stills round: its own service, request log and decode gate. The round is
  // read twice — locked before the release, settled after — then the gate is
  // released and the unlock awaited, so no later paint can cancel this round first.
  //
  // S75-072 card shape: no per-shot button. Two card-wide buttons ("Approve all",
  // "Send my changes"), both gated on the stills. `fill` is the list of notes by
  // shot number — [{ n: 2, text }, { n: 5, text }] — or null for "Approve all".
  const STORY_BUTTONS = ["Approve all", "Send my changes"];
  const storyButtonsIn = (card) => (card ? walk(card).filter((n) => n.tagName === "BUTTON"
    && STORY_BUTTONS.includes(n.textContent)) : []);
  const stillsRound = async (fill) => {
    const svc = fakeService(storyItems());
    const seen = [];
    svc.fetchApprovalMedia = async (url) => {
      seen.push(url);
      const f = knownBlobs.get(url);
      if (!f) { const e = new Error("That media address is not this studio's approval route."); e.code = "APPROVAL_MEDIA_REFUSED"; throw e; }
      return { blob: makeBlob(f.bytes), sha256: f.sha256 };
    };
    let release = null;
    activeGate = new Promise((res) => { release = res; });
    globalThis.studioService = svc;
    const root = makeElement("div");
    const rendered = await renderApprovalsFor({ order_id: ORDER_ID }, root);
    const card = findCard(root, "storyboard");
    const preImgs = card ? walk(card).filter((n) => n.tagName === "IMG") : [];
    const preBtns = storyButtonsIn(card);
    const pre = {
      imgCount: preImgs.length, imgSrcs: preImgs.map((im) => im.getAttribute("src")),
      btnCount: preBtns.length,
      lockedAll: preBtns.length > 0 && preBtns.every((b) => "disabled" in b.attrs),
    };
    release();
    await new Promise((r) => setTimeout(r, 200));
    const postCard = findCard(root, "storyboard");
    const postImgs = postCard ? walk(postCard).filter((n) => n.tagName === "IMG") : [];
    const postBtns = storyButtonsIn(postCard);
    const out = {
      svc, seen: seen.slice(), rendered, root, pre,
      imgCount: postImgs.length, imgSrcs: postImgs.map((im) => im.getAttribute("src")),
      btnCount: postBtns.length,
      unlockedAll: postBtns.length > 0 && postBtns.every((b) => !("disabled" in b.attrs)),
    };
    if (fill !== undefined) {
      const nowCard = findCard(root, "storyboard");
      if (fill === null) {
        const goBtn = findButton(nowCard, "Approve all");
        if (goBtn) await click(goBtn);
      } else {
        const boxes = walk(nowCard).filter((n) => n.tagName === "INPUT");
        for (const { n, text } of fill) {
          if (boxes[n - 1]) boxes[n - 1].value = text;
        }
        const sendBtn = findButton(nowCard, "Send my changes");
        if (sendBtn) await click(sendBtn);
      }
      await new Promise((r) => setTimeout(r, 200));
      out.sent = svc.sent().slice();
    }
    return out;
  };
  try {
    const listed = mediaFiles.length;
    const approvedRoutes = mediaFiles.map((f) => f.url);
    const storyRoutes = new Set(approvedRoutes);
    const stills = await stillsRound();
    const storySeen = stills.seen.filter((u) => storyRoutes.has(u));
    rule("storyboard answers stay locked until the stills decode",
      stills.pre.btnCount === 2 && stills.pre.lockedAll,
      `${stills.pre.btnCount} button(s) pre-decode`);
    rule("storyboard lists one still per listed file",
      stills.imgCount === listed, `${stills.imgCount} still(s) for ${listed} file(s)`);
    rule("storyboard stills show fetched blob URLs, never the listing address",
      stills.imgCount === listed && stills.imgSrcs.every((s) => typeof s === "string" && s.startsWith("blob:")),
      stills.imgSrcs.join(","));
    rule("storyboard stills are fetched over the exact revisioned route",
      approvedRoutes.every((u) => storySeen.includes(u))
        && storySeen.every((u) => REV_ROUTE.test(u))
        && stills.seen.every((u) => knownBlobs.has(u)),
      storySeen.join(","));
    rule("storyboard answers unlock after the stills decode",
      stills.btnCount === 2 && stills.unlockedAll,
      `${stills.btnCount} button(s) post-decode`);
    rule("storyboard offers the two card-wide buttons and no per-shot button",
      STORY_BUTTONS.every((t) => !!findButton(findCard(stills.root, "storyboard"), t))
        && buttonsIn(findCard(stills.root, "storyboard")).length === 2,
      `${buttonsIn(findCard(stills.root, "storyboard")).length} button(s) on the card`);

    const go = await stillsRound(null);
    rule("storyboard “Approve all” sends GO",
      stills.imgCount === listed && go.sent[0]?.[4] === "GO", JSON.stringify(go.sent[0]));

    // The headline case: notes on shots 2 and 5 leave in ONE answer, one line
    // per shot, in shot order.
    const many = await stillsRound([
      { n: 5, text: "end on the empty stage" },
      { n: 2, text: "tighter close-up" },
    ]);
    rule("notes on shots 2 and 5 produce one answer with two lines",
      many.sent.length === 1
        && many.sent[0]?.[4] === "shot 2: tighter close-up\nshot 5: end on the empty stage",
      JSON.stringify(many.sent));

    const one = await stillsRound([{ n: 2, text: "the door should be red" }]);
    rule("a note on one shot still leaves as a single shot line",
      one.sent.length === 1 && one.sent[0]?.[4] === "shot 2: the door should be red",
      JSON.stringify(one.sent));

    const none = await stillsRound([]);
    rule("empty boxes send no answer", none.sent.length === 0, `${none.sent.length} call(s)`);
    rule("empty boxes get the write-something-first sentence",
      registry.status.textContent === "Write what should change under at least one shot first.",
      registry.status.textContent);
  } finally {
    globalThis.document.createElement = origCreate;
    activeGate = null;
  }
}

// ── 7. the answer lands back on the card, in words ───────────────────────────
{
  const { root } = await render(SAMPLE);
  const card = findCard(root, "script");
  await click(findButton(card, "Looks great"));
  const after = findCard(root, "script");
  rule("an approved card says it is moving on and offers no buttons",
    textOf(after).includes("Approved. We are moving to the next step.")
      && buttonsIn(after).length === 0, textOf(after).slice(0, 140));
}

// ── 7b. a change is answered with the change sentence ────────────────────────
{
  const { root } = await render(SAMPLE);
  const card = findCard(root, "script");
  const box = walk(card).find((n) => n.tagName === "TEXTAREA");
  box.value = "make the opening shorter";
  await click(findButton(card, "Change something"));
  const after = findCard(root, "script");
  rule("a change says the new version will appear",
    textOf(after).includes("Your changes were sent. A new version will appear here."),
    textOf(after).slice(0, 160));
}

// ── 8. an item that arrives already answered ─────────────────────────────────
{
  const items = SAMPLE.map((i) => (i.stage === "song"
    ? { ...i, answer: { value: "2", by: "telegram", at: 1 } } : i));
  const { root } = await render(items);
  const card = findCard(root, "song");
  rule("an item answered elsewhere shows the pick in words",
    textOf(card).includes("You picked version 2."), textOf(card).slice(0, 140));
  rule("an answered item offers no buttons", buttonsIn(card).length === 0,
    `${buttonsIn(card).length} button(s)`);
}

// ── 9. the second answer is refused with 409 ─────────────────────────────────
{
  const taken = () => {
    const err = new Error("This approval is already answered");
    err.code = "APPROVAL_ANSWER_TAKEN";
    err.status = 409;
    throw err;
  };
  const { root } = await render(SAMPLE, taken);
  const card = findCard(root, "script");
  await click(findButton(card, "Looks great"));
  const after = findCard(root, "script");
  rule("a refused (409) answer says it was already answered elsewhere",
    textOf(after).includes("This was already answered, from your chat or another device. Nothing more to do here."),
    textOf(after).slice(0, 200));
}

// ── 10. no service installed → words, no crash ───────────────────────────────
{
  delete globalThis.studioService;
  const root = makeElement("main");
  let threw = null;
  try {
    await renderApprovalsFor({ order_id: ORDER_ID }, root);
  } catch (err) { threw = err; }
  rule("no service installed renders a sentence instead of throwing",
    threw === null && /not connected/.test(textOf(root)), threw ? threw.message : textOf(root).slice(0, 100));
}
delete globalThis.studioService;

console.log(results.join("\n"));
if (failures > 0) {
  console.log(`\napprovals-view check FAILED: ${failures} rule(s)`);
  process.exit(2);
}
console.log(`\napprovals-view check OK: ${results.length} rules passed`);
process.exit(0);
