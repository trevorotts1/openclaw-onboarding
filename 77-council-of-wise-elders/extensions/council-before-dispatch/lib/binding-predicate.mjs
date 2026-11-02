// CTR-210: one fail-closed binding predicate shared by provision.mjs and
// entry-validate.mjs.
//
// OpenClaw resolves an inbound direct message through these route tiers, in
// order (dist/resolve-route-*.mjs): exact peer, peer.parent, peer wildcard,
// guild+roles, guild, team, account, channel. A direct message carries no
// parent, guild or team context, so those tiers cannot fire for a DM; the
// predicate excludes them rather than guessing. A Council entry is valid only
// when the tier
// that actually resolves the entry's conversationId selects the entry's own
// agentId, and conversationId is an authorized sender on that account.
//
// A channel-wide binding may win for a DM, but it is accepted only as the
// winning tier with an allowlisted conversationId; it is never expanded into
// "any sender". A peer wildcard is never evidence for one specific DM.
// Conflicting agents in the winning tier are ambiguous and fail closed.
//
// CTR-215: an account allowFrom that contains a wildcard authorizes nothing on
// its own. Automatic derivation still fails closed with
// ACCOUNT_ALLOWLIST_WILDCARD. An explicit binding may pass exact numeric
// senderIds; each must already be enumerated in that account's own allowFrom,
// and (because the wildcard proves no identity) the binding must name exactly
// one of them, equal to the conversation. The wildcard never becomes a Council
// permission and never authorizes a sender that is not enumerated.
//
// Legacy scalar match.peer is not a route in OpenClaw 2026.10.8
// (normalizePeerConstraint requires a kind), so it proves nothing here.

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizeAccountId(value) {
  return text(value).toLowerCase() || "default";
}

function normalizeAgentId(value) {
  return text(value).toLowerCase();
}

function isWildcard(value) {
  const s = String(value).trim().toLowerCase();
  return s === "*" || s === "all" || s === "any" || s.includes("*");
}

function peerConstraint(match) {
  const peer = match?.peer;
  if (peer === undefined || peer === null) return { state: "none" };
  if (!isPlainObject(peer)) return { state: "invalid" };
  const kind = text(peer.kind).toLowerCase();
  const id = typeof peer.id === "number" || typeof peer.id === "bigint"
    ? String(peer.id).trim()
    : text(peer.id);
  if (!kind || !id) return { state: "invalid" };
  if (id === "*") return { state: "wildcard", kind };
  return { state: "exact", kind, id };
}

function isDirectKind(kind) {
  // Same normalization OpenClaw applies: "dm" -> direct; "private" is not a
  // recognized chat type there and is therefore not proof of a DM router here.
  return kind === "direct" || kind === "dm";
}

function accountMatches(rawAccountId, accountId) {
  const pattern = text(rawAccountId);
  if (pattern === "*") return true;
  return normalizeAccountId(pattern) === normalizeAccountId(accountId);
}

// A DM scope has no guild, team or member roles, so a binding carrying any of
// those constraints cannot win for it.
function isDmScopeBinding(match) {
  if (text(match.guildId) || text(match.teamId)) return false;
  if (Array.isArray(match.roles) && match.roles.length > 0) return false;
  return true;
}

function tierOf(match, conversationId) {
  const peer = peerConstraint(match);
  if (peer.state === "exact") {
    return isDirectKind(peer.kind) && peer.id === conversationId ? "binding.peer" : null;
  }
  if (peer.state === "wildcard") {
    return isDirectKind(peer.kind) ? "binding.peer.wildcard" : null;
  }
  if (peer.state === "invalid") return null;
  return text(match.accountId) === "*" ? "binding.channel" : "binding.account";
}

const TIERS = ["binding.peer", "binding.peer.wildcard", "binding.account", "binding.channel"];

function stringList(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const item of value) {
    if (typeof item !== "string") continue;
    const trimmed = item.trim();
    if (trimmed && !out.includes(trimmed)) out.push(trimmed);
  }
  return out;
}

export function isWildcardEntry(entry) {
  const s = String(entry).trim().toLowerCase();
  return s === "*" || s === "all" || s === "any" || s.includes("*");
}

function isNumericSenderId(value) {
  return /^[0-9]+$/.test(String(value));
}

/**
 * The authorized sender set for one account, shared by provision and the
 * existing-entry validator so both classify identically.
 *
 * On its own, the account's allowFrom is the only authorization source: a
 * wildcard entry is never expanded and an empty list authorizes nobody. An
 * explicit binding list may narrow that set; every id must already be an exact
 * enumerated allowFrom entry, must be a numeric sender id, must carry no
 * wildcard, and must contain the conversation. When the account allowFrom has a
 * wildcard, only the single enumerated id equal to the conversation is allowed.
 *
 * Returns { ok: true, senderIds, source } or { ok: false, code, detail }.
 */
