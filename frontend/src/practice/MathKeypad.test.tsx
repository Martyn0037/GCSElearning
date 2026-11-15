// frontend/src/practice/MathKeypad.test.tsx
/**
 * Covers:
 * - numeric questions show the keys; tapping 3, a/b, 5 builds "3/5", shows a
 *   fraction preview and submits "3/5"
 * - minus and decimal point keys; delete removes the last character; clear empties
 * - symbol keys come from the server (symbolKeys) with spoken names; π typed
 *   from the keys ("1/2π") is submitted, with a tip for π; none when not needed
 * - word answers (keypad false) keep the keyboard, still get every key below
 * - languages: only their accented letters, no number pad or maths tips;
 *   tapping ñ types it and keeps the box focused with the cursor after it
 *   (typing carries on in place); the phone keyboard stays; no maths preview
 * - other word subjects: no on-screen keys at all
 * - keys insert and delete at the cursor
 * - the keys stop the phone keyboard opening until "Use keyboard instead"
 * - answerAsLatex: fractions, π, roots, powers, ×, ≤, degrees, percent; no preview
 *   for plain numbers, ratios, words, or anything with a backslash
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
  keypad: true,
  numberKeys: true,
  symbolKeys: [],
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
    expect(
      screen
        .getByText(/Looks like:/)
        .closest("p")
        ?.querySelector("math"),
    ).not.toBeNull();
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

  it("should show the symbol keys the server asks for, with spoken names", async () => {
    // Arrange
    const { user, input, onSubmit } = setup({
      ...NUMERIC,
      questionType: "short_text",
      stem: "Write down the exact value of $\\frac{5}{6}\\pi - \\frac{1}{3}\\pi$",
      symbolKeys: ["π", "√", "^", "(", ")", ":", "x"],
    });

    // Act
    for (const name of ["1", "Fraction", "2", "Pi"]) {
      await user.click(screen.getByRole("button", { name }));
    }
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    // Assert
    expect(input).toHaveValue("1/2π");
    expect(onSubmit).toHaveBeenCalledWith("1/2π");
    for (const name of ["Square root", "Power", "Open bracket", "Close bracket", "Ratio", "x"]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    expect(screen.getByText(/For π, use the π key/)).toBeInTheDocument();
  });

  it("should show only number keys when no symbols are needed", () => {
    // Arrange / Act
    setup();

    // Assert
    expect(screen.queryByRole("button", { name: "Pi" })).not.toBeInTheDocument();
    expect(screen.queryByText(/For π/)).not.toBeInTheDocument();
  });

  it("should keep the keyboard for word answers, with every key still below", async () => {
    // Arrange
    const { user, input } = setup({
      ...NUMERIC,
      questionType: "short_text",
      keypad: false,
      numberKeys: true,
      symbolKeys: ["π", "²", "°"],
    });

    // Act
    await user.type(input as HTMLElement, "12 cm");
    await user.click(screen.getByRole("button", { name: "Squared" }));

    // Assert
    expect(input).toHaveAttribute("inputmode", "text");
    expect(input).toHaveValue("12 cm²");
    expect(screen.getByRole("group", { name: "Maths keys" })).toBeInTheDocument();
    expect(screen.getByText(/Numbers and symbols are on the keys below/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Use keyboard instead" })).not.toBeInTheDocument();
  });

  it("should insert and delete at the cursor, not just the end", async () => {
    // Arrange
    const { user, input } = setup({ ...NUMERIC, questionType: "short_text", symbolKeys: ["π"] });
    const field = input as HTMLInputElement;
    await user.type(field, "1/2");

    // Act: put the cursor after "1", add π there, then delete it again
    field.setSelectionRange(1, 1);
    await user.click(screen.getByRole("button", { name: "Pi" }));
    const afterInsert = field.value;
    field.setSelectionRange(2, 2);
    await user.click(screen.getByRole("button", { name: "Delete" }));

    // Assert
    expect(afterInsert).toBe("1π/2");
    expect(field).toHaveValue("1/2");
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

describe("keys by subject", () => {
  const SPANISH: PracticeItemOut = {
    ...NUMERIC,
    questionType: "short_text",
    stem: "Translate: the boy",
    keypad: false,
    numberKeys: false,
    symbolKeys: ["á", "é", "í", "ó", "ú", "ü", "ñ", "¿", "¡"],
  };

  it("should give a language its accented letters and nothing else", async () => {
    // Arrange
    const { onSubmit, user, input } = setup(SPANISH);

    // Act
    await user.type(input as HTMLElement, "el ni");
    await user.click(screen.getByRole("button", { name: "ñ" }));
    // Carry on typing without touching the box: focus and cursor stay put.
    await vi.waitFor(() => {
      expect(input).toHaveFocus();
    });
    await user.keyboard("o");
    await user.click(screen.getByRole("button", { name: "Check answer" }));

    // Assert
    expect(onSubmit).toHaveBeenCalledWith("el niño");
    expect(screen.getByRole("group", { name: "Accented letters" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "7" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pi" })).not.toBeInTheDocument();
    expect(screen.getByText(/Accented letters are on the keys below/)).toBeInTheDocument();
    expect(screen.queryByText(/For π/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Looks like/)).not.toBeInTheDocument();
    expect(input).not.toHaveAttribute("inputmode", "none");
  });

  it("should show no keys for other word subjects", () => {
    // Arrange / Act
    setup({ ...SPANISH, symbolKeys: [] });

    // Assert
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(screen.getByText("Type your answer.")).toBeInTheDocument();
  });
});

describe("answerAsLatex", () => {
  it.each([
    ["3/5", "\\frac{3}{5}"],
    [" -7 / 2 ", "-\\frac{7}{2}"],
    ["−1/4", "-\\frac{1}{4}"],
    ["1.5/3%", "\\frac{1.5}{3}\\%"],
    ["1/2π", "\\frac{1}{2}\\pi"],
    ["π/2", "\\frac{\\pi}{2}"],
    ["√3", "\\sqrt{3}"],
    ["√(x+1)", "\\sqrt{x+1}"],
    ["x^2", "x^{2}"],
    ["3×4", "3\\times4"],
    ["2πx", "2\\pi x"],
    ["x≤3", "x\\le3"],
    ["45°", "45^{\\circ}"],
  ])("should typeset %j", (typed, latex) => {
    expect(answerAsLatex(typed)).toBe(latex);
  });

  it.each(["3", "0.6", "2:3", "3/5 \\href", "prime", ""])("should not preview %j", (typed) => {
    expect(answerAsLatex(typed)).toBeNull();
  });
});
