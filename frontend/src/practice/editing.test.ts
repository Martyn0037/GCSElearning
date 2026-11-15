// frontend/src/practice/editing.test.ts
/**
 * Covers:
 * - insertAt: at the end, in the middle, over a selection, out-of-range caret,
 *   and the 200-character limit (trimmed, caret after what fitted)
 * - deleteBack: before the caret, a selection, at the start (no change)
 */
import { describe, expect, it } from "vitest";

import { deleteBack, insertAt } from "./editing";

describe("insertAt", () => {
  it.each([
    ["1/2", "π", 3, 3, "1/2π", 4],
    ["1/2", "π", 1, 1, "1π/2", 2],
    ["1/2", "3", 0, 3, "3", 1],
    ["12", "x", 99, 99, "12x", 3],
  ])("should put %j + %j at %i..%i", (value, text, start, end, expected, caret) => {
    expect(insertAt(value, text, start, end)).toEqual({ value: expected, caret });
  });

  it("should stop at 200 characters", () => {
    const full = "1".repeat(199);
    expect(insertAt(full, "23", 199, 199)).toEqual({ value: `${full}2`, caret: 200 });
    expect(insertAt(`${full}1`, "π", 0, 0).value).toHaveLength(200);
  });
});

describe("deleteBack", () => {
  it.each([
    ["1π/2", 2, 2, "1/2", 1],
    ["1π/2", 1, 3, "12", 1],
    ["12", 0, 0, "12", 0],
  ])("should delete from %j at %i..%i", (value, start, end, expected, caret) => {
    expect(deleteBack(value, start, end)).toEqual({ value: expected, caret });
  });
});
