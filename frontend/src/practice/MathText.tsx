// frontend/src/practice/MathText.tsx
import { memo, useLayoutEffect, useRef } from "react";

import { formatNumbers, renderMathInto, splitMath, toPieces } from "./math";

/** One LaTeX expression, drawn by KaTeX into its own element. */
const MathSpan = memo(function MathSpan({ tex }: { tex: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  // Layout effect: draw before paint, so the raw LaTeX never flashes.
  useLayoutEffect(() => {
    if (ref.current) renderMathInto(ref.current, tex);
  }, [tex]);
  return <span ref={ref} className="maths" />;
});

/**
 * Text with inline maths. Plain text is escaped by React; maths is built as
 * DOM nodes by KaTeX (no HTML strings). Numbers are formatted for reading
 * (grouped digits, true minus signs), and punctuation stays with its maths.
 */
export const MathText = memo(function MathText({ text }: { text: string }) {
  return (
    <span className="whitespace-pre-line">
      {toPieces(splitMath(text)).map((piece, index) =>
        piece.kind === "text" ? (
          <span key={index}>{formatNumbers(piece.value)}</span>
        ) : (
          <span key={index} className="whitespace-nowrap">
            <MathSpan tex={piece.value} />
            {piece.after}
          </span>
        ),
      )}
    </span>
  );
});
