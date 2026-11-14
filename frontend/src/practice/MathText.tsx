// frontend/src/practice/MathText.tsx
import { memo } from "react";

import { formatNumbers, renderMath, splitMath, toPieces } from "./math";

/**
 * Text with inline maths. Plain text is escaped by React; only KaTeX's
 * generated markup is inserted as HTML. Numbers are formatted for reading
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
            <span
              className="maths"
              // KaTeX output only, from LaTeX with trust disabled.
              dangerouslySetInnerHTML={{ __html: renderMath(piece.value) }}
            />
            {piece.after}
          </span>
        ),
      )}
    </span>
  );
});
