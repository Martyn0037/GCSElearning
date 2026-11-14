// frontend/src/practice/answerPreview.ts

/**
 * LaTeX for a typed answer, so "3/5" can be previewed as a stacked fraction.
 *
 * Returns `null` unless the answer contains a fraction and only number
 * characters: anything else is shown as typed.
 */
export function answerAsLatex(answer: string): string | null {
  const text = answer.trim().replace(/−/g, "-");
  if (!text.includes("/") || !/^[0-9.,\s\-/:%()]+$/.test(text)) return null;
  return text
    .replace(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/g, "\\frac{$1}{$2}")
    .replace(/%/g, "\\%");
}
