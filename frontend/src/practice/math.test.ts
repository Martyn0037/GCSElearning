// frontend/src/practice/math.test.ts
/**
 * Covers:
 * - splitting text and $...$ maths; escaped \$; unmatched and empty $ kept as text
 * - rendering produces MathML only (no inline styles), bad LaTeX doesn't throw,
 *   and \href is not turned into a link (trust disabled)
 */
import { describe, expect, it } from "vitest";

import { renderMath, splitMath } from "./math";

describe("splitMath", () => {
  it("should split text and maths", () => {
    expect(splitMath("Work out $\\frac{7}{2}$ + 1")).toEqual([
      { kind: "text", value: "Work out " },
      { kind: "math", value: "\\frac{7}{2}" },
      { kind: "text", value: " + 1" },
    ]);
  });

  it("should treat escaped and unmatched dollars as text", () => {
    expect(splitMath("Costs \\$5 or $3")).toEqual([{ kind: "text", value: "Costs $5 or $3" }]);
    expect(splitMath("$$")).toEqual([{ kind: "text", value: "$$" }]);
  });
});

describe("renderMath", () => {
  it("should render MathML without inline styles", () => {
    const html = renderMath("2^{5}");

    expect(html).toContain("<math");
    expect(html).not.toContain("style=");
  });

  it("should not throw on invalid LaTeX", () => {
    expect(() => renderMath("\\frac{1}{")).not.toThrow();
  });

  it("should not create links from \\href", () => {
    expect(renderMath("\\href{https://evil.example}{x}")).not.toContain("href=");
  });
});
