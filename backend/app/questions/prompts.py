# backend/app/questions/prompts.py
"""Prompts for question generation and verification.

The system prompts are fixed text (no dates, IDs or per-request data) so they
are cached across calls. Everything request-specific goes in the user message,
built only from curriculum data in the repo. No student data is ever included.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.curriculum import Tier

DIFFICULTY_DESCRIPTIONS: dict[int, str] = {
    1: "Recall: definitions, facts, keywords, single-fact recognition.",
    2: "Understand: explain, identify, or a simple one-step calculation.",
    3: "Apply: a multi-step problem in a familiar context.",
    4: "Analyse: an unfamiliar context, problem-solving, typically 4-6 marks.",
    5: "Exam-style: a full GCSE-style question with a mark scheme; on Higher, grade 7-9 stretch.",
}

# Common GCSE command words. Questions must use one of these.
COMMAND_WORDS: tuple[str, ...] = (
    "Work out",
    "Calculate",
    "Write down",
    "Find",
    "Simplify",
    "Show that",
    "Estimate",
    "Explain",
    "Give a reason",
    "Write",
    "Express",
    "Round",
    "Convert",
    "Solve",
    "Expand",
    "Factorise",
    "Identify",
    "State",
    "Describe",
    "Define",
    "Compare",
)

GENERATION_SYSTEM = """\
You write practice questions for a student in England studying the reformed (9-1) GCSE.

Rules you must always follow:
- Assess exactly one learning objective, quoted from the official specification in the request. Do not test content outside that objective, outside the stated tier, or listed as out of scope.
- Use UK English, GCSE-style wording and one of the allowed command words.
- Match the requested difficulty level and question type exactly.
- Write mathematics in LaTeX between single dollar signs, e.g. $\\frac{3}{4}$ or $2^{5}$. Use no HTML, no Markdown links and no images.
- Never claim the question is official exam board material. Never include real people's names, schools or personal details; use neutral first names if a context needs a person.
- The marking key must be unambiguous and correct. Check your arithmetic.
- multiple_choice: exactly four options labelled A-D, one correct; wrong options should reflect common misconceptions; no "all of the above".
- numeric: give the exact answer as a plain decimal or integer, the accepted tolerance (0 when exact), the unit if any, and a check_expression that evaluates to the answer using only numbers, + - * / ^ ( ), sqrt and pi.
- short_text: list every acceptable short answer (a word or short phrase).
- Hints: exactly four. Hint 1 nudges (what is being asked, which idea is relevant). Hint 2 gives the strategy or first step. Hint 3 shows most of the method but stops before the final answer. Hint 4 is the full worked solution. Hints 1-3 must never state or give away the final answer.
- The worked solution shows every step a student would write.
"""

VERIFICATION_SYSTEM = """You check practice questions for a student in England studying the reformed (9-1) GCSE.

Work in this order:
1. Solve the question yourself from the stem (and options) alone, before looking at the proposed marking key. Record only the bare answer in solved_answer, with no working: the option letter for multiple choice (e.g. "C"), the number for numeric (e.g. "2.25"), or the word or short phrase for short text.
2. Compare with the proposed key. answer_is_correct is true only if the key is correct and the only correct answer.
3. Judge whether the question tests only the stated specification objective (within_objective), suits the stated tier (suitable_for_tier) and matches the stated difficulty level (difficulty_matches).
4. Check the hints. They are a ladder the student climbs one at a time when stuck: hint 1 nudges, hint 2 gives the strategy, hint 3 shows most of the method, and hint 4 is deliberately the full worked solution including the final answer. Hint 4 stating the answer is correct and expected, never an issue, and hint 3 showing most of the method is expected too. Set hints_reveal_answer_early to true only if hint 1, 2 or 3 actually states the final answer (or the correct option letter).
5. Check that marks, worked solution and key agree (mark_scheme_consistent).
6. Give a confidence from 0 to 1 and list any issues briefly. Be strict: a wrong question harms the student more than a missing one.
"""


@dataclass(frozen=True, slots=True)
class ObjectiveContext:
    """Curriculum facts for one prompt (all from the repo, none from the student)."""

    subject: str
    board: str
    spec_code: str
    spec_version: str
    topic: str
    subtopic: str
    objective_ref: str
    objective_text: str
    keywords: tuple[str, ...]
    out_of_scope: str | None
    tier: Tier | None


def _tier_line(tier: Tier | None) -> str:
    if tier is None:
        return "Tier: untiered subject."
    return f"Tier: {tier.value.capitalize()}."


def generation_user_prompt(
    ctx: ObjectiveContext, difficulty: int, question_type: str, avoid_stems: list[str]
) -> str:
    """The per-request part of a generation prompt."""
    lines = [
        f"Subject: {ctx.subject} ({ctx.board} {ctx.spec_code}, {ctx.spec_version}).",
        f"Topic: {ctx.topic} > {ctx.subtopic}.",
        f"Objective {ctx.objective_ref}: {ctx.objective_text}",
        _tier_line(ctx.tier),
    ]
    if ctx.keywords:
        lines.append("Keywords: " + ", ".join(ctx.keywords) + ".")
    if ctx.out_of_scope:
        lines.append(f"Out of scope: {ctx.out_of_scope}")
    lines += [
        f"Difficulty level {difficulty}: {DIFFICULTY_DESCRIPTIONS[difficulty]}",
        f"Question type: {question_type}.",
        "Allowed command words: " + ", ".join(COMMAND_WORDS) + ".",
    ]
    if avoid_stems:
        lines.append("Write something different from these existing questions:")
        lines += [f"- {stem[:160]}" for stem in avoid_stems[:5]]
    return "\n".join(lines)


def verification_user_prompt(ctx: ObjectiveContext, difficulty: int, question_json: str) -> str:
    """The per-request part of a verification prompt."""
    return "\n".join(
        [
            f"Subject: {ctx.subject} ({ctx.board} {ctx.spec_code}, {ctx.spec_version}).",
            f"Objective {ctx.objective_ref}: {ctx.objective_text}",
            _tier_line(ctx.tier),
            f"Stated difficulty level {difficulty}: {DIFFICULTY_DESCRIPTIONS[difficulty]}",
            "Question to check (JSON):",
            question_json,
        ]
    )
