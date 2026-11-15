# Curriculum data

Everything the app teaches and tests comes from these files. They are copied
**word for word** from each exam board's official specification PDF; nothing is
generated or paraphrased (ADR-012).

```
catalogue.yaml          exam boards + subjects shown on the student's setup screen
template.yaml           a blank spec file to copy
specs/<board>-<code>.yaml   one exact version of one board's specification
```

## How the files get into the app

The `migrate` service imports this folder on every start (`docker compose up`),
after the database migrations. To check files without importing anything, run:

```bash
docker compose run --rm api python -m app.cli.import_curriculum --check /app/curriculum
```

If any file is invalid, **nothing** is imported and the error lists each
problem with its location (e.g. `topics.0.subtopics.1.objectives.2: …`).

Importing a spec also switches on any of the student's subjects that were
waiting for it ("being set up"), and matches any set texts he typed in that
exactly match a title on the board's list.

## Adding or finishing a specification

1. Download the PDF from the board's website, and note the **issue/version and
   date** printed in its footer. Use only that version.
2. Copy `template.yaml` to `specs/<board>-<code>.yaml` (e.g. `specs/aqa-8464.yaml`).
3. Fill in the `specification:` header. `board` and `subject` must match codes
   in `catalogue.yaml`.
4. For each section of the subject content, add a topic, its subtopic headings,
   and every numbered statement:
   - `ref`: the statement's own reference (`N1`, `4.1.2.3`, …).
   - `foundation`: the statement as printed. For **tiered** specs this is the
     Foundation-tier wording; leave it out if the statement is Higher-only.
     For **untiered** specs, put all wording here.
   - `higher`: only for tiered specs, and only when the Higher-tier wording is
     different (usually longer).
   - `keywords`: a few phrases copied **exactly** from the wording. The importer
     rejects a keyword that isn't in the statement.
   - `out_of_scope` (optional): notes from the spec on what is *not* required.
5. Write fractions and superscripts that the PDF typesets as LaTeX between
   `$…$`, e.g. `$\frac{7}{2}$`, `$10^{n}$`. Keep everything else exactly as printed.
6. If you can't read something clearly, write `TODO` in it. The importer refuses
   files containing `TODO`, so unfinished statements never reach the student.
7. For English Literature, list the board's set texts under `set_texts:`, using
   the categories from `catalogue.yaml`.
8. Run the `--check` command above, then restart (`docker compose up -d`).

A newer issue of the same spec gets its own `version:`. When imported with
`current: true`, it becomes the version used for new and pending subjects.
Students already on the older version stay on it until the admin moves them.

## Status

Every subject in `catalogue.yaml` has a spec on its most common board. A
student on another board waits as "being set up" until that board's spec is
added (ADR-012).

| File | Spec | Version | Statements |
|---|---|---|---|
| `specs/pearson-edexcel-1ma1.yaml` | Pearson Edexcel Maths 1MA1 | Issue 2 – June 2015 | 97 (all 6 topics) |
| `specs/aqa-8700.yaml` | AQA English Language 8700 | Version 1.5 14 October 2021 | 9 |
| `specs/aqa-8702.yaml` | AQA English Literature 8702 (with set texts) | Version 1.3 28 September 2022 | 11 |
| `specs/aqa-8464.yaml` | AQA Combined Science: Trilogy 8464 | Version 1.1 04 October 2019 | 216 |
| `specs/aqa-8461.yaml` | AQA Biology 8461 | Version 1.0 21 April 2016 | 97 |
| `specs/aqa-8462.yaml` | AQA Chemistry 8462 | Version 1.1 04 October 2019 | 124 |
| `specs/aqa-8463.yaml` | AQA Physics 8463 | Version 1.1 30 September 2019 | 81 |
| `specs/aqa-8035.yaml` | AQA Geography 8035 | Version 1.1 12 September 2023 | 56 |
| `specs/pearson-edexcel-1hi0.yaml` | Pearson Edexcel History 1HI0 | Issue 6 – June 2024 | 213 |
| `specs/aqa-8062.yaml` | AQA Religious Studies A 8062 | Version 1.2 10 November 2017 | 236 |
| `specs/ocr-j277.yaml` | OCR Computer Science J277 | Version 3.1 | 26 |
| `specs/aqa-8652.yaml` | AQA French 8652 | Version 1.0 June 2023 | 43 |
| `specs/aqa-8692.yaml` | AQA Spanish 8692 | Version 1.0 8 December 2023 | 41 |

How each was copied is described at the top of its file. In short (ADR-017):

- Wording is copied from the PDF text layer by small scripts, then checked by
  hand; typeset maths is transcribed into LaTeX, scripts into Unicode.
- Diagrams, structural formulae and tables printed as images are not
  reproduced (nothing is invented in their place).
- Where students choose options (History options, RS religions and themes,
  Geography landscapes), every option is included; the topic map lets the
  admin mark which are "covered at school".
- Language vocabulary lists aren't statements; they're not copied.
