// frontend/src/practice/math.ts
// Splitting text into plain and LaTeX parts, and rendering LaTeX safely.
import "katex/dist/katex.min.css";
import katex from "katex";

/** A run of plain text, or a LaTeX expression that was between `$...$`. */
export type Segment = { kind: "text"; value: string } | { kind: "math"; value: string };

/**
 * Split text on `$...$` delimiters. `\$` is a literal dollar sign. An
 * unmatched `$` is treated as text, so malformed input still displays.
 */
export function splitMath(input: string): Segment[] {
  const segments: Segment[] = [];
  let text = "";
  let i = 0;
  while (i < input.length) {
    const char = input.charAt(i);
    if (char === "\\" && input[i + 1] === "$") {
      text += "$";
      i += 2;
      continue;
    }
    if (char === "$") {
      const end = input.indexOf("$", i + 1);
      if (end > i + 1) {
        if (text) segments.push({ kind: "text", value: text });
        segments.push({ kind: "math", value: input.slice(i + 1, end) });
        text = "";
        i = end + 1;
        continue;
      }
    }
    text += char;
    i += 1;
  }
  if (text) segments.push({ kind: "text", value: text });
  return segments;
}

/** A piece of rendered text: plain text, or maths with any punctuation glued after it. */
export type Piece =
  { kind: "text"; value: string } | { kind: "math"; value: string; after: string };

const TRAILING_PUNCTUATION = /^[.,;:!?)%]+/;

/**
 * Attach punctuation that directly follows a maths segment ("$x$." → math + ".")
 * so the full stop can't wrap onto its own line or sit apart from the maths.
 */
export function toPieces(segments: Segment[]): Piece[] {
  const pieces: Piece[] = [];
  for (let i = 0; i < segments.length; i += 1) {
    const segment = segments[i];
    if (segment === undefined) continue;
    if (segment.kind === "text") {
      pieces.push(segment);
      continue;
    }
    const next = segments[i + 1];
    const after = next?.kind === "text" ? (TRAILING_PUNCTUATION.exec(next.value)?.[0] ?? "") : "";
    pieces.push({ kind: "math", value: segment.value, after });
    if (next?.kind === "text" && after) {
      const rest = next.value.slice(after.length);
      if (rest) pieces.push({ kind: "text", value: rest });
      i += 1;
    }
  }
  return pieces;
}

/** U+202F: a narrow no-break space, as used to group digits in printed exam papers. */
const DIGIT_GROUP_SPACE = " ";

/** Whole numbers of five or more digits; not decimal places, not inside codes like "A12345". */
const LONG_WHOLE_NUMBER = /(?<![\w.,])\d{5,}(?!\d)/g;

function groupInThrees(digits: string, separator: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, separator);
}

/**
 * Make numbers in plain text easier to read:
 * - long whole numbers are grouped in threes ("1250000" → "1 250 000"), the way
 *   exam papers print them; four-digit numbers such as years are left alone;
 * - a hyphen used as a minus sign ("-5") becomes a true minus ("−5"), which is
 *   wider and can't be split from its number at a line break.
 */
export function formatNumbers(text: string): string {
  return text
    .replace(LONG_WHOLE_NUMBER, (digits) => groupInThrees(digits, DIGIT_GROUP_SPACE))
    .replace(/(^|[\s(=])-(?=\d)/g, "$1−");
}

/** Group long whole numbers inside LaTeX with a thin space (`\,`). */
export function formatTexNumbers(tex: string): string {
  return tex.replace(/(?<![\d.])\d{5,}(?!\d)/g, (digits) => groupInThrees(digits, "\\,"));
}

/**
 * Draw LaTeX into `element` with KaTeX's own layout and fonts, so maths looks
 * the same in every browser (native MathML rendering varies a lot between
 * Chrome, Safari and Firefox). Screen readers get the hidden MathML copy.
 *
 * Security:
 * - KaTeX builds DOM nodes and sets their styles through the CSSOM, which the
 *   strict Content-Security-Policy (`style-src 'self'`) allows; an HTML string
 *   with `style="..."` attributes would be blocked.
 * - `trust: false` blocks \href, \url, \includegraphics and similar.
 * - Invalid LaTeX is shown as plain text: KaTeX's own error display uses a
 *   style attribute, which the policy would block.
 *
 * `\displaystyle` draws fractions full size rather than shrunk to the line,
 * as exam papers do.
 *
 * @param element - Element whose contents are replaced.
 * @param tex - LaTeX source, without `$` delimiters.
 */
export function renderMathInto(element: HTMLElement, tex: string): void {
  try {
    katex.render(`\\displaystyle ${formatTexNumbers(tex)}`, element, {
      output: "htmlAndMathml",
      throwOnError: true,
      trust: false,
      strict: "ignore",
      maxSize: 20,
      maxExpand: 200,
    });
  } catch (error) {
    if (!(error instanceof katex.ParseError)) throw error;
    element.textContent = tex;
  }
}
