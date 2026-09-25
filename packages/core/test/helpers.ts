import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { loadSourceProject } from "../src/analyze/project.js";
import { locateOrmCalls, type LocatedOperation } from "../src/analyze/orm-calls.js";
import { parseSchema } from "../src/schema/parse.js";
import type { ORMOperation } from "../src/analyze/types.js";

export const FIXTURES = fileURLToPath(new URL("../../../fixtures/", import.meta.url));
export const SOURCE_SCHEMA_PATH = join(FIXTURES, "source", "schema.prisma");
export const SOURCE_SCHEMA = parseSchema(readFileSync(SOURCE_SCHEMA_PATH, "utf8"));

export function sourceDir(name: string): string {
  return join(FIXTURES, "source", name);
}

export function locateFixture(name: string): LocatedOperation[] {
  const rootDir = sourceDir(name);
  return locateOrmCalls(loadSourceProject(rootDir), { rootDir, schema: SOURCE_SCHEMA });
}

/** Operations in `file`, keyed as `enclosingFunction:model.operation`. */
export function summarize(operations: ORMOperation[], file: string): string[] {
  return operations
    .filter((op) => op.file === file)
    .map((op) => `${op.enclosingFunction ?? "<module>"}:${op.model}.${op.operation}`);
}
