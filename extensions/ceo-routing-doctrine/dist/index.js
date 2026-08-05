// ceo-routing-doctrine — CEO Routing Doctrine via prompt pre-injection.
//
// Replaces the removed CEO gate (a hard tool-deny that caused the memoryFlush
// write-denial loop). This plugin injects the routing doctrine as a system-context
// preamble on EVERY agent turn via the before_prompt_build hook. It denies nothing,
// so no write-denial loop can form. It honors an explicit human override.
//
// Wiring precedent: ~/.openclaw/extensions/openclaw-mem0/dist/index.js uses
// api.on("before_prompt_build", ...) returning { prependSystemContext }.
//
// gated by: plugins.entries.<id>.hooks.allowPromptInjection (OpenClaw 2026.7.1-2).

'use strict';

const ROUTING_PREAMBLE = [
  '## CEO Routing Doctrine (injected policy — apply this turn)',
  '',
  'You are the CEO/router agent. Your default mode is to ROUTE work, not self-execute:',
  '- For a task you are equipped to delegate, route it via the ingest/routing path',
  '  (POST /api/tasks/ingest, or the mc-route / route-presentation helper) to the',
  '  department specialist who executes. You coordinate and route; the specialist does.',
  '- Do NOT self-execute production work as a matter of course.',
  '',
  '## HUMAN OVERRIDE — honor it without question',
  '- If the human (owner) explicitly says they want YOU to do the work personally —',
  '  e.g. "I want you to personally do this", "you take care of this yourself",',
  '  "I want you to handle it", "do it yourself", or any clear personal-assignment',
  '  intent — then ROUTE IS OVERRIDDEN: you may and should do that work directly.',
  '  The override applies to the specific task(s) the owner assigned to you personally.',
  '- The override does not revoke your judgment: for anything the owner did NOT',
  '  personally assign, keep the default route-not-self-execute behavior.',
  '',
  'This is an instruction layer, not a permission wall. You retain all your tools.',
  'The point is behavior: route by default, execute when personally asked.',
].join('\n');

let logger = null;

module.exports = (api) => {
  try {
    if (api && typeof api.getSystemLogger === 'function') {
      logger = api.getSystemLogger();
    }
  } catch (_e) { /* no logger */ }

  api.on('before_prompt_build', async (_event, _ctx) => {
    try {
      if (logger && logger.debug) logger.debug('[ceo-routing-doctrine] injecting routing preamble');
    } catch (_e) { /* ignore */ }
    return {
      prependSystemContext: ROUTING_PREAMBLE,
    };
  });
};
