import type { AnalysisContext } from "../analyze/types.js";
import type { Finding } from "../models.js";
import { missingIndexOnFilteredField } from "./missing-index-on-filtered-field.js";
import { missingPagination } from "./missing-pagination.js";
import { nPlusOneInLoop } from "./n-plus-one-in-loop.js";
import { sequentialIndependentAwaits } from "./sequential-independent-awaits.js";
import type { Rule } from "./support.js";
import { unboundedMutation } from "./unbounded-mutation.js";

export const RULES: readonly Rule[] = [
  nPlusOneInLoop,
  missingIndexOnFilteredField,
  unboundedMutation,
  sequentialIndependentAwaits,
  missingPagination,
];

export function runRules(context: AnalysisContext): Finding[] {
  return RULES.flatMap((rule) => rule(context)).sort(
    (a, b) => a.file.localeCompare(b.file) || a.line - b.line || a.ruleId.localeCompare(b.ruleId),
  );
}
