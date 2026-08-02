#!/bin/bash
# Hand-rolled external upload to Slack - should trigger AF-AW-ENTRY-BYPASS
echo "Uploading to slack.com..."
curl -X POST "https://slack.com/api/chat.postMessage" \
  -H "Content-Type: application/json" \
  -d '{"channel": "#general", "text": "Anthology complete!"}'
