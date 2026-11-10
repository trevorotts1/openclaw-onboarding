"""Compile ordered mixed quiz questions using captured empty-page writers.

Each batch keeps its own runner intent and Save/reopen receipt. No native page
identity, question key or property default is inferred from an earlier result.
The caller supplies the full expected inventory at every boundary, and this
compiler proves that those inventories describe one continuous authored plan.
"""
from copy import deepcopy

if __package__:
    from .skill6_playwright import Stop
else:
    from skill6_playwright import Stop


def compile_batches(data):
    from playwright_recipes.intake import QUIZ_CREATION, quiz_creation

    config = data.get('configuration')
    if not isinstance(config, dict) or 'question_batches' not in config:
        return None
    if set(config) != {'question_batches'} or 'options' in data:
        raise Stop('Mixed quiz questions require an exclusive ordered question-batch job')
    batches = config['question_batches']
    if not isinstance(batches, list) or not 2 <= len(batches) <= 50:
        raise Stop('Mixed quiz authoring requires two to fifty explicit question batches')
    result = []
    expected_pages = None
    quiz_name = None
    for index, batch in enumerate(batches):
        if (not isinstance(batch, dict) or len(batch) != 1
                or not set(batch).issubset(QUIZ_CREATION)):
            raise Stop('Every quiz batch requires one captured question-writer request')
        # The complete-inventory written writer authors the same captured
        # Short Answer tile and can preserve preceding choice/picture owners.
        # The legacy single-type writer remains available outside mixed jobs.
        compiled = deepcopy(batch)
        if 'short_answer_questions' in compiled:
            short = compiled['short_answer_questions']
            if (not isinstance(short, dict) or not isinstance(short.get('questions'), list)
                    or any(not isinstance(question, dict) or question.get('field_type') != 'TEXT'
                           for question in short['questions'])):
                raise Stop('Short Answer batches require captured TEXT questions')
            compiled = {'written_answer_questions': short}
        request = {**data, 'configuration': compiled}
        action, payload = quiz_creation(request)
        if len(payload['questions']) != 1:
            raise Stop('Mixed quiz batches author exactly one question per confirmed empty page')
        if index and (payload['expected_quiz_name'] != quiz_name or payload['pages'] != expected_pages):
            raise Stop('Quiz batch inventory must exactly retain every earlier page and authored question')
        if not payload.get('create_page') and (index or payload['pages'][payload['target_page'] - 1]['questions']):
            raise Stop('Mixed quiz batches require an existing empty first page and explicit new pages thereafter')
        quiz_name = payload['expected_quiz_name']
        expected_pages = deepcopy(payload['pages'])
        if payload.get('create_page'):
            expected_pages.append({'label': payload['new_page_label'], 'questions': []})
        authored = deepcopy(payload['questions'])
        if action == 'quiz_picture_choices':
            from playwright_recipes.quiz_picture_questions import _authored
            authored = [_authored(question) for question in authored]
        expected_pages[payload['target_page'] - 1]['questions'].extend(authored)
        result.append((action, payload))
    return result
