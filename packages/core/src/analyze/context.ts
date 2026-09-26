import type { Project } from "ts-morph";
import type { SchemaModel } from "../schema/types.js";
import { findIndependentAwaitGroups } from "./await-groups.js";
import { resolveLoopSources } from "./dataflow.js";
import { locateOrmCalls } from "./orm-calls.js";
import type { AnalysisContext } from "./types.js";

const EMPTY_SCHEMA: SchemaModel = { datasources: [], generators: [], models: [], enums: [], types: [] };

/**
 * Runs every syntax-level pass (call location, data-flow, await grouping) and
 * returns plain data. Rules only ever see this context, never the AST.
 */
export function buildAnalysisContext(
  project: Project,
  schema: SchemaModel | undefined,
  options: { rootDir: string; schemaFile: string },
): AnalysisContext {
  // Without a schema, delegates are taken at their word (`prisma.user` is `User`) and the
  // context carries an empty schema, so rules that judge indexes find nothing to judge.
  const located = locateOrmCalls(project, { rootDir: options.rootDir, ...(schema ? { schema } : {}) });
  resolveLoopSources(located);
  return {
    schema: schema ?? EMPTY_SCHEMA,
    schemaFile: options.schemaFile,
    operations: located.map((entry) => entry.operation),
    independentAwaitGroups: findIndependentAwaitGroups(located),
  };
}
