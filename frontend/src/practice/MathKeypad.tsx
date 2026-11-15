// frontend/src/practice/MathKeypad.tsx
/**
 * On-screen keys for typing maths answers without hunting for symbols on a
 * phone keyboard. The number keys are always there; on short answers the
 * server adds every symbol key (π, √, powers, brackets, °, ratio, letters the
 * maths uses...), so the student can always type the answer from the screen. Every key produces text
 * the marker understands (e.g. "3/5", "1/2π", "x^2").
 */

interface MathKeypadProps {
  /** Add text to the end of the answer. */
  onInsert: (text: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  /** Extra symbol keys for this question, from the server (`symbolKeys`). */
  symbols: readonly string[];
}

interface Key {
  label: string;
  /** Spoken name when the label is a symbol. */
  name?: string;
  action: "insert" | "backspace" | "clear";
  value?: string;
  wide?: boolean;
}

/** Spoken names for symbol keys (screen readers say "pi", not "π"). */
const SYMBOL_NAMES: Record<string, string> = {
  π: "Pi",
  "√": "Square root",
  "^": "Power",
  "²": "Squared",
  "³": "Cubed",
  "(": "Open bracket",
  ")": "Close bracket",
  ":": "Ratio",
  "%": "Percent",
  "°": "Degrees",
  "×": "Times",
  "÷": "Divide",
  "=": "Equals",
  "<": "Less than",
  ">": "Greater than",
  "≤": "Less than or equal to",
  "≥": "Greater than or equal to",
};

const insert = (value: string, name?: string): Key => ({
  label: value,
  value,
  action: "insert",
  ...(name ? { name } : {}),
});

const NUMBER_KEYS: readonly Key[] = [
  insert("7"),
  insert("8"),
  insert("9"),
  { label: "⌫", name: "Delete", action: "backspace" },
  insert("4"),
  insert("5"),
  insert("6"),
  { label: "a/b", name: "Fraction", value: "/", action: "insert" },
  insert("1"),
  insert("2"),
  insert("3"),
  { label: "−", name: "Minus", value: "-", action: "insert" },
  insert("0"),
  insert(".", "Decimal point"),
  { label: "Clear", action: "clear", wide: true },
];

const keyClass =
  "min-h-12 rounded-xl text-xl font-medium shadow-card ring-1 ring-slate-200 transition select-none active:scale-95 focus-visible:outline-2 focus-visible:outline-brand-600";

/** Number keys in a 4-column grid, then this question's symbol keys. Keys never submit. */
export function MathKeypad({ onInsert, onBackspace, onClear, symbols }: MathKeypadProps) {
  function press(key: Key) {
    if (key.action === "backspace") onBackspace();
    else if (key.action === "clear") onClear();
    else onInsert(key.value ?? key.label);
  }
  const symbolKeys = symbols.map((symbol) => insert(symbol, SYMBOL_NAMES[symbol]));

  return (
    <div role="group" aria-label="Maths keys" className="space-y-2">
      {symbolKeys.length > 0 && (
        <div className="grid grid-cols-5 gap-2">
          {symbolKeys.map((key) => (
            <button
              key={key.label}
              type="button"
              aria-label={key.name}
              className={`${keyClass} bg-brand-50 text-brand-ink hover:bg-brand-100`}
              onClick={() => {
                press(key);
              }}
            >
              {key.label}
            </button>
          ))}
        </div>
      )}
      <div className="grid grid-cols-4 gap-2">
        {NUMBER_KEYS.map((key) => (
          <button
            key={key.name ?? key.label}
            type="button"
            aria-label={key.name}
            className={`${keyClass} bg-surface text-slate-900 hover:bg-slate-50 active:bg-brand-50 ${key.wide ? "col-span-2" : ""}`}
            onClick={() => {
              press(key);
            }}
          >
            {key.label}
          </button>
        ))}
      </div>
    </div>
  );
}
