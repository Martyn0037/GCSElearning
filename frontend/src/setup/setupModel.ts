// frontend/src/setup/setupModel.ts
/**
 * Pure state logic for the subject setup screen: what's selected, the
 * board/tier/set-text choices for each subject, and converting to and from
 * the API. Kept free of React so it's easy to test.
 */
import type {
  CatalogueOut,
  CatalogueSpecificationOut,
  CatalogueSubjectOut,
  EnrolmentOut,
  SetTextChoice,
  SubjectChoice,
  Tier,
} from "../api/generated/model";

/** A board ID, or "unknown" when the student chose "I don't know". */
export type BoardChoice = string;
export type TierChoice = Tier | "unknown";

/** One set text: picked from the board's list, or typed in. Empty = skipped. */
export type SetTextDraft =
  { kind: "none" } | { kind: "option"; optionId: string } | { kind: "custom"; title: string };

export interface SubjectDraft {
  /** Stable key: the subject ID, or "custom:<name>" for typed-in subjects. */
  key: string;
  subjectId: string | null;
  customName: string | null;
  board: BoardChoice;
  tier: TierChoice;
  setTexts: Record<string, SetTextDraft>;
}

export const MAX_CUSTOM_NAME = 80;

export function customKey(name: string): string {
  return `custom:${name.trim().toLocaleLowerCase("en-GB")}`;
}

/** A fresh draft for a catalogue subject: every choice starts as "I don't know". */
export function newSubjectDraft(subject: CatalogueSubjectOut): SubjectDraft {
  return {
    key: subject.id,
    subjectId: subject.id,
    customName: null,
    board: "unknown",
    tier: "unknown",
    setTexts: {},
  };
}

export function newCustomDraft(name: string): SubjectDraft {
  return {
    key: customKey(name),
    subjectId: null,
    customName: name.trim(),
    board: "unknown",
    tier: "unknown",
    setTexts: {},
  };
}

/** Rebuild drafts from what the student saved before, so the screen opens pre-filled. */
export function draftsFromEnrolments(enrolments: readonly EnrolmentOut[]): SubjectDraft[] {
  return enrolments.map((e) => {
    const setTexts: Record<string, SetTextDraft> = {};
    for (const text of e.setTexts) {
      setTexts[text.category] = text.optionId
        ? { kind: "option", optionId: text.optionId }
        : { kind: "custom", title: text.title };
    }
    return {
      key: e.subjectId ?? customKey(e.subjectName),
      subjectId: e.subjectId,
      customName: e.isCustom ? e.subjectName : null,
      board: e.boardConfirmed && e.boardId ? e.boardId : "unknown",
      tier: e.tierConfirmed && e.tier ? e.tier : "unknown",
      setTexts,
    };
  });
}

/** The board the server will use: the chosen one, or the subject's most common. */
export function effectiveBoardId(
  draft: SubjectDraft,
  subject: CatalogueSubjectOut | undefined,
): string | null {
  if (draft.board !== "unknown") return draft.board;
  return subject?.mostCommonBoardId ?? null;
}

/** The current imported spec for the subject on the effective board, if any. */
export function specFor(
  draft: SubjectDraft,
  subject: CatalogueSubjectOut | undefined,
): CatalogueSpecificationOut | undefined {
  const boardId = effectiveBoardId(draft, subject);
  return subject?.specifications.find((s) => s.boardId === boardId);
}

/** Convert drafts to the request body, dropping set texts left empty or not on the list. */
export function toChoices(
  drafts: readonly SubjectDraft[],
  catalogue: CatalogueOut,
): SubjectChoice[] {
  const subjects = new Map(catalogue.subjects.map((s) => [s.id, s]));
  return drafts.map((draft) => {
    const subject = draft.subjectId ? subjects.get(draft.subjectId) : undefined;
    const spec = specFor(draft, subject);
    const validOptions = new Set(spec?.setTexts.map((t) => t.id) ?? []);
    const setTexts = Object.entries(draft.setTexts).flatMap<SetTextChoice>(([category, text]) => {
      if (text.kind === "option" && validOptions.has(text.optionId)) {
        return [{ category, optionId: text.optionId }];
      }
      if (text.kind === "custom" && text.title.trim()) {
        return [{ category, customTitle: text.title.trim() }];
      }
      return [];
    });
    return {
      ...(draft.subjectId
        ? { subjectId: draft.subjectId }
        : { customName: draft.customName ?? "" }),
      boardId: draft.board === "unknown" ? null : draft.board,
      tier: subject?.hasTiers && draft.tier !== "unknown" ? draft.tier : null,
      setTexts,
    };
  });
}