export function authorizedSenderSelection(account, explicitSenderIds, conversationId) {
  const entries = stringList(account?.allowFrom);
  const chatId = text(conversationId);
  if (entries.length === 0) {
    return { ok: false, code: "NO_AUTHORIZED_SENDERS", detail: "allowFrom is empty or missing" };
  }
  const hasWildcard = entries.some(isWildcardEntry);
  const explicit = stringList(explicitSenderIds);

  if (explicit.length === 0) {
    // Automatic derivation never reads a wildcard as permission.
    if (hasWildcard) {
      return { ok: false, code: "ACCOUNT_ALLOWLIST_WILDCARD", detail: "allowFrom contains a wildcard entry" };
    }
    if (!chatId || !entries.includes(chatId)) {
      return { ok: false, code: "CONVERSATION_NOT_AUTHORIZED", detail: `conversation ${chatId || "(none)"} is not in allowFrom` };
    }
    return { ok: true, senderIds: entries, source: "allowFrom" };
  }

  // Explicit narrow binding: exact enumerated ids only, never a pattern.
  if (explicit.some(isWildcardEntry)) {
    return { ok: false, code: "BINDING_SENDER_WILDCARD", detail: "binding senderIds contains a wildcard entry" };
  }
  const notNumeric = explicit.filter((id) => !isNumericSenderId(id));
  if (notNumeric.length > 0) {
    return { ok: false, code: "BINDING_SENDER_NOT_NUMERIC", detail: `binding senderIds are not numeric sender ids: ${notNumeric.join(", ")}` };
  }
  const outside = explicit.filter((id) => !entries.includes(id));
  if (outside.length > 0) {
    return { ok: false, code: "BINDING_SENDER_NOT_AUTHORIZED", detail: `binding senderIds not enumerated in allowFrom: ${outside.join(", ")}`, outside };
  }
  if (!chatId || !explicit.includes(chatId)) {
    return { ok: false, code: "BINDING_CONVERSATION_NOT_ENUMERATED", detail: `conversation ${chatId || "(none)"} is not one of the enumerated binding senderIds` };
  }
  if (hasWildcard && !(explicit.length === 1 && explicit[0] === chatId)) {
    return {
      ok: false,
      code: "BINDING_SENDER_NOT_EXACT",
      detail: `allowFrom contains a wildcard, so the binding must enumerate exactly one sender id equal to conversation ${chatId}`,
    };
  }
  return { ok: true, senderIds: explicit, source: "binding" };
}

export function resolveCouncilBinding({ cfg, channel, accountId, conversationId, agentId, senderIds }) {
  const channelId = text(channel).toLowerCase();
  const chatId = text(conversationId);
  const wantedAgent = normalizeAgentId(agentId);
  if (!channelId || !chatId || !wantedAgent) {
    return { ok: false, code: "BINDING_INPUT_INCOMPLETE", detail: "channel, accountId, conversationId and agentId are required" };
  }

  const accounts = isPlainObject(cfg?.channels?.telegram?.accounts) ? cfg.channels.telegram.accounts : {};
  // OpenClaw resolves the account id through normalizeAccountId (trim, lower,
  // or "default"). Match that normalization here so a differently-cased config
  // key cannot turn a real route into a false negative.
  const wantedAccount = normalizeAccountId(accountId);
  const accountKey = Object.keys(accounts).find((key) => normalizeAccountId(key) === wantedAccount);
  const account = accountKey === undefined ? undefined : accounts[accountKey];
  if (!isPlainObject(account)) {
    return { ok: false, code: "ACCOUNT_NOT_FOUND", detail: `telegram account ${text(accountId) || "(none)"} does not exist` };
  }
  if (account.enabled === false) {
    return { ok: false, code: "ACCOUNT_DISABLED", detail: `telegram account ${text(accountId)} is disabled` };
  }
  const selection = authorizedSenderSelection(account, senderIds, chatId);
  if (!selection.ok) {
    return { ok: false, code: selection.code, detail: `telegram account ${text(accountId)}: ${selection.detail}` };
  }

  const bindings = (Array.isArray(cfg?.bindings) ? cfg.bindings : [])
    .filter((binding) => isPlainObject(binding) && binding.type !== "acp" && isPlainObject(binding.match))
    .filter((binding) => text(binding.match.channel).toLowerCase() === channelId)
    .filter((binding) => accountMatches(binding.match.accountId, accountId))
    .filter((binding) => isDmScopeBinding(binding.match));

  for (const tier of TIERS) {
    const agents = [...new Set(bindings
      .filter((binding) => tierOf(binding.match, chatId) === tier)
      .map((binding) => normalizeAgentId(binding.agentId))
      .filter(Boolean))];
    if (agents.length === 0) continue;
    if (tier === "binding.peer.wildcard") {
      return {
        ok: false,
        code: "BINDING_PEER_WILDCARD_UNSAFE",
        detail: `conversation ${chatId} is covered only by a direct peer wildcard for ${agents.join(", ")}`,
      };
    }
    if (agents.length > 1) {
      return {
        ok: false,
        code: "BINDING_ROUTE_AMBIGUOUS",
        detail: `conversation ${chatId} matches ${agents.length} agents at ${tier}: ${agents.join(", ")}`,
      };
    }
    if (agents[0] !== wantedAgent) {
      return {
        ok: false,
        code: "BINDING_ROUTE_OTHER_AGENT",
        detail: `conversation ${chatId} resolves to ${agents[0]} at ${tier}, not ${wantedAgent}`,
      };
    }
    return { ok: true, agentId: agents[0], matchedBy: tier };
  }

  return {
    ok: false,
    code: "BINDING_ROUTE_UNRESOLVED",
    detail: `conversation ${chatId} has no telegram route for ${wantedAgent}`,
  };
}
