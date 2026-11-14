// frontend/src/practice/math.ts
// Splitting text into plain and LaTeX parts, and rendering LaTeX safely.
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
 * Render LaTeX as MathML (native browser rendering: no fonts, no inline
 * styles, so the strict Content-Security-Policy is unchanged). `trust: false`
 * blocks \href, \url, \includegraphics and similar; bad LaTeX renders as an
 * error span instead of throwing.
 */
export function renderMath(tex: string): string {
  return katex.renderToString(formatTexNumbers(tex), {
    output: "mathml",
    throwOnError: false,
    trust: false,
    strict: "ignore",
    maxSize: 20,
    maxExpand: 200,
  });
}
