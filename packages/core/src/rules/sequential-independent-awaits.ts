import type { Finding } from "../models.js";
import { callEvidence, callLabel, codeBlock, delegateName, fingerprint, type Rule } from "./support.js";

export const SEQUENTIAL_INDEPENDENT_AWAITS = "SEQUENTIAL_INDEPENDENT_AWAITS";

/** R4: independent Prisma reads awaited one after another instead of concurrently. */
export const sequentialIndependentAwaits: Rule = (context) =>
  context.independentAwaitGroups.flatMap((group): Finding[] => {
    const operations = group.operations.flatMap((index) => context.operations[index] ?? []);
    const first = operations[0];
    const last = operations.at(-1);
    if (!first || !last || operations.length < 2) return [];

    const labels = operations.map((operation) => `\`${callLabel(operation)}\``).join(", ");
    const names = operations.map((operation, i) => `${delegateName(operation.model)}${i + 1}`);

    return [
      {
        schemaVersion: 1,
        ruleId: SEQUENTIAL_INDEPENDENT_AWAITS,
        severity: "MEDIUM",
        confidence: "HIGH",
        file: first.file,
        line: first.line,
        endLine: last.line,
        title: `${operations.length} independent queries awaited sequentially`,
        body:
          `${labels} are awaited one after another in ${first.enclosingFunction ? `\`${first.enclosingFunction}\`` : "module scope"}, ` +
          `but none uses a value produced by another. Each waits a full round trip for the previous one; running them concurrently costs one.`,
        evidence: operations.map((operation, i) =>
          callEvidence(
            operation,
            i === 0
              ? `\`${callLabel(operation)}\` awaited first`
              : `\`${callLabel(operation)}\` awaited next; references no binding from the earlier queries (symbol analysis)`,
          ),
        ),
        suggestedFix: codeBlock(
          "ts",
          `
const [${names.join(", ")}] = await Promise.all([
${operations.map((operation) => `  prisma.${delegateName(operation.model)}.${operation.operation}(/* ... */),`).join("\n")}
]);
`,
        ),
        fingerprint: fingerprint(
          SEQUENTIAL_INDEPENDENT_AWAITS,
          first.file,
          first.enclosingFunction,
          operations.map((operation) => operation.normalizedCall).join("+"),
        ),
      },
    ];
  });
