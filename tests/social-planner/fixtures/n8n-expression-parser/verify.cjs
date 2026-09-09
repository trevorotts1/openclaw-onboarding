'use strict';
// Compile the complete n8n parameter expression, including {{ }} delimiters.
// Node vm alone misses Tournament's delimiter splitting and accepts invalid
// nested adjacent braces. Code-node bodies are JavaScript, not expressions.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { Tournament } = require('@n8n/tournament');
const parser = new Tournament((error) => { throw error; });
const root = path.resolve(__dirname, '../../../..');
const directory = path.join(root, '35-social-media-planner/config/n8n');
const failures = [];
let checked = 0;
function compile(expression) {
  return parser.getExpressionCode(expression.startsWith('=') ? expression.slice(1) : expression);
}
function visit(value, location) {
  if (typeof value === 'string' && value.startsWith('=')) {
    checked += 1;
    try { compile(value); }
    catch (error) { failures.push({ location, error: error.message }); }
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const [key, entry] of Object.entries(value)) {
    if (key === 'jsCode' || key === 'functionCode') continue;
    visit(entry, `${location}.${key}`);
  }
}
for (const name of fs.readdirSync(directory).filter((file) => file.endsWith('.json')).sort()) {
  const workflow = JSON.parse(fs.readFileSync(path.join(directory, name), 'utf8'));
  if (!Array.isArray(workflow.nodes)) continue;
  for (const node of workflow.nodes) visit(node.parameters, `${name}:${node.name}`);
}
// Prove this suite detects the exact failure Node VM didn't catch. The
// first inner }} closes Tournament's interpolation before JavaScript ends.
assert.throws(() => compile("={{ JSON.stringify({appProperties:{state:'ready'}}) }}"), /Unexpected end|syntax/i);
const safe = "={{ JSON.stringify({appProperties:{state:'ready'} }) }}";
assert.doesNotThrow(() => compile(safe));
assert.equal(parser.execute(safe.slice(1), { JSON }), '{"appProperties":{"state":"ready"}}');
// IIFEs themselves are supported: don't misdiagnose the arrow as the cause.
const safeIife = "={{ (()=>{const src={name:'Fixture'};return JSON.stringify({name:src.name,appProperties:{state:'initializing'} });})() }}";
assert.doesNotThrow(() => compile(safeIife));
assert.equal(JSON.parse(parser.execute(safeIife.slice(1), { JSON })).appProperties.state, 'initializing');
assert.ok(checked > 0, 'No real export expressions checked');
const result = { parser: '@n8n/tournament@1.10.1', checked, regressionAssertions: 6, failures, passed: failures.length === 0 };
console.log(JSON.stringify(result, null, 2));
if (failures.length) process.exitCode = 1;
