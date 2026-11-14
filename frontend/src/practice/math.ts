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

/**
 * Render LaTeX as MathML (native browser rendering: no fonts, no inline
 * styles, so the strict Content-Security-Policy is unchanged). `trust: false`
 * blocks \href, \url, \includegraphics and similar; bad LaTeX renders as an
 * error span instead of throwing.
 */
export function renderMath(tex: string): string {
  return katex.renderToString(tex, {
    output: "mathml",
    throwOnError: false,
    trust: false,
    strict: "ignore",
    maxSize: 20,
    maxExpand: 200,
  });
}
