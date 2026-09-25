import { existsSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { Project, ts } from "ts-morph";

const SOURCE_EXTENSIONS = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"];
const SKIPPED_DIRECTORIES = new Set(["node_modules", "dist", "build", "out", "coverage"]);

function isSourceFile(name: string): boolean {
  return !name.endsWith(".d.ts") && SOURCE_EXTENSIONS.some((ext) => name.endsWith(ext));
}

function collectSourceFiles(dir: string, excluded: Set<string>, files: string[]): void {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name.startsWith(".") || SKIPPED_DIRECTORIES.has(entry.name) || excluded.has(path)) continue;
      collectSourceFiles(path, excluded, files);
    } else if (entry.isFile() && isSourceFile(entry.name)) {
      files.push(path);
    }
  }
}

/**
 * Loads every source file under `sourceDir` into a ts-morph project with a
 * working type checker. Uses the project's own tsconfig.json when present so
 * path aliases resolve.
 *
 * @param excludeDirs absolute directories to skip, e.g. generated Prisma client output
 */
export function loadSourceProject(sourceDir: string, excludeDirs: string[] = []): Project {
  const root = resolve(sourceDir);
  const tsConfigFilePath = join(root, "tsconfig.json");
  const project = existsSync(tsConfigFilePath)
    ? new Project({ tsConfigFilePath, skipAddingFilesFromTsConfig: true })
    : new Project({
        compilerOptions: {
          allowJs: true,
          jsx: ts.JsxEmit.Preserve,
          module: ts.ModuleKind.ESNext,
          moduleResolution: ts.ModuleResolutionKind.Bundler,
          target: ts.ScriptTarget.ES2022,
          strict: true,
          skipLibCheck: true,
          noEmit: true,
        },
      });

  const files: string[] = [];
  collectSourceFiles(root, new Set(excludeDirs.map((dir) => resolve(dir))), files);
  for (const file of files) project.addSourceFileAtPath(file);
  return project;
}
