# Labelling protocol (DRAFT, for the author to review before any labelling starts)

Written before any finding was looked at. Nothing has been labelled. Changing this after labelling
starts invalidates the labels already made; if it must change, start over and record why.

## The unit and the question

One row of `labelling/worksheet.csv` is one finding. The question for every row is:

> **Is the claim the finding makes true of this code, in the context of this project?**

Judge the code, not the analyzer's confidence: confidence and severity are hidden from the
worksheet on purpose (`worksheet_key.csv` holds them, joined by `finding_id` at analysis time).
Read the source context and schema excerpt in the row; open the repository at the pinned commit
if the row is not enough. Do not run the analyzer again to "check".

## Labels (column `label`)

| Value | Meaning |
|---|---|
| `TP` | The pattern the finding names is really there, and it has the consequence the finding describes for this code. |
| `FP` | The claim is false for this code, or the pattern is there but the consequence cannot happen here (see causes below). |
| `UNSURE` | You cannot decide from the code and one hour's reading of the project. `rationale` is required. Reported separately; never counted as either. |

"Would I fix this?" is **not** the test. A true pattern in code that does not matter (a bounded
table, a one-off script) is still a `TP` if the claim is true; note it in `rationale`. Use the
rule-specific tests below.

## Rule-specific tests

| Rule | `TP` when | `FP` when |
|---|---|---|
| `N_PLUS_ONE_IN_LOOP` | A database call executes once per iteration of a loop over rows that came from an earlier query, so query count grows with the number of rows. | The loop is over a fixed or tiny in-memory list, the call is not on each iteration, or the "loop" is not one. |
| `MISSING_INDEX_ON_FILTERED_FIELD` | The field is filtered on in a query, and `schema.prisma` declares no index (or unique/PK) that leads with it. | An index does declare it (misread schema), the filter cannot use an index, or the table is a fixed tiny lookup. |
| `UNBOUNDED_MUTATION` | `deleteMany` / `updateMany` really runs with no `where` filter. | A filter is present but was not seen (spread, shorthand, variable), or the call is a deliberate reset in test or seed code. |
| `SEQUENTIAL_INDEPENDENT_AWAITS` | The awaited calls do not depend on each other and could run concurrently. | One depends on another (data, ordering, a transaction), or they must be sequential. |
| `MISSING_PAGINATION` | A `findMany` on a table that can grow returns all rows to a caller with no `take` / `skip` / `cursor`. | The result is bounded another way (filter on a unique key, small enum table) or a bound is applied elsewhere. |

## Why a `FP` is a `FP` (column `fp_cause`, required for every `FP`)

Exactly one of:

| Cause | Meaning |
|---|---|
| `analysis_error` | The analyzer misread the code: wrong type, wrong loop, wrong data flow, unresolved import. |
| `schema_misread` | The analyzer misread the declared schema (an index that is declared, a field that maps elsewhere). |
| `pattern_harmless_here` | The pattern is real but harmless in this context (bounded data, admin-only, batch job). |
| `not_application_code` | Test, seed, script, or migration code. |
| `index_outside_schema` | The claim is about a missing index, but the index exists in the database and is not declared in `schema.prisma`. Needs the project's migrations or SQL to show. |
| `other` | Say what in `rationale`. |

`fp_cause` stays empty for `TP` and `UNSURE`.

## Independence and disagreement

- `double_label` = `yes` rows (at least 20% of every rule's findings, fixed by seed before
  labelling) are labelled by a **second person** in `label_2` / `fp_cause_2` / `rationale_2`,
  without seeing the first person's columns. Hide those columns before handing the file over.
- Disagreements are **never resolved by editing a label.** Both labels are kept. Cohen's kappa is
  computed on the two raw label columns. Adjudication, if any, is recorded separately and
  reported as such.
- Label in one sitting per repository where possible, so project context is fresh.
- Do not label a row you have any reason to think you already know the answer to from having
  built the analyzer's rule (for instance from a fixture); mark it `UNSURE` and say why.

## Known limits

- The author built the analyzer and is likely to be the first labeller: that is the reason for
  the second labeller, and it is reported.
- `index_outside_schema` can only be established for projects whose migrations or SQL are in the
  repository. For the rest the true figure cannot be measured and is reported as a bound.
