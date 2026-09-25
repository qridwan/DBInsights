import { describe, expect, it } from "vitest";
import { analyze } from "../src/index.js";

describe("analyze", () => {
  it("rejects a missing schema file", async () => {
    await expect(analyze({ sourceDir: ".", schemaPath: "does-not-exist.prisma" })).rejects.toThrow(/ENOENT/);
  });
});
