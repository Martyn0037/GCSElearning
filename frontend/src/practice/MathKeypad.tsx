// frontend/src/practice/MathKeypad.tsx
/**
 * On-screen keys for typing maths answers without hunting for symbols on a
 * phone keyboard. Every key produces text the marker already understands
 * (e.g. "3/5", "-2.5", "2:3").
 */

interface MathKeypadProps {
  /** Add text to the end of the answer. */
  onInsert: (text: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  /** Show the ratio and percent keys (short-text answers only). */
  extraKeys: boolean;
}

interface Key {
  label: string;
  /** Spoken name when the label is a symbol. */
  name?: string;
  action: "insert" | "backspace" | "clear";
  value?: string;
  wide?: boolean;
}

const insert = (value: string, name?: string): Key => ({
  label: value,
  value,
  action: "insert",
  ...(name ? { name } : {}),
});

const BACKSPACE: Key = { label: "⌫", name: "Delete", action: "backspace" };
const FRACTION: Key = { label: "a/b", name: "Fraction", value: "/", action: "insert" };
const MINUS: Key = { label: "−", name: "Minus", value: "-", action: "insert" };

function keys(extraKeys: boolean): Key[] {
  const lastRow: Key[] = extraKeys
    ? [insert("0"), insert(".", "Decimal point"), insert(":", "Ratio"), insert("%", "Percent")]
    : [insert("0"), insert(".", "Decimal point"), { label: "Clear", action: "clear", wide: true }];
  return [
    insert("7"),
    insert("8"),
    insert("9"),
    BACKSPACE,
    insert("4"),
    insert("5"),
    insert("6"),
    FRACTION,
    insert("1"),
    insert("2"),
    insert("3"),
    MINUS,
    ...lastRow,
    ...(extraKeys ? [{ label: "Clear", action: "clear", wide: true } satisfies Key] : []),
  ];
}

const keyClass =
  "min-h-12 rounded-lg border border-slate-300 bg-white text-xl font-medium text-slate-900 shadow-sm hover:bg-slate-50 active:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-600";

/** A 4-column keypad. Keys are buttons, so they never submit the form. */
export function MathKeypad({ onInsert, onBackspace, onClear, extraKeys }: MathKeypadProps) {
  return (
    <div role="group" aria-label="Maths keys" className="grid grid-cols-4 gap-2">
      {keys(extraKeys).map((key) => (
        <button
          key={key.name ?? key.label}
          type="button"
          aria-label={key.name}
          className={`${keyClass} ${key.wide ? "col-span-2" : ""}`}
          onClick={() => {
            if (key.action === "backspace") onBackspace();
            else if (key.action === "clear") onClear();
            else onInsert(key.value ?? key.label);
          }}
        >
          {key.label}
        </button>
      ))}
    </div>
  );
}
