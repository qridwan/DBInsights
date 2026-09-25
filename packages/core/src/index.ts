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

/**
 * Static analysis of a Prisma project: application source plus the declared
 * schema. Needs no database connection.
 */
export async function analyze(input: AnalyzeInput): Promise<Finding[]> {
  const sourceDir = resolve(input.sourceDir);
  const schemaPath = resolve(input.schemaPath);
  const schema = parseSchema(await readFile(schemaPath, "utf8"));

  // Generated Prisma client code is not application code.
  const generatedDirs = schema.generators.flatMap((generator) =>
    generator.output ? [resolve(dirname(schemaPath), generator.output)] : [],
  );
  const project = loadSourceProject(sourceDir, generatedDirs);
  const schemaFile = relative(sourceDir, schemaPath).split(sep).join("/");

  return runRules(buildAnalysisContext(project, schema, { rootDir: sourceDir, schemaFile }));
}
