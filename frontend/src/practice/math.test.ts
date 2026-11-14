// frontend/src/practice/math.test.ts
/**
 * Covers:
 * - splitting text and $...$ maths; escaped \$; unmatched and empty $ kept as text
 * - rendering produces MathML only (no inline styles), bad LaTeX doesn't throw,
 *   and \href is not turned into a link (trust disabled)
 * - punctuation after maths is attached to it (only leading punctuation; text
 *   after it kept; maths at the end or before maths gets none)
 * - number formatting: 5+ digit whole numbers grouped, 4-digit numbers, decimal
 *   places and codes left alone; hyphen-minus becomes − only before a number
 *   and not inside ranges; LaTeX numbers grouped with \, and rendered grouped
 */
import { describe, expect, it } from "vitest";

import { formatNumbers, formatTexNumbers, renderMath, splitMath, toPieces } from "./math";

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

describe("toPieces", () => {
  it("should attach a full stop to the maths before it", () => {
    expect(toPieces(splitMath("The value of $\\sqrt[3]{125}$."))).toEqual([
      { kind: "text", value: "The value of " },
      { kind: "math", value: "\\sqrt[3]{125}", after: "." },
    ]);
  });

  it("should keep the text that follows the punctuation", () => {
    expect(toPieces(splitMath("($x$), then stop"))).toEqual([
      { kind: "text", value: "(" },
      { kind: "math", value: "x", after: ")," },
      { kind: "text", value: " then stop" },
    ]);
  });

  it("should attach nothing when maths is followed by a space, more maths or nothing", () => {
    expect(toPieces(splitMath("$a$ and $b$$c$"))).toEqual([
      { kind: "math", value: "a", after: "" },
      { kind: "text", value: " and " },
      { kind: "math", value: "b", after: "" },
      { kind: "math", value: "c", after: "" },
    ]);
  });

  it("should return nothing for empty text", () => {
    expect(toPieces(splitMath(""))).toEqual([]);
  });
});

describe("formatNumbers", () => {
  it("should group whole numbers of five or more digits in threes", () => {
    expect(formatNumbers("A car costs £12500, a house 1250000.")).toBe(
      "A car costs £12\u202F500, a house 1\u202F250\u202F000.",
    );
  });

  it("should leave four-digit numbers, decimal places and codes alone", () => {
    expect(formatNumbers("In 2028, 3.14159 and ref A123456 and 12,500")).toBe(
      "In 2028, 3.14159 and ref A123456 and 12,500",
    );
  });

  it("should group only the whole-number part of a long decimal", () => {
    expect(formatNumbers("12345.678")).toBe("12\u202F345.678");
  });

  it("should turn a hyphen used as a minus sign into a true minus", () => {
    expect(formatNumbers("-5 is less than (-2) and x = -3")).toBe(
      "\u22125 is less than (\u22122) and x = \u22123",
    );
  });

  it("should leave hyphens in ranges and words alone", () => {
    expect(formatNumbers("pages 3-4, a well-known 2-digit number")).toBe(
      "pages 3-4, a well-known 2-digit number",
    );
  });
});

describe("formatTexNumbers", () => {
  it("should group long whole numbers with a thin space", () => {
    expect(formatTexNumbers("\\frac{125000}{10} + 0.123456")).toBe(
      "\\frac{125\\,000}{10} + 0.123456",
    );
  });

  it("should leave short numbers unchanged", () => {
    expect(formatTexNumbers("2^{10} = 1024")).toBe("2^{10} = 1024");
  });

  it("should render grouped numbers as separate MathML numbers with a space", () => {
    const html = renderMath("1250000");

    expect(html).toContain("<mn>1</mn><mtext>\u2009</mtext><mn>250</mn>");
    expect(html).not.toContain("1250000</mn>");
  });
});
