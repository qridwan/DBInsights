import type { Project } from "ts-morph";
import type { SchemaModel } from "../schema/types.js";
import { findIndependentAwaitGroups } from "./await-groups.js";
import { resolveLoopSources } from "./dataflow.js";
import { locateOrmCalls } from "./orm-calls.js";
import type { AnalysisContext } from "./types.js";

/**
 * Runs every syntax-level pass (call location, data-flow, await grouping) and
 * returns plain data. Rules only ever see this context, never the AST.
 */
export function buildAnalysisContext(
  project: Project,
  schema: SchemaModel,
  options: { rootDir: string; schemaFile: string },
): AnalysisContext {
  const located = locateOrmCalls(project, { rootDir: options.rootDir, schema });
  resolveLoopSources(located);
  return {
    schema,
    schemaFile: options.schemaFile,
    operations: located.map((entry) => entry.operation),
    independentAwaitGroups: findIndependentAwaitGroups(located),
  };
}
