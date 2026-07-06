"""Alias tables and known-container list for the deterministic mapper.

Seeded verbatim from design/webhook-design.md Section 4.2 step 2 and the
Convert and Flow field-map facts in design/ghl-design.md (the double-underscore
additional-info key, the podcast_survey_writing_style selector, the
podcast_interview_smiq transparency field). Onboarding extends these per client
when a real upstream payload is inspected; the tests exercise the seeded set.

No language model is involved anywhere in mapping. Determinism here is what makes
the canonical hash stable, and a stable hash is what makes dedup real.
"""

# Containers the mapper flattens, in the order it searches them (Section 4.2 step 1).
# "contact" and "location" are ALSO id-sensitive: their sub-keys are surfaced in
# dotted form (contact.id, contact.first_name, location.id) so that a bare "id"
# is only ever read as a contact id when it genuinely sits inside a contact object.
KNOWN_CONTAINERS = ["customData", "data", "body", "payload", "contact", "fields", "answers"]
DOTTED_CONTAINERS = ["contact", "location"]

# field -> ordered alias keys. First hit wins per field (exact pass, then fuzzy pass).
ALIASES = {
    "contact_id": ["contact_id", "contactId", "contact.id"],
    "location_id": ["location_id", "locationId", "location.id"],
    "podcast_id": ["podcast_id", "podcastId", "podbean_podcast_id"],
    "mode": ["mode", "production_mode", "productionMode", "podcast_mode", "podcast_type"],
    "style": [
        "style",
        "presentation_style",
        "presentationStyle",
        "writing_style",
        "podcast_survey_writing_style",
        "select_your_presentation_style_personal_podcast",
    ],
    "preferred_pronoun": ["preferred_pronoun", "my_preferred_pronoun", "pronoun", "pronouns"],
    "first_name": ["first_name", "firstName", "contact.first_name"],
    "last_name": ["last_name", "lastName", "contact.last_name"],
    "show_name": ["show_name", "showName", "podcast_show_name"],
    "host_name": ["host_name", "hostName", "podcast_host_name"],
    "additional_info": ["additional_info", "podcast_survey__additional_info", "additional_information"],
    "publish_timestamp": ["publish_timestamp", "publishTimestamp", "publish_date", "date_for_release"],
    "target_runtime": ["target_runtime", "targetRuntime", "runtime"],
    "tts_model": ["tts_model", "ttsModel", "voice_model"],
    "writing_model": ["writing_model", "writingModel"],
    "web_research_tool": ["web_research_tool", "webResearchTool", "research_tool"],
    "episode_type": ["episode_type", "episodeType"],
    "explicit": ["explicit", "is_explicit"],
    "workflow_trigger": ["workflow_trigger", "workflowTrigger"],
    # layer-local extras (Sections 3.3 and 8); carried on the canonical record but
    # deliberately excluded from the job-key hash (see job_key.HASH_FIELDS).
    "retry": ["retry", "operator_retry"],
    "_test": ["_test", "test_flag", "is_test"],
    "q1_answer": ["q1_answer", "q1", "question_1", "answer_1"],
    "q2_answer": ["q2_answer", "q2", "question_2", "answer_2"],
    "q3_answer": ["q3_answer", "q3", "question_3", "answer_3"],
    "q4_answer": ["q4_answer", "q4", "question_4", "answer_4"],
    "q5_answer": ["q5_answer", "q5", "question_5", "answer_5"],
    "q6_answer": ["q6_answer", "q6", "question_6", "answer_6"],
    "q7_answer": ["q7_answer", "q7", "question_7", "answer_7"],
}

# The transparency answer (SMIQ, the Single Most Important Question) arrives under
# its own aliases and lands in the q-slot dictated by the chosen style's path
# (Section 4.2 step 2, transparency-answer row). The tests use the Counter
# Intuitive path where the transparency beat occupies q5.
TRANSPARENCY_ALIASES = ["podcast_interview_smiq", "smiq", "transparency_answer"]

DEFAULT_STYLE_TRANSPARENCY_SLOT = {
    "counter_intuitive": "q5_answer",
    "vulnerable": "q5_answer",
    "provocative": "q5_answer",
    "passionate": "q5_answer",
}
