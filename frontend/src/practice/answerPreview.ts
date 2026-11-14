// frontend/src/practice/answerPreview.ts

/** Characters a typed maths answer may contain for it to be previewed. */
const PREVIEWABLE = /^[0-9a-z.,\s+\-/:%()π√^×÷=<>≤≥°]+$/i;
/** Only answers with something to typeset are previewed ("3" stays as typed). */
const TYPESET = /[/π√^×÷≤≥°]/;
const COMMANDS: Record<string, string> = {
  π: "\\pi",
  "×": "\\times",
  "÷": "\\div",
  "≤": "\\le",
  "≥": "\\ge",
};
const OPERAND = String.raw`(\d+(?:\.\d+)?|[a-z]|π)`;

/**
 * LaTeX for a typed answer, so "3/5", "1/2π", "√3" and "x^2" are previewed
 * as they'd be written.
 *
 * Returns `null` unless the answer has something to typeset and contains only
 * keypad characters, so no LaTeX command can be smuggled in (no backslashes).
 */
export function answerAsLatex(answer: string): string | null {
  const text = answer.trim().replace(/−/g, "-");
  if (!TYPESET.test(text) || !PREVIEWABLE.test(text)) return null;
  return text
    .replace(new RegExp(`${OPERAND}\\s*/\\s*${OPERAND}`, "gi"), "\\frac{$1}{$2}")
    .replace(/√\(([^()]*)\)/g, "\\sqrt{$1}")
    .replace(new RegExp(`√${OPERAND}`, "gi"), "\\sqrt{$1}")
    .replace(new RegExp(`\\^${OPERAND}`, "gi"), "^{$1}")
    .replace(/[π×÷≤≥]/g, (symbol, offset: number, whole: string) => {
      // A letter straight after a command would join it ("\\pix"), so add a space then.
      const command = COMMANDS[symbol] ?? "";
      return /[a-z]/i.test(whole.charAt(offset + 1)) ? `${command} ` : command;
    })
    .replace(/°/g, "^{\\circ}")
    .replace(/%/g, "\\%")
    .trim();
}
