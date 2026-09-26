import { readFile } from "node:fs/promises";
import { dirname, relative, resolve, sep } from "node:path";
import { buildAnalysisContext } from "./analyze/context.js";
import { loadSourceProject } from "./analyze/project.js";
import type { AnalyzeInput, Finding } from "./models.js";
import { runRules } from "./rules/index.js";
import { parseSchema } from "./schema/parse.js";

export type {
  AnalyzeInput,
  Confidence,
  Evidence,
  EvidenceSource,
  Finding,
  Severity,
} from "./models.js";
export { parseSchema, SchemaParseError } from "./schema/parse.js";
export type * from "./schema/types.js";
export type * from "./analyze/types.js";
export { RULES, runRules } from "./rules/index.js";

async function buildContext(input: AnalyzeInput) {
  const sourceDir = resolve(input.sourceDir);
  const schemaPath = input.schemaPath ? resolve(input.schemaPath) : undefined;
  const schema = schemaPath ? parseSchema(await readFile(schemaPath, "utf8")) : undefined;

  // Generated Prisma client code is not application code.
  const generatedDirs = (schema?.generators ?? []).flatMap((generator) =>
    generator.output && schemaPath ? [resolve(dirname(schemaPath), generator.output)] : [],
  );
  const project = loadSourceProject(sourceDir, generatedDirs);
  const schemaFile = schemaPath ? relative(sourceDir, schemaPath).split(sep).join("/") : "";
  return { project, context: buildAnalysisContext(project, schema, { rootDir: sourceDir, schemaFile }) };
}

/**
 * Static analysis of a Prisma project: application source plus the declared
 * schema. Needs no database connection.
 */
export async function analyze(input: AnalyzeInput): Promise<Finding[]> {
  return runRules((await buildContext(input)).context);
}

export interface Coverage {
  /** Source files the analyzer loaded. */
  sourceFiles: number;
  /** Prisma model operations it located (each is something a rule can judge). */
  ormOperations: number;
  byOperation: Record<string, number>;
}

/**
 * How much of a project the analyzer can see, independent of any rule: files loaded and Prisma
 * operations located. Zero operations in a project that plainly uses Prisma means the analyzer
 * did not recognise its client, so an absence of findings there is not evidence of clean code.
 */
export async function coverage(input: AnalyzeInput): Promise<Coverage> {
  const { project, context } = await buildContext(input);
  const byOperation: Record<string, number> = {};
  for (const operation of context.operations) {
    byOperation[operation.operation] = (byOperation[operation.operation] ?? 0) + 1;
  }
  return { sourceFiles: project.getSourceFiles().length, ormOperations: context.operations.length, byOperation };
}
