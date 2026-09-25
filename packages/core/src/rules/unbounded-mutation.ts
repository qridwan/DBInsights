import type { Finding } from "../models.js";
import { callEvidence, callLabel, codeBlock, delegateName, fingerprint, where, type Rule } from "./support.js";

export const UNBOUNDED_MUTATION = "UNBOUNDED_MUTATION";

const BULK_MUTATIONS = new Set(["deleteMany", "updateMany", "updateManyAndReturn"]);

/** R3: a bulk mutation with no `where`, affecting every row of the table. */
export const unboundedMutation: Rule = (context) =>
  context.operations.flatMap((operation): Finding[] => {
    if (!BULK_MUTATIONS.has(operation.operation) || !operation.argsResolved) return [];
    const missing = !operation.args.hasWhere;
    if (!missing && !operation.whereEmpty) return [];

    return [
      {
        schemaVersion: 1,
        ruleId: UNBOUNDED_MUTATION,
        severity: "HIGH",
        confidence: missing ? "HIGH" : "MEDIUM",
        file: operation.file,
        line: operation.line,
        title: `Unbounded \`${callLabel(operation)}\` affects every ${operation.model} row`,
        body:
          `\`${callLabel(operation)}\` in ${where(operation)} has ${missing ? "no `where` argument" : "an empty `where`"}, ` +
          `so it ${operation.operation === "deleteMany" ? "deletes" : "updates"} every row in ${operation.model}.`,
        evidence: [
          callEvidence(operation, missing ? "No `where` argument" : "`where` is statically empty", {
            operation: operation.operation,
          }),
        ],
        suggestedFix: codeBlock(
          "ts",
          [
            `await prisma.${delegateName(operation.model)}.${operation.operation}({`,
            "  where: { /* the rows this operation is meant to affect */ },",
            ...(operation.operation === "deleteMany" ? [] : ["  data: { /* ... */ },"]),
            "});",
          ].join("\n"),
        ),
        fingerprint: fingerprint(UNBOUNDED_MUTATION, operation.file, operation.enclosingFunction, operation.normalizedCall),
      },
    ];
  });
