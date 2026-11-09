// CTR-127: real plugin `before_dispatch` claim for an authorized explicit
// Council ask. Installed OpenClaw docs/contracts used at this boundary:
//   docs/plugins/hooks/reference.md  — before_dispatch is a Claim hook
//   docs/plugins/hooks/messages.md   — return { handled: true, text }
//   dist/config-contracts-DhkndZxE.d.ts
//     PluginHookBeforeDispatchEvent / Context / Result
//   dist/dispatch-from-config-Bjj9te2c.mjs:816-860 — call site has NO
//     isAuthorizedSender gate, so ./lib/core.mjs enforces the equivalent
//     account + channel + sender + agent/session binding before any spend.
//
// The hook runs before model dispatch and returns the supported front door's
// actual output or typed refusal. It never emits GO/approval text and never
// chooses a provider itself.

import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { classifyInbound, handleInbound, normalizeConfig, renderFailure } from "./lib/core.mjs";

export default definePluginEntry({
  id: "council-before-dispatch",
  name: "Council Before Dispatch",
  description:
    "Runs the supported Council front door for an authorized explicit ask before the model turn.",
  register(api) {
    const parsed = normalizeConfig(api.pluginConfig ?? {});
    if (!parsed.ok) {
      // Fail closed: no registration that could act on a malformed binding.
      api.logger.error(`[council-before-dispatch] disabled: ${parsed.reason}`);
      return;
    }
    const config = parsed.config;

    api.on(
      "before_dispatch",
      async (event, ctx) => {
        try {
          return await handleInbound({ event, ctx, config, deps: { logger: api.logger } });
        } catch (error) {
          api.logger.error(`[council-before-dispatch] handler fault: ${String(error?.message ?? error)}`);
          // Narrow, non-blanket recovery. Only a message that IS an authorized
          // explicit ask (or a recognized ask the handler already rejects) is
          // answered here; every unrelated or untrusted message still returns
          // undefined and keeps the normal model path and its own sender
          // authorization. Losing a recognized ask to `undefined` is what lets
          // a model invent approval prose, so it must not happen.
          let recognized = false;
          try {
            const check = classifyInbound({ event, ctx, config });
            recognized = Boolean(check && (check.matched || check.rejected));
          } catch {
            recognized = false;
          }
          if (!recognized) return undefined;
          return {
            handled: true,
            text: renderFailure(
              "COUNCIL_PLUGIN_ERROR",
              String(error?.message ?? error),
              "Read the Gateway log; no Council sitting was started for this message.",
            ),
          };
        }
      },
      { registrationId: "council-before-dispatch" },
    );
  },
});
