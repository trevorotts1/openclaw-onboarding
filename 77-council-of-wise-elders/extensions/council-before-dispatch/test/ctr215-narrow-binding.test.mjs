// CTR-215 regression source: an explicit binding may authorize ONLY exact
// numeric senderIds already enumerated in the account allowFrom, and a wildcard
// account allowlist still authorizes nothing on its own.
// Created NOT RUN in this lane. A reviewer runs:
//   node --test test/ctr215-narrow-binding.test.mjs

import assert from "node:assert/strict";
import test from "node:test";

import {
  authorizedSenderSelection,
  resolveCouncilBinding,
} from "../lib/binding-predicate.mjs";

const OWNER_DM = "8487";
const OTHER_DM = "1679";

function config(bindings, allowFrom) {
  return {
    channels: {
      telegram: {
        enabled: true,
        accounts: {
          default: { enabled: true, dmPolicy: "allowlist", allowFrom },
        },
      },
    },
    agents: {
      entries: {
        "dept-master-orchestrator": { workspace: "/w/dept" },
        "remote-rescue": { workspace: "/w/rescue" },
      },
    },
    bindings,
  };
}

const catchAll = {
  agentId: "dept-master-orchestrator",
  match: { channel: "telegram", accountId: "*" },
};

function resolveWith(senderIds, { allowFrom = ["*", OWNER_DM], agentId = "dept-master-orchestrator", conversationId = OWNER_DM } = {}) {
  return resolveCouncilBinding({
    cfg: config([catchAll], allowFrom),
    channel: "telegram",
    accountId: "default",
    conversationId,
    agentId,
    senderIds,
  });
}

test("Monique shape: owner DM enumerated in allowFrom + wildcard account, explicit binding works", () => {
  const result = resolveWith([OWNER_DM]);
  assert.equal(result.ok, true, result.detail);
  assert.equal(result.matchedBy, "binding.channel");
  assert.equal(result.agentId, "dept-master-orchestrator");
});

test("wildcard account alone still fails closed for automatic derivation", () => {
  const result = resolveWith(undefined);
  assert.equal(result.ok, false);
  assert.equal(result.code, "ACCOUNT_ALLOWLIST_WILDCARD");
});

test("wildcard-only account authorizes no explicit sender", () => {
  const result = resolveWith([OWNER_DM], { allowFrom: ["*"] });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_SENDER_NOT_AUTHORIZED");
});

test("an unknown sender is refused even when the request names it explicitly", () => {
  const result = resolveWith([OTHER_DM]);
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_SENDER_NOT_AUTHORIZED");
});

test("a wildcard inside binding senderIds is refused", () => {
  const result = resolveWith(["*"]);
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_SENDER_WILDCARD");
});

test("a non-numeric binding sender id is refused", () => {
  const result = resolveWith(["owner"]);
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_SENDER_NOT_NUMERIC");
});

test("the conversation must be the enumerated sender", () => {
  const result = resolveWith([OTHER_DM], { allowFrom: ["*", OWNER_DM, OTHER_DM] });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_CONVERSATION_NOT_ENUMERATED");
});

test("a wildcard account forces exactly one enumerated id", () => {
  const result = resolveWith([OWNER_DM, OTHER_DM], { allowFrom: ["*", OWNER_DM, OTHER_DM] });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_SENDER_NOT_EXACT");
});

test("a route owned by another agent is refused", () => {
  const result = resolveWith([OWNER_DM], { agentId: "remote-rescue" });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_ROUTE_OTHER_AGENT");
});

test("a peer wildcard binding is never proof for one conversation", () => {
  const wildcard = {
    agentId: "dept-master-orchestrator",
    match: { channel: "telegram", peer: { kind: "direct", id: "*" } },
  };
  const result = resolveCouncilBinding({
    cfg: config([wildcard], ["*", OWNER_DM]),
    channel: "telegram",
    accountId: "default",
    conversationId: OWNER_DM,
    agentId: "dept-master-orchestrator",
    senderIds: [OWNER_DM],
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_PEER_WILDCARD_UNSAFE");
});

test("a wildcard-free account still narrows to an explicit subset", () => {
  const selection = authorizedSenderSelection(
    { allowFrom: [OWNER_DM, OTHER_DM] },
    [OWNER_DM],
    OWNER_DM,
  );
  assert.equal(selection.ok, true, selection.detail);
  assert.equal(selection.source, "binding");
  assert.deepEqual(selection.senderIds, [OWNER_DM]);
});

test("a wildcard-free account derives allowFrom and requires the conversation", () => {
  const ok = authorizedSenderSelection({ allowFrom: [OWNER_DM] }, undefined, OWNER_DM);
  assert.equal(ok.ok, true, ok.detail);
  assert.equal(ok.source, "allowFrom");
  const missing = authorizedSenderSelection({ allowFrom: [OTHER_DM] }, undefined, OWNER_DM);
  assert.equal(missing.ok, false);
  assert.equal(missing.code, "CONVERSATION_NOT_AUTHORIZED");
});
