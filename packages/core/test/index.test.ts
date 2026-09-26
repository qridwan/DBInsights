import { describe, expect, it } from "vitest";
import { analyze, coverage } from "../src/index.js";
import { SOURCE_SCHEMA_PATH, sourceDir } from "./helpers.js";

describe("analyze", () => {
  it("rejects a missing schema file", async () => {
    await expect(analyze({ sourceDir: ".", schemaPath: "does-not-exist.prisma" })).rejects.toThrow(/ENOENT/);
  });
});

describe("coverage", () => {
  it("counts the files loaded and the Prisma operations located, by operation", async () => {
    const result = await coverage({ sourceDir: sourceDir("rules/unbounded-mutation"), schemaPath: SOURCE_SCHEMA_PATH });
    expect(result.sourceFiles).toBeGreaterThan(0);
    expect(result.ormOperations).toBeGreaterThan(0);
    expect(Object.values(result.byOperation).reduce((a, b) => a + b, 0)).toBe(result.ormOperations);
    expect(result.byOperation).toHaveProperty("deleteMany");
  });

  it("reports zero operations for code that does not use Prisma, so silence can be told from cleanliness", async () => {
    const result = await coverage({ sourceDir: sourceDir("orm-calls"), schemaPath: SOURCE_SCHEMA_PATH });
    expect(result.ormOperations).toBeGreaterThan(0);
    const none = await coverage({ sourceDir: sourceDir("dataflow"), schemaPath: SOURCE_SCHEMA_PATH });
    expect(none.sourceFiles).toBeGreaterThan(0);
    expect(typeof none.ormOperations).toBe("number");
  });

  it("does not need a schema", async () => {
    const result = await coverage({ sourceDir: sourceDir("no-schema") });
    expect(result.ormOperations).toBeGreaterThan(0);
  });
});
