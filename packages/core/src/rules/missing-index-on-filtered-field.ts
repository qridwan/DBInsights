import type { Finding } from "../models.js";
import type { Model } from "../schema/types.js";
import { callEvidence, callLabel, codeBlock, fingerprint, where, type Rule } from "./support.js";

export const MISSING_INDEX_ON_FILTERED_FIELD = "MISSING_INDEX_ON_FILTERED_FIELD";

/** Only operations that scan by a non-unique filter; unique lookups always hit an index. */
const FILTERING_OPERATIONS = new Set(["findMany", "findFirst", "findFirstOrThrow", "count"]);

/**
 * Maps a `where` key to the column it filters on: the field itself for
 * scalars and enums; the leading FK column for a relation filter whose FK
 * lives on this model. Other relation filters are joins on the other table
 * and are not judged here.
 */
function filteredColumn(model: Model, key: string): string | undefined {
  const field = model.fields.find((candidate) => candidate.name === key);
  if (!field) return undefined;
  if (field.kind === "scalar" || field.kind === "enum") return field.name;
  if (field.kind === "relation") {
    const relation = model.relations.find((candidate) => candidate.field === key);
    return relation?.foreignKeyOn === "self" ? relation.fields[0] : undefined;
  }
  return undefined;
}

function isLeadingIndexColumn(model: Model, column: string): boolean {
  return model.indexes.some((index) => index.fields[0]?.name === column);
}

/**
 * R2: a non-unique query filters only on columns that no declared index can
 * serve. Conservative by design: if ANY filtered column is the leading column
 * of a declared index (@id, @unique, @@id, @@unique, @@index), the planner has
 * an index to start from and the query is not reported.
 */
export const missingIndexOnFilteredField: Rule = (context) =>
  context.operations.flatMap((operation): Finding[] => {
    if (!FILTERING_OPERATIONS.has(operation.operation)) return [];
    if (!operation.argsResolved || !operation.whereResolved || !operation.args.hasWhere) return [];

    const model = context.schema.models.find((candidate) => candidate.name === operation.model);
    if (!model || model.blockType !== "model") return [];

    const columns = [
      ...new Set(operation.args.whereFields.flatMap((key) => filteredColumn(model, key) ?? [])),
    ];
    if (columns.length === 0) return [];
    if (columns.some((column) => isLeadingIndexColumn(model, column))) return [];

    const fields = columns.map((column) => model.fields.find((field) => field.name === column));
    const lowSelectivity = fields.every((field) => field?.kind === "enum" || field?.type === "Boolean");
    const list = columns.map((column) => `\`${column}\``).join(", ");
    const declared = model.indexes.map((index) => `${index.kind}(${index.fields.map((f) => f.name).join(", ")})`);

    return [
      {
        schemaVersion: 1,
        ruleId: MISSING_INDEX_ON_FILTERED_FIELD,
        severity: "HIGH",
        confidence: lowSelectivity ? "LOW" : "MEDIUM",
        file: operation.file,
        line: operation.line,
        title: `No declared index covers the filter on ${model.name}.${columns.join(", ")}`,
        body:
          `\`${callLabel(operation)}\` in ${where(operation)} filters ${model.name} by ${list}, ` +
          `but schema.prisma declares no index whose leading column is ${columns.length > 1 ? "any of these" : "this field"}. ` +
          `Without one, PostgreSQL must scan the table for every call.` +
          (lowSelectivity
            ? ` The filtered field${columns.length > 1 ? "s are" : " is"} boolean or enum typed; an index helps only if the matching values are rare.`
            : ""),
        evidence: [
          callEvidence(operation, `\`${callLabel(operation)}\` filters on ${list}`, { whereFields: operation.args.whereFields }),
          {
            source: "DECLARED_SCHEMA",
            description:
              declared.length > 0
                ? `Declared indexes on ${model.name}: ${declared.join("; ")}. None leads with ${list}.`
                : `${model.name} declares no indexes.`,
            file: context.schemaFile,
            line: model.line,
            data: { model: model.name, indexes: declared },
          },
        ],
        suggestedFix: codeBlock(
          "prisma",
          `
model ${model.name} {
  // ...existing fields
  @@index([${columns.join(", ")}])
}
`,
        ),
        fingerprint: fingerprint(
          MISSING_INDEX_ON_FILTERED_FIELD,
          operation.file,
          operation.enclosingFunction,
          `${operation.normalizedCall}:${columns.join(",")}`,
        ),
      },
    ];
  });
