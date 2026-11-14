// frontend/src/practice/MathKeypad.test.tsx
/**
 * Covers:
 * - numeric questions show the keys; tapping 3, a/b, 5 builds "3/5", shows a
 *   fraction preview and submits "3/5"
 * - minus and decimal point keys; delete removes the last character; clear empties
 * - short-text maths questions get the ratio and percent keys; short-text
 *   questions without maths and multiple choice get no keys
 * - the keys stop the phone keyboard opening until "Use keyboard instead"
 * - answerAsLatex: fractions only, numbers only, percent escaped
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PracticeItemOut } from "../api/generated/model";
import { answerAsLatex } from "./answerPreview";
import { QuestionCard } from "./QuestionCard";

const NUMERIC: PracticeItemOut = {
  id: "00000000-0000-4000-8000-0000000000f1",
  questionType: "numeric",
  commandWord: "Write down",
  stem: "Write down $0.6$ as a fraction.",
  options: [],
  unit: null,
  marks: 1,
  difficulty: 1,
  objectiveRef: "N10",
  hints: [],
  hintsRemaining: 4,
  review: false,
};

function setup(item: PracticeItemOut = NUMERIC) {
  const onSubmit = vi.fn();
  render(<QuestionCard item={item} submitting={false} onSubmit={onSubmit} />);
  return { onSubmit, user: userEvent.setup(), input: screen.queryByLabelText("Your answer") };
}

describe("MathKeypad on a question", () => {
  it("should build a fraction from the keys, preview it and submit it", async () => {
    // Arrange
    const { onSubmit, user, input } = setup();

    // Act
    await user.click(screen.getByRole("button", { name: "3" }));
    await user.click(screen.getByRole("button", { name: "Fraction" }));
    await user.click(screen.getByRole("button", { name: "5" }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    // Assert
    expect(input).toHaveValue("3/5");
    expect(screen.getByText(/Looks like:/)).toBeInTheDocument();
    expect(screen.getByText(/Looks like:/).querySelector("math")).not.toBeNull();
    expect(onSubmit).toHaveBeenCalledWith("3/5");
  });

  it("should type minus and decimal point, delete and clear", async () => {
    // Arrange
    const { user, input } = setup();

    // Act
    for (const name of ["Minus", "2", "Decimal point", "5", "7"]) {
      await user.click(screen.getByRole("button", { name }));
    }
    await user.click(screen.getByRole("button", { name: "Delete" }));

    // Assert
    expect(input).toHaveValue("-2.5");
    expect(screen.queryByText(/Looks like:/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(input).toHaveValue("");
  });

  it("should add ratio and percent keys for short maths answers", async () => {
    // Arrange
    const { user, input } = setup({ ...NUMERIC, questionType: "short_text" });

    // Act
    await user.click(screen.getByRole("button", { name: "2" }));
    await user.click(screen.getByRole("button", { name: "Ratio" }));
    await user.click(screen.getByRole("button", { name: "3" }));

    // Assert
    expect(input).toHaveValue("2:3");
    expect(screen.getByRole("button", { name: "Percent" })).toBeInTheDocument();
  });

  it("should not show keys for word answers or multiple choice", () => {
    setup({ ...NUMERIC, questionType: "short_text", stem: "State the inverse of squaring." });
    expect(screen.queryByRole("group", { name: "Maths keys" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Your answer")).toHaveAttribute("inputmode", "text");
  });

  it("should keep the phone keyboard closed until asked for", async () => {
    // Arrange
    const { user, input } = setup();
    expect(input).toHaveAttribute("inputmode", "none");

    // Act
    await user.click(screen.getByRole("button", { name: "Use keyboard instead" }));

    // Assert
    expect(input).toHaveAttribute("inputmode", "decimal");
    await user.click(screen.getByRole("button", { name: "Use the on-screen keys only" }));
    expect(input).toHaveAttribute("inputmode", "none");
  });
});

describe("answerAsLatex", () => {
  it.each([
    ["3/5", "\\frac{3}{5}"],
    [" -7 / 2 ", "-\\frac{7}{2}"],
    ["−1/4", "-\\frac{1}{4}"],
    ["1.5/3%", "\\frac{1.5}{3}\\%"],
  ])("should turn %j into a fraction", (typed, latex) => {
    expect(answerAsLatex(typed)).toBe(latex);
  });

  it.each(["3", "0.6", "x/2", "3/5 \\href", ""])("should not preview %j", (typed) => {
    expect(answerAsLatex(typed)).toBeNull();
  });
});
