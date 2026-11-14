# backend/app/questions/answer_forms.py
"""Maths answer forms: compare what a student types with keys written in LaTeX,
and work out which symbol keys the student needs to type an answer.

Students type plain text from the on-screen keypad ("1/2π", "√3", "x^2");
answer keys may be written in LaTeX ("\\frac{1}{2}\\pi"). Both are reduced to
one canonical plain form before comparing. Multiples of π are also compared
by value, so "1/2π", "π/2" and "0.5π" are the same answer.
"""

from __future__ import annotations

import re
from fractions import Fraction

PI = "\u03c0"
ROOT = "\u221a"
TIMES = "\u00d7"  # multiplication sign, not the letter x

# LaTeX commands with a plain-text equivalent. Order matters: longer first.
_TEX_SYMBOLS: tuple[tuple[str, str], ...] = (
    (r"\times", TIMES),
    (r"\cdot", TIMES),
    (r"\div", "÷"),
    (r"\pi", PI),
    (r"\leq", "≤"),
    (r"\geq", "≥"),
    (r"\le", "≤"),
    (r"\ge", "≥"),
    (r"\neq", "≠"),
    (r"\circ", "°"),
    (r"\degree", "°"),
    (r"\%", "%"),
    (r"\left", ""),
    (r"\right", ""),
    (r"\,", ""),
    (r"\;", ""),
    (r"\!", ""),
)
_FRAC = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_SQRT = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_BRACED_POWER = re.compile(r"\^\s*\{([^{}]*)\}")
_SUPERSCRIPTS = {"²": "^2", "³": "^3"}
_SIMPLE_TOKEN = re.compile(r"^[\w.\u03c0]+$")
_NUMBER = re.compile(r"^-?(?:\d+(?:\.\d+)?|\.\d+)(?:/(?:\d+(?:\.\d+)?))?$")


def _group(token: str) -> str:
    """Bracket a fraction part unless it's a single number or letter group."""
    return token if _SIMPLE_TOKEN.match(token) else f"({token})"


def tex_to_plain(value: str) -> str:
    """Rewrite common LaTeX as the plain text a student would type.

    ``\\frac{1}{2}\\pi`` → ``1/2π``; ``\\sqrt{3}`` → ``√3``; ``x^{2}`` → ``x^2``.
    Text without LaTeX is returned unchanged (apart from ``$`` delimiters).
    """
    text = value.replace("$", "")
    for _ in range(5):  # nested fractions/roots, bounded
        replaced = _FRAC.sub(lambda m: f"{_group(m[1].strip())}/{_group(m[2].strip())}", text)
        replaced = _SQRT.sub(lambda m: f"{ROOT}{_group(m[1].strip())}", replaced)
        replaced = _BRACED_POWER.sub(lambda m: f"^{_group(m[1].strip())}", replaced)
        if replaced == text:
            break
        text = replaced
    for tex, plain in _TEX_SYMBOLS:
        text = text.replace(tex, plain)
    return text


def canonical(value: str) -> str:
    """One comparable form: plain text, no spaces, case-folded, standard symbols."""
    text = tex_to_plain(value).casefold()
    for sup, plain in _SUPERSCRIPTS.items():
        text = text.replace(sup, plain)
    text = text.replace("\u2212", "-").replace("*", TIMES)
    text = re.sub(r"\bpi\b", PI, text)
    return re.sub(r"\s+", "", text)


def _number(text: str) -> Fraction | None:
    if not _NUMBER.match(text):
        return None
    top, _, bottom = text.partition("/")
    denominator = Fraction(bottom) if bottom else Fraction(1)
    return Fraction(top) / denominator if denominator else None


def pi_multiple(value: str) -> Fraction | None:
    """The coefficient ``k`` when the answer is ``kπ`` (e.g. "π/2" → 1/2), else ``None``."""
    text = canonical(value)
    if text.count(PI) != 1:
        return None
    # "(2π)/3" → "2π/3"
    bracketed = re.match(r"^\(([^()]*)\)(/[^()]*)?$", text)
    if bracketed and PI in bracketed[1]:
        text = bracketed[1] + (bracketed[2] or "")
    left, right = text.split(PI)
    left = left.removeprefix("(").removesuffix(")") if left.startswith("(") else left
    left = left.removesuffix(TIMES)
    if left in ("", "-"):
        coefficient: Fraction | None = Fraction(-1 if left == "-" else 1)
    else:
        coefficient = _number(left)
    if coefficient is None:
        return None
    if right:
        divisor = _number(right.removeprefix("/")) if right.startswith("/") else None
        if not divisor:
            return None
        coefficient /= divisor
    return coefficient


def same_maths(given: str, expected: str) -> bool:
    """Whether two maths answers are the same, allowing LaTeX keys and π multiples."""
    a, b = canonical(given), canonical(expected)
    if not a or not b:
        return False
    if a == b:
        return True
    pa, pb = pi_multiple(given), pi_multiple(expected)
    if pa is not None and pb is not None:
        return pa == pb
    na, nb = _number(a), _number(b)
    return na is not None and nb is not None and na == nb


def display_answer(value: str) -> str:
    """Show a LaTeX answer key as maths: wrap it in ``$...$`` if it isn't already."""
    return f"${value}$" if "\\" in value and "$" not in value else value


# Symbol keys the keypad can offer, in display order. Digits, ".", "/" and "-"
# are always on the keypad.
KEYPAD_SYMBOLS: tuple[str, ...] = (
    PI,
    ROOT,
    "^",
    "(",
    ")",
    ":",
    "%",
    "°",
    TIMES,
    "÷",
    "=",
    "<",
    ">",
    "≤",
    "≥",
)
# Offered on every maths short answer, so the keys don't give the answer's form away.
STANDARD_SYMBOLS: frozenset[str] = frozenset({PI, ROOT, "^", "(", ")"})
_MATHS_CHARS = re.compile(
    r"^[0-9a-z.,/\-+" + "".join(re.escape(s) for s in KEYPAD_SYMBOLS) + r"]+$"
)
_WORD = re.compile(r"[a-z]{2,}")


def is_maths_answer(value: str) -> bool:
    """True for answers like "1/2π", "3x+2", "2:3"; false for words like "prime"."""
    text = canonical(value)
    return bool(text) and bool(_MATHS_CHARS.match(text)) and not _WORD.search(text)


def keypad_symbols(accepted: list[str]) -> list[str]:
    """Symbol keys needed to type these answers, plus the standard maths set.

    Single letters used as variables ("x", "n") are included as keys too.
    """
    needed: set[str] = set(STANDARD_SYMBOLS)
    letters: set[str] = set()
    for answer in accepted:
        text = canonical(answer)
        needed.update(s for s in KEYPAD_SYMBOLS if s in text)
        letters.update(re.findall(r"[a-z]", text))
    return [s for s in KEYPAD_SYMBOLS if s in needed] + sorted(letters)
