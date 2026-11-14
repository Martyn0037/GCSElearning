// frontend/src/setup/setupModel.test.ts
/**
 * Covers:
 * - new drafts start as "I don't know" for board and tier
 * - custom subject keys ignore case/spacing
 * - pre-filling from saved subjects: unconfirmed -> "unknown"; set texts mapped
 * - effective board falls back to the most common board
 * - toChoices: null for "don't know", tier only for tiered subjects, set texts
 *   kept only when on the current spec's list or typed in, blanks dropped
 */
import { describe, expect, it } from "vitest";

import type { EnrolmentOut } from "../api/generated/model";
import { CATALOGUE, subjectAt } from "../test/catalogue";
import {
  customKey,
  draftsFromEnrolments,
  effectiveBoardId,
  newCustomDraft,
  newSubjectDraft,
  specFor,
  toChoices,
} from "./setupModel";

const [maths, englit] = [subjectAt(0), subjectAt(1)];

describe("drafts", () => {
  it("should start new subjects as don't know", () => {
    expect(newSubjectDraft(maths)).toMatchObject({
      board: "unknown",
      tier: "unknown",
      setTexts: {},
    });
  });

  it("should key custom subjects ignoring case and spacing", () => {
    expect(customKey("  Art ")).toBe(customKey("art"));
    expect(newCustomDraft(" Statistics ").customName).toBe("Statistics");
  });

  it("should pre-fill from saved subjects", () => {
    const saved: EnrolmentOut[] = [
      {
        id: "00000000-0000-4000-8000-000000000018",
        subjectId: "00000000-0000-4000-8000-000000000004",
        subjectName: "English Literature",
        isCustom: false,
        boardId: "00000000-0000-4000-8000-000000000001",
        boardName: "AQA",
        boardConfirmed: true,
        tier: null,
        tierConfirmed: true,
        status: "active",
        specification: null,
        setTexts: [
          {
            id: "00000000-0000-4000-8000-000000000012",
            category: "Shakespeare play",
            optionId: "00000000-0000-4000-8000-000000000007",
            title: "Macbeth",
            author: null,
            status: "active",
          },
          {
            id: "00000000-0000-4000-8000-000000000013",
            category: "19th-century novel",
            optionId: null,
            title: "Frankenstein",
            author: null,
            status: "pending",
          },
        ],
      },
      {
        id: "00000000-0000-4000-8000-000000000019",
        subjectId: null,
        subjectName: "Statistics",
        isCustom: true,
        boardId: null,
        boardName: null,
        boardConfirmed: false,
        tier: "higher",
        tierConfirmed: false,
        status: "pending",
        specification: null,
        setTexts: [],
      },
    ];

    const [english, stats] = draftsFromEnrolments(saved);

    expect(english).toMatchObject({
      key: "00000000-0000-4000-8000-000000000004",
      board: "00000000-0000-4000-8000-000000000001",
      setTexts: {
        "Shakespeare play": { kind: "option", optionId: "00000000-0000-4000-8000-000000000007" },
        "19th-century novel": { kind: "custom", title: "Frankenstein" },
      },
    });
    expect(stats).toMatchObject({
      key: "custom:statistics",
      customName: "Statistics",
      board: "unknown",
      tier: "unknown",
    });
  });
});

describe("board and spec", () => {
  it("should fall back to the most common board when unknown", () => {
    const draft = newSubjectDraft(maths);

    expect(effectiveBoardId(draft, maths)).toBe("00000000-0000-4000-8000-000000000002");
    expect(specFor(draft, maths)?.code).toBe("1MA1");
  });

  it("should find no spec for a board without one", () => {
    const draft = { ...newSubjectDraft(maths), board: "00000000-0000-4000-8000-000000000001" };

    expect(specFor(draft, maths)).toBeUndefined();
  });

  it("should have no board for an unknown typed-in subject", () => {
    expect(effectiveBoardId(newCustomDraft("Art"), undefined)).toBeNull();
  });
});

describe("toChoices", () => {
  it("should send nulls for don't know and omit tier for untiered subjects", () => {
    const choices = toChoices(
      [newSubjectDraft(maths), { ...newSubjectDraft(englit), tier: "higher" }],
      CATALOGUE,
    );

    expect(choices).toEqual([
      {
        subjectId: "00000000-0000-4000-8000-000000000003",
        boardId: null,
        tier: null,
        setTexts: [],
      },
      {
        subjectId: "00000000-0000-4000-8000-000000000004",
        boardId: null,
        tier: null,
        setTexts: [],
      },
    ]);
  });

  it("should send chosen board and tier", () => {
    const [choice] = toChoices(
      [
        {
          ...newSubjectDraft(maths),
          board: "00000000-0000-4000-8000-000000000002",
          tier: "foundation",
        },
      ],
      CATALOGUE,
    );

    expect(choice).toMatchObject({
      boardId: "00000000-0000-4000-8000-000000000002",
      tier: "foundation",
    });
  });

  it("should keep listed and typed set texts and drop blanks and stale options", () => {
    const draft = {
      ...newSubjectDraft(englit),
      setTexts: {
        "Shakespeare play": {
          kind: "option" as const,
          optionId: "00000000-0000-4000-8000-000000000007",
        },
        "19th-century novel": { kind: "custom" as const, title: "  A Christmas Carol " },
        Blank: { kind: "custom" as const, title: "   " },
        Skipped: { kind: "none" as const },
      },
    };
    const onOtherBoard = { ...draft, key: "x", board: "00000000-0000-4000-8000-000000000002" };

    const [onList, notOnList] = toChoices([draft, onOtherBoard], CATALOGUE);

    expect(onList?.setTexts).toEqual([
      { category: "Shakespeare play", optionId: "00000000-0000-4000-8000-000000000007" },
      { category: "19th-century novel", customTitle: "A Christmas Carol" },
    ]);
    expect(notOnList?.setTexts).toEqual([
      { category: "19th-century novel", customTitle: "A Christmas Carol" },
    ]);
  });

  it("should send typed-in subjects by name", () => {
    expect(toChoices([newCustomDraft("Statistics")], CATALOGUE)).toEqual([
      { customName: "Statistics", boardId: null, tier: null, setTexts: [] },
    ]);
  });
});
