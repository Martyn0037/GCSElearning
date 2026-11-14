// frontend/src/test/catalogue.ts
// A small catalogue shared by tests (not real exam board data).
// IDs are UUIDs because the API client validates them; legend:
//   00000000-0000-4000-8000-000000000001 = b-aqa
//   00000000-0000-4000-8000-000000000002 = b-edx
//   00000000-0000-4000-8000-000000000003 = s-maths
//   00000000-0000-4000-8000-000000000004 = s-englit
//   00000000-0000-4000-8000-000000000005 = spec-1ma1
//   00000000-0000-4000-8000-000000000006 = spec-8702
//   00000000-0000-4000-8000-000000000007 = opt-macbeth
import type { CatalogueOut, CatalogueSubjectOut } from "../api/generated/model";

export const CATALOGUE: CatalogueOut = {
  boards: [
    { id: "00000000-0000-4000-8000-000000000001", code: "aqa", name: "AQA" },
    {
      id: "00000000-0000-4000-8000-000000000002",
      code: "pearson-edexcel",
      name: "Pearson Edexcel",
    },
  ],
  subjects: [
    {
      id: "00000000-0000-4000-8000-000000000003",
      slug: "maths",
      name: "Mathematics",
      hasTiers: true,
      setTextCategories: [],
      mostCommonBoardId: "00000000-0000-4000-8000-000000000002",
      specifications: [
        {
          id: "00000000-0000-4000-8000-000000000005",
          boardId: "00000000-0000-4000-8000-000000000002",
          code: "1MA1",
          title: "Maths",
          version: "Issue 2",
          tiered: true,
          setTexts: [],
        },
      ],
    },
    {
      id: "00000000-0000-4000-8000-000000000004",
      slug: "english-literature",
      name: "English Literature",
      hasTiers: false,
      setTextCategories: ["Shakespeare play", "19th-century novel"],
      mostCommonBoardId: "00000000-0000-4000-8000-000000000001",
      specifications: [
        {
          id: "00000000-0000-4000-8000-000000000006",
          boardId: "00000000-0000-4000-8000-000000000001",
          code: "8702",
          title: "English Literature",
          version: "1.0",
          tiered: false,
          setTexts: [
            {
              id: "00000000-0000-4000-8000-000000000007",
              category: "Shakespeare play",
              title: "Macbeth",
              author: "William Shakespeare",
            },
          ],
        },
      ],
    },
  ],
};

/** The catalogue subject at ``index``; throws if missing so tests fail loudly. */
export function subjectAt(index: number): CatalogueSubjectOut {
  const subject = CATALOGUE.subjects[index];
  if (!subject) throw new Error(`No catalogue subject at ${index}`);
  return subject;
}
