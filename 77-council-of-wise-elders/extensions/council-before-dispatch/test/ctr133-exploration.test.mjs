// CTR-133 targeted regression source. NOT EXECUTED by the implementer.
//
// Run by Trevor (or an independent reviewer) with:
//   node --test test/ctr133-exploration.test.mjs
//
// Every seam is injected: no Council service, provider, Telegram, database, or
// network call is made. The fake runtime never convenes and never scores.
//
// Cases:
//   1. the EXACT observed screenshot ask (Instagram following, no stated
//      alternatives) must not produce a scored brief or the option-explore
//      placeholder;
//   2. an unavailable runtime/context must remain a typed refusal;
//   3. a genuine preparation pass may supply PROPOSED alternatives, labelled
//      as proposals, which then form a normal brief;
//   4. the placeholder is never reintroduced from a legacy permitted payload.

import assert from "node:assert/strict";
import test from "node:test";

import {
  BRIEF_STATE,
  buildBrief,
  EXPLORATION_OPTION_ID,
  EXPLORATION_OPTION_LABEL,
  isUnresolvedExplorationOption,
  PREPARATION_REQUIRED_CODE,
  RUNTIME_UNRESOLVED_CODE,
} from "../lib/core.mjs";

const OBSERVED_QUESTION = "WHAT THE BEST WAY TO GROM MY INSTAGRAM FOLLOWING";
const NOW = "2026-10-30T10:58:12.852Z";

function fakeRuntime(overrides = {}) {
  return {
    assembleBrief: () => ({
      options: [],
      facts: [],
      constraints: [],
      unknowns: [],
      meta: { sources_read: ["agents.md", "user.md"] },
      ...overrides.permitted,
    }),
    validateDecisionBrief: (brief) => ({ ok: true, value: brief }),
    prepareProposals: overrides.prepareProposals,
  };
}

function baseArgs(loadRuntimeImpl, extra = {}) {
  return {
    question: OBSERVED_QUESTION,
    workspace: "/tmp/ctr133-workspace",
    displayTimezone: "America/New_York",
    now: NOW,
    runtimeRoot: "",
    councilAskPath: "/tmp/council-runtime/bin/council-ask",
    loadRuntimeImpl,
    readFile: () => Buffer.from(""),
    ...extra,
  };
}

test("exact screenshot ask never builds a scored placeholder brief", async () => {
  const result = await buildBrief(baseArgs(async () => fakeRuntime()));

  assert.equal(result.ok, false);
  assert.equal(result.code, PREPARATION_REQUIRED_CODE);
  assert.equal(result.state, BRIEF_STATE.INPUT_NEEDED);
  assert.equal(result.brief, undefined, "no DecisionBrief may be returned");
  assert.equal(result.preparation.request_budget, 0, "no provider request without a route");
  assert.equal(result.preparation.requires_new_inference, false);

  const serialized = JSON.stringify(result);
  assert.equal(serialized.includes(EXPLORATION_OPTION_ID), false);
  assert.equal(serialized.includes(EXPLORATION_OPTION_LABEL), false);
});

test("unavailable runtime context stays a typed refusal, never a brief", async () => {
  const error = Object.assign(new Error("zod missing"), {
    code: RUNTIME_UNRESOLVED_CODE,
    detail: "the activated release is not dependency-complete",
    action: "Repair the Council runtime, then resend.",
  });
  const result = await buildBrief(
    baseArgs(async () => {
      throw error;
    }),
  );

  assert.equal(result.ok, false);
  assert.equal(result.code, RUNTIME_UNRESOLVED_CODE);
  assert.equal(result.brief, undefined);
  assert.equal(JSON.stringify(result).includes(EXPLORATION_OPTION_ID), false);
});

test("a preparation pass supplies proposed alternatives, labelled as proposals", async () => {
  const prepareProposals = async () => ({
    ok: true,
    state: "preparing",
    options: [
      { id: "option-proposed-1", label: "Publish three belief-led reels per week for 30 days", kind: "bounded_test" },
      { id: "option-proposed-2", label: "Run one collaboration with a same-audience creator", kind: "change" },
    ],
    unknowns: ["Current follower baseline is not stated."],
    request_budget: 1,
    request_count: 1,
  });
  const result = await buildBrief(baseArgs(async () => fakeRuntime(), { prepareProposals }));

  assert.equal(result.ok, true);
  assert.equal(result.state, BRIEF_STATE.RECOMMENDATION);
  assert.equal(result.brief.options.length, 2);
  assert.deepEqual(
    result.brief.options.map((option) => option.id),
    ["option-proposed-1", "option-proposed-2"],
  );
  const unknowns = result.brief.unknowns.map((unknown) => unknown.statement).join(" ");
  assert.match(unknowns, /PROPOSED strategies/);
  assert.match(unknowns, /Current follower baseline is not stated/);
  assert.equal(JSON.stringify(result.brief).includes(EXPLORATION_OPTION_ID), false);
});

test("delegated preparation exposes preparing and requires a linked new inference", async () => {
  const prepareProposals = async () => ({
    state: "preparing",
    pending: true,
    request_budget: 1,
  });
  const result = await buildBrief(baseArgs(async () => fakeRuntime(), { prepareProposals }));

  assert.equal(result.ok, false);
  assert.equal(result.code, PREPARATION_REQUIRED_CODE);
  assert.equal(result.state, BRIEF_STATE.PREPARING);
  assert.equal(result.preparation.requires_new_inference, true);
  assert.equal(result.preparation.request_budget, 1);
  assert.equal(result.brief, undefined);
});

test("a legacy placeholder option in permitted context is dropped, not renamed", async () => {
  const result = await buildBrief(
    baseArgs(async () =>
      fakeRuntime({
        permitted: {
          options: [EXPLORATION_OPTION_LABEL],
          facts: [],
          constraints: [],
          unknowns: [],
          meta: { sources_read: ["agents.md"] },
        },
      }),
    ),
  );

  assert.equal(result.ok, false);
  assert.equal(result.code, PREPARATION_REQUIRED_CODE);
  assert.equal(result.state, BRIEF_STATE.INPUT_NEEDED);
  assert.equal(JSON.stringify(result).includes("option-explore"), false);
});

test("the placeholder predicate recognises id and legacy label only", () => {
  assert.equal(isUnresolvedExplorationOption({ id: EXPLORATION_OPTION_ID, label: "anything" }), true);
  assert.equal(isUnresolvedExplorationOption({ id: "option-1", label: EXPLORATION_OPTION_LABEL }), true);
  assert.equal(
    isUnresolvedExplorationOption({ id: "option-1", label: "Explore hiring a content editor" }),
    false,
  );
  assert.equal(
    isUnresolvedExplorationOption({ id: "option-2", label: "Publish three reels per week" }),
    false,
  );
});
