import { describe, expect, it } from "vitest";
import { analyze } from "../src/index.js";

describe("analyze", () => {
  it("is not implemented yet", () => {
    expect(() => analyze({ sourceDir: ".", schemaPath: "schema.prisma" })).toThrow(
      "not implemented",
    );
  });
});
