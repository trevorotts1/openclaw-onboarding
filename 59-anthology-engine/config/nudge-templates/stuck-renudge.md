<!--
  SANCTIONED CLIENT-FACING TEMPLATE: stuck-renudge
  The ONLY copy the engine may send as the single automatic re-nudge at 7 days
  stuck (deduped). All other repeats are manual via the board re-send button.
  Filled by nudge_send.py from the ledger row; recipient resolved from the ledger,
  never a literal address. Zero em dash characters, zero code fences, no internal
  tool or model names. The {{slots}} are resolved at send time by the client-clean
  serializer.
-->
Subject: A friendly reminder about {{anthology_name}}

Hi {{first_name}},

Just a gentle nudge that your {{deliverable_label}} is still waiting for you whenever you are ready.

Here is the link again:

{{gate_link}}

No rush at all. Your place is saved and nothing is lost. If now is not a good time, you can come back to it later.

Thank you again for being part of {{anthology_name}}.

Warmly,
{{producer_display_name}}
