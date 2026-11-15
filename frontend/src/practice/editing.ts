// frontend/src/practice/editing.ts
// Editing an answer from on-screen keys at the caret, like a real keyboard.

export interface Edit {
  value: string;
  /** Where the caret goes afterwards. */
  caret: number;
}

/** Longest short answer; written (extended) answers allow `ESSAY_MAX_LENGTH`. */
export const MAX_LENGTH = 200;
export const ESSAY_MAX_LENGTH = 4000;

/** Replace the selection (or insert at the caret) with `text`, within the length limit. */
export function insertAt(
  value: string,
  text: string,
  start: number,
  end: number,
  maxLength: number = MAX_LENGTH,
): Edit {
  const from = Math.max(0, Math.min(start, value.length));
  const to = Math.max(from, Math.min(end, value.length));
  const room = maxLength - (value.length - (to - from));
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
