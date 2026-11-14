// frontend/src/practice/MathText.tsx
import { memo } from "react";

import { renderMath, splitMath } from "./math";

/**
 * Text with inline maths. Plain text is escaped by React; only KaTeX's
 * generated markup is inserted as HTML.
 */
export const MathText = memo(function MathText({ text }: { text: string }) {
  return (
    <span className="whitespace-pre-line">
      {splitMath(text).map((segment, index) =>
        segment.kind === "text" ? (
          <span key={index}>{segment.value}</span>
        ) : (
          <span
            key={index}
            className="mx-0.5 inline-block align-middle"
            // KaTeX output only, from LaTeX with trust disabled.
            dangerouslySetInnerHTML={{ __html: renderMath(segment.value) }}
          />
        ),
      )}
    </span>
  );
});
