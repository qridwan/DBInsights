import type { Finding } from "../models.js";
import { callEvidence, callLabel, codeBlock, delegateName, fingerprint, where, type Rule } from "./support.js";

export const MISSING_PAGINATION = "MISSING_PAGINATION";

/** R5: `findMany` with no `take`, `skip` or `cursor`: result size grows with the table. */
export const missingPagination: Rule = (context) =>
  context.operations.flatMap((operation): Finding[] => {
    if (operation.operation !== "findMany" || !operation.argsResolved) return [];
    const { hasTake, hasSkip, hasCursor, hasWhere } = operation.args;
    if (hasTake || hasSkip || hasCursor) return [];

    return [
      {
        schemaVersion: 1,
        ruleId: MISSING_PAGINATION,
        severity: "MEDIUM",
        confidence: hasWhere ? "MEDIUM" : "HIGH",
        file: operation.file,
        line: operation.line,
        title: `Unpaginated \`${callLabel(operation)}\``,
        body:
          `\`${callLabel(operation)}\` in ${where(operation)} has no \`take\`, \`skip\` or \`cursor\`, ` +
          (hasWhere
            ? `so it returns every ${operation.model} row matching its filter.`
            : `and no filter, so it returns the entire ${operation.model} table.`),
        evidence: [callEvidence(operation, "No `take`, `skip` or `cursor` argument", { hasWhere })],
        suggestedFix: codeBlock(
          "ts",
          `
await prisma.${delegateName(operation.model)}.findMany({
  // ...existing arguments
  take: pageSize,
  ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
  orderBy: { id: "asc" },
});
`,
        ),
        fingerprint: fingerprint(MISSING_PAGINATION, operation.file, operation.enclosingFunction, operation.normalizedCall),
      },
    ];
  });
