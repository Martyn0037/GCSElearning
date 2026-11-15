// frontend/src/practice/editing.ts
// Editing an answer from on-screen keys at the caret, like a real keyboard.

export interface Edit {
  value: string;
  /** Where the caret goes afterwards. */
  caret: number;
}

const MAX_LENGTH = 200;

/** Replace the selection (or insert at the caret) with `text`, within the length limit. */
export function insertAt(value: string, text: string, start: number, end: number): Edit {
  const from = Math.max(0, Math.min(start, value.length));
  const to = Math.max(from, Math.min(end, value.length));
  const room = MAX_LENGTH - (value.length - (to - from));
  const added = text.slice(0, Math.max(0, room));
  return { value: value.slice(0, from) + added + value.slice(to), caret: from + added.length };
}

/** Delete the selection, or the character before the caret. */
export function deleteBack(value: string, start: number, end: number): Edit {
  const from = Math.max(0, Math.min(start, value.length));
  const to = Math.max(from, Math.min(end, value.length));
  if (to > from) return { value: value.slice(0, from) + value.slice(to), caret: from };
  if (from === 0) return { value, caret: 0 };
  return { value: value.slice(0, from - 1) + value.slice(from), caret: from - 1 };
}
