import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { SOURCE_SCHEMA_PATH, sourceDir } from "./helpers.js";

const CLI = fileURLToPath(new URL("../dist/cli.js", import.meta.url));

function call(request: unknown): { ok: boolean; result?: unknown; error?: string } {
  try {
    return JSON.parse(execFileSync("node", [CLI], { input: JSON.stringify(request), encoding: "utf8" }));
  } catch (error) {
    return JSON.parse((error as { stdout: string }).stdout);
  }
}

// Exercises the built artifact: the exact thing the Python services spawn.
describe.skipIf(!existsSync(CLI))("JSON stdio contract (dist/cli.js)", () => {
  it("parses a schema", () => {
    const response = call({ command: "parseSchema", schemaPath: SOURCE_SCHEMA_PATH });
    expect(response.ok).toBe(true);
    expect((response.result as { models: { name: string }[] }).models.map((m) => m.name)).toContain("Invoice");
  });

  it("analyzes a project", () => {
    const response = call({ command: "analyze", sourceDir: sourceDir("rules/unbounded-mutation"), schemaPath: SOURCE_SCHEMA_PATH });
    expect(response.ok).toBe(true);
    expect((response.result as { ruleId: string }[]).some((f) => f.ruleId === "UNBOUNDED_MUTATION")).toBe(true);
  });

  it("analyzes a project without a schema", () => {
    const response = call({ command: "analyze", sourceDir: sourceDir("no-schema") });
    expect(response.ok).toBe(true);
    expect((response.result as { ruleId: string }[]).some((f) => f.ruleId === "N_PLUS_ONE_IN_LOOP")).toBe(true);
  });

  it("reports malformed requests as ok: false", () => {
    expect(call({ command: "nope" })).toMatchObject({ ok: false });
    expect(call({ command: "parseSchema", schemaPath: "/does/not/exist.prisma" })).toMatchObject({ ok: false });
  });
});
