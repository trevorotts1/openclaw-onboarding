// CTR-210 regression source for the shared, fail-closed binding predicate.
// No network, no Council runtime, no Telegram: config objects only.
//
// Run by a reviewer with:
//   node --test test/binding-predicate.test.mjs

import assert from "node:assert/strict";
import test from "node:test";

import { resolveCouncilBinding } from "../lib/binding-predicate.mjs";

const CLIENT_DM = "1000000001";
const RESCUE_DM = "1000000002";

function config(bindings, allowFrom = [CLIENT_DM, RESCUE_DM]) {
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
        "dept-ceo": { workspace: "/w/ceo" },
        "remote-rescue": { workspace: "/w/rescue" },
      },
    },
    bindings,
  };
}

const channelCatchAll = {
  agentId: "dept-ceo",
  match: { channel: "telegram", accountId: "*" },
};
const rescuePeer = {
  agentId: "remote-rescue",
  match: { channel: "telegram", peer: { kind: "direct", id: RESCUE_DM } },
};

test("Aurelia shape: channel catch-all + allowlisted DM resolves to dept-ceo", () => {
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll, rescuePeer]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, true, result.detail);
  assert.equal(result.matchedBy, "binding.channel");
});

test("an exact peer binding outranks the channel catch-all", () => {
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll, rescuePeer]),
    channel: "telegram",
    accountId: "default",
    conversationId: RESCUE_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_ROUTE_OTHER_AGENT");
});

test("an account-scoped binding outranks the channel catch-all", () => {
  const accountBinding = {
    agentId: "remote-rescue",
    match: { channel: "telegram", accountId: "default" },
  };
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll, accountBinding]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_ROUTE_OTHER_AGENT");
});

test("two agents in the winning tier are ambiguous and refused", () => {
  const second = {
    agentId: "remote-rescue",
    match: { channel: "telegram", accountId: "*" },
  };
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll, second]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_ROUTE_AMBIGUOUS");
});

test("a direct peer wildcard never certifies one conversation", () => {
  const wildcard = {
    agentId: "dept-ceo",
    match: { channel: "telegram", peer: { kind: "direct", id: "*" } },
  };
  const result = resolveCouncilBinding({
    cfg: config([wildcard]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_PEER_WILDCARD_UNSAFE");
});

test("a conversation outside allowFrom is refused", () => {
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll], [RESCUE_DM]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "CONVERSATION_NOT_AUTHORIZED");
});

test("a legacy scalar peer proves nothing", () => {
  const legacy = {
    agentId: "dept-ceo",
    match: { channel: "telegram", peer: CLIENT_DM },
  };
  const result = resolveCouncilBinding({
    cfg: config([legacy]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "BINDING_ROUTE_UNRESOLVED");
});

test("an account allowlist wildcard is refused", () => {
  const result = resolveCouncilBinding({
    cfg: config([channelCatchAll], ["*"]),
    channel: "telegram",
    accountId: "default",
    conversationId: CLIENT_DM,
    agentId: "dept-ceo",
  });
  assert.equal(result.ok, false);
  assert.equal(result.code, "ACCOUNT_ALLOWLIST_WILDCARD");
});
