<!--
  SANCTIONED CLIENT-FACING TEMPLATE: gate-open
  The ONLY copy the engine may send when a gate opens. Filled by nudge_send.py
  from the ledger row; the recipient is resolved from the ledger for the given
  contact_id (participant gates) or the producer record (producer gates), never a
  literal address. Zero em dash characters, zero code fences, no internal tool or
  model names. The {{slots}} are resolved at send time by the client-clean
  serializer. Deep link points to the board card (producer) or the participant
  token page (participant), same endpoint behind both doors.
-->
Subject: Your next step on {{anthology_name}} is ready

Hi {{first_name}},

Your {{deliverable_label}} is ready for you to review.

Please open the link below to take a look and choose your next step:

{{gate_link}}

It only takes a couple of minutes, and there is no deadline. Your place is saved, so you can come back whenever the timing is right for you.

Thank you for being part of {{anthology_name}}.

Warmly,
{{producer_display_name}}
