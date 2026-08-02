#!/usr/bin/env node
// AF-AW-ENTRY-BYPASS negative fixture — a hand-rolled external Slack sender.
// The Anthology Writer delivers LOCAL-ONLY; fetch to slack.com/api must trip exit 5.
const notify = async (message) => {
  const res = await fetch('https://slack.com/api/chat.postMessage', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ channel: '#anthology-complete', text: message })
  });
  return res.json();
};
module.exports = { notify };
