# backend/app/questions/validation.py
"""Rules a generated question must pass before it's checked or stored.

Returns a problem description (so the gateway can retry) or ``None``.
"""

from __future__ import annotations

import itertools
import re
from decimal import Decimal, InvalidOperation

from app.questions.llm_schemas import GeneratedQuestion
from app.questions.marking import normalise_text, parse_number
from app.questions.prompts import COMMAND_WORDS

MAX_STEM_LENGTH = 1500
MAX_TEXT_LENGTH = 3000
# Anything that looks like an HTML tag. Model output is rendered as text +
# KaTeX only, but reject markup outright rather than rely on escaping alone.
_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_COMMAND_WORDS = {normalise_text(w) for w in COMMAND_WORDS}


def _texts(q: GeneratedQuestion) -> list[str]:
    return [
        q.stem,
        q.worked_solution,
        *q.hints,
        *(o.text for o in q.options),
        *q.accepted_answers,
        *(p.text for p in q.marking_points),
        *(level.descriptor for level in q.level_descriptors),
        q.model_answer or "",
    ]


def _final_answers(q: GeneratedQuestion) -> list[str]:
    """Strings that would give the answer away if they appeared in hints 1-3."""
    if q.question_type == "multiple_choice":
        correct = next((o.text for o in q.options if o.label == q.correct_option), "")
        return [correct] if len(normalise_text(correct)) >= 3 else []
    if q.question_type == "numeric" and q.numeric_answer:
        return [q.numeric_answer]
    if q.question_type == "extended":
        return []  # no single final answer to leak
    return [a for a in q.accepted_answers if len(normalise_text(a)) >= 3]


def _leaks(hint: str, answer: str) -> bool:
    if parse_number(answer) is not None:
        # Whole-number match only: "35" mustn't match inside "3.5" or "135".
        return re.search(rf"(?<![\d.]){re.escape(answer.strip())}(?![\d])", hint) is not None
    return normalise_text(answer) in normalise_text(hint)


def check_generated(q: GeneratedQuestion, expected_type: str) -> str | None:
    """Validate a generated question. Returns a problem, or ``None`` if acceptable."""
    if q.question_type != expected_type:
        return f"expected a {expected_type} question, got {q.question_type}"
    if not q.stem.strip() or len(q.stem) > MAX_STEM_LENGTH:
        return "stem empty or too long"
    if any(len(t) > MAX_TEXT_LENGTH for t in _texts(q)):
        return "a text field is too long"
    if any(_HTML_TAG.search(t) for t in _texts(q)):
        return "contains HTML markup"
    if normalise_text(q.command_word) not in _COMMAND_WORDS:
        return f"command word {q.command_word!r} not allowed"
    low, high = (2, 16) if q.question_type == "extended" else (1, 6)
    if not low <= q.marks <= high:
        return f"marks must be {low}-{high}"
    if len(q.hints) != 4 or any(not h.strip() for h in q.hints):
        return "needs exactly four non-empty hints"

    problem = _check_type_fields(q)
    if problem:
        return problem
    for answer in _final_answers(q):
        if any(_leaks(hint, answer) for hint in q.hints[:3]):
            return "hints 1-3 give away the answer"
    return None


def _check_extended(q: GeneratedQuestion) -> str | None:
    if q.options or q.accepted_answers or q.numeric_answer or q.correct_option:
        return "extended questions have no options, accepted answers or numeric answer"
    if not q.marking_points:
        return "extended questions need marking points"
    if any(p.marks < 1 or p.marks > q.marks for p in q.marking_points):
        return "each marking point needs 1 to the question's marks"
    if any(not re.fullmatch(r"AO[1-4]", p.ao.strip()) for p in q.marking_points):
        return "marking point AO must be AO1-AO4"
    if sum(p.marks for p in q.marking_points) < q.marks:
        return "marking points must add up to at least the marks available"
    if not (q.model_answer or "").strip():
        return "extended questions need a model answer"
    levels = sorted(q.level_descriptors, key=lambda level: level.level)
    if q.marks >= 6 and not levels:
        return "6+ mark questions need level descriptors"
    if levels:
        if levels[0].min_marks != 1 or levels[-1].max_marks != q.marks:
            return "levels must cover 1 to the total marks"
        for lower, upper in itertools.pairwise(levels):
            if upper.min_marks != lower.max_marks + 1:
                return "levels must not overlap or leave gaps"
        if any(level.min_marks > level.max_marks for level in levels):
            return "a level's minimum is above its maximum"
    return None


def _check_type_fields(q: GeneratedQuestion) -> str | None:
    if q.question_type == "extended":
        return _check_extended(q)
    if q.marking_points or q.level_descriptors or q.model_answer:
        return "only extended questions have a mark scheme or model answer"
    if q.question_type == "multiple_choice":
        labels = [o.label for o in q.options]
        if sorted(labels) != ["A", "B", "C", "D"]:
            return "multiple choice needs options A-D"
        if len({normalise_text(o.text) for o in q.options}) != 4:
            return "options must be distinct"
        if q.correct_option not in labels:
            return "correct_option must be one of A-D"
        return None
    if q.question_type == "numeric":
        if q.options or q.accepted_answers:
            return "numeric questions have no options or accepted_answers"
        try:
            Decimal(q.numeric_answer or "")
            tolerance = Decimal(q.numeric_tolerance or "0")
        except InvalidOperation:
            return "numeric_answer and numeric_tolerance must be plain numbers"
        if tolerance < 0:
            return "tolerance can't be negative"
        return None
    if q.options or not q.accepted_answers:
        return "short_text needs accepted_answers and no options"
    if any(len(a) > 80 for a in q.accepted_answers):
        return "accepted answers must be short"
    return None
