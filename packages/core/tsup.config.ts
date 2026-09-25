import { defineConfig } from "tsup";

export default defineConfig([
  {
    entry: ["src/index.ts"],
    format: ["esm", "cjs"],
    dts: true,
    sourcemap: true,
    target: "node22",
  },
  {
    // Subprocess entry for the Python services (JSON over stdin/stdout).
    entry: ["src/cli.ts"],
    format: ["esm"],
    sourcemap: true,
    target: "node22",
  },
]);
