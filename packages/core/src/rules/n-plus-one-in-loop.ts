import type { Evidence, Finding } from "../models.js";
import { callEvidence, callLabel, codeBlock, delegateName, fingerprint, where, type Rule } from "./support.js";

export const N_PLUS_ONE_IN_LOOP = "N_PLUS_ONE_IN_LOOP";

/** R1: a Prisma call executed once per loop iteration. */
export const nPlusOneInLoop: Rule = (context) =>
  context.operations.flatMap((operation): Finding[] => {
    const loop = operation.loopContext;
    if (!loop) return [];

    const source = loop.iteratesOverORMResult
      ? context.operations.find((other) => other.file === operation.file && other.line === loop.sourceOperationLine)
      : undefined;

    const evidence: Evidence[] = [
      callEvidence(operation, `\`${callLabel(operation)}\` runs inside a ${loop.loopKind} loop`, {
        loopKind: loop.loopKind,
        loopLine: loop.loopLine,
      }),
    ];
    if (loop.iteratesOverORMResult && loop.sourceOperationLine !== null) {
      evidence.push({
        source: "STATIC_SOURCE",
        description: `The loop iterates over the result of ${source ? `\`${callLabel(source)}\`` : "a Prisma call"} (resolved via symbol analysis)`,
        file: operation.file,
        line: loop.sourceOperationLine,
      });
    }

    const model = delegateName(operation.model);
    return [
      {
        schemaVersion: 1,
        ruleId: N_PLUS_ONE_IN_LOOP,
        severity: "HIGH",
        confidence: loop.iteratesOverORMResult ? "HIGH" : "MEDIUM",
        file: operation.file,
        line: operation.line,
        title: `N+1 query: \`${callLabel(operation)}\` inside a loop`,
        body:
          `\`${callLabel(operation)}\` in ${where(operation)} runs once per iteration of the ${loop.loopKind} loop on line ${loop.loopLine}` +
          (loop.iteratesOverORMResult
            ? `, which iterates over rows returned by the query on line ${loop.sourceOperationLine}. The number of queries grows with the number of rows.`
            : `. The loop's collection could not be traced to a Prisma query, so the row count driving it is unknown.`),
        evidence,
        suggestedFix: codeBlock(
          "ts",
          `
// Load the related rows with the parent query instead of one query per row:
//   include: { <relation>: true }
// or batch the lookup into a single query keyed by the collected ids:
const rows = await prisma.${model}.${operation.operation}({
  where: { <key>: { in: ids } },
});
`,
        ),
        fingerprint: fingerprint(N_PLUS_ONE_IN_LOOP, operation.file, operation.enclosingFunction, operation.normalizedCall),
      },
    ];
  });
