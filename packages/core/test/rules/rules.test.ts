import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { analyze } from "../../src/index.js";
import type { Finding } from "../../src/models.js";
import { SOURCE_SCHEMA_PATH, sourceDir } from "../helpers.js";

async function findingsFor(dir: string, ruleId: string): Promise<Finding[]> {
  const findings = await analyze({ sourceDir: sourceDir(`rules/${dir}`), schemaPath: SOURCE_SCHEMA_PATH });
  return findings.filter((finding) => finding.ruleId === ruleId);
}

const summary = (findings: Finding[], file: string) =>
  findings.filter((f) => f.file === file).map((f) => ({ line: f.line, confidence: f.confidence }));

describe("R1 N_PLUS_ONE_IN_LOOP", async () => {
  const findings = await findingsFor("n-plus-one", "N_PLUS_ONE_IN_LOOP");

  it("fires HIGH over an ORM result and MEDIUM over an unresolved collection", () => {
    expect(summary(findings, "positive.ts")).toEqual([
      { line: 8, confidence: "HIGH" },
      { line: 15, confidence: "MEDIUM" },
    ]);
  });

  it("cites the originating query as data-flow evidence", () => {
    const high = findings.find((f) => f.confidence === "HIGH");
    expect(high?.evidence.map((e) => [e.source, e.line])).toEqual([
      ["STATIC_SOURCE", 8],
      ["STATIC_SOURCE", 5],
    ]);
  });

  it("does not fire on include, batched lookups, or a query used as the iterable", () => {
    expect(summary(findings, "near-miss.ts")).toEqual([]);
  });
});

describe("R2 MISSING_INDEX_ON_FILTERED_FIELD", async () => {
  const findings = await findingsFor("missing-index", "MISSING_INDEX_ON_FILTERED_FIELD");

  it("fires on unindexed, unindexed-FK, non-leading composite and boolean-only filters", () => {
    expect(
      findings.filter((f) => f.file === "positive.ts").map((f) => [f.line, f.confidence, f.title]),
    ).toEqual([
      [5, "MEDIUM", "No declared index covers the filter on Invoice.amountCents"],
      [10, "MEDIUM", "No declared index covers the filter on Invoice.teamId"],
      [15, "MEDIUM", "No declared index covers the filter on User.createdAt"],
      [20, "LOW", "No declared index covers the filter on User.active"],
    ]);
  });

  it("pairs source evidence with declared-schema evidence", () => {
    expect(findings[0]?.evidence.map((e) => [e.source, e.file])).toEqual([
      ["STATIC_SOURCE", "positive.ts"],
      ["DECLARED_SCHEMA", "../../schema.prisma"],
    ]);
    expect(findings[0]?.suggestedFix).toContain("@@index([amountCents])");
  });

  it("does not fire on covered, unique, mixed, joined, dynamic or non-filtering queries", () => {
    expect(summary(findings, "near-miss.ts")).toEqual([]);
  });
});

describe("R3 UNBOUNDED_MUTATION", async () => {
  const findings = await findingsFor("unbounded-mutation", "UNBOUNDED_MUTATION");

  it("fires HIGH with no where and MEDIUM with an empty where", () => {
    expect(summary(findings, "positive.ts")).toEqual([
      { line: 4, confidence: "HIGH" },
      { line: 8, confidence: "HIGH" },
      { line: 13, confidence: "MEDIUM" },
    ]);
  });

  it("does not fire on filtered, OR-only, caller-supplied or single-row mutations", () => {
    expect(summary(findings, "near-miss.ts")).toEqual([]);
  });
});

describe("R4 SEQUENTIAL_INDEPENDENT_AWAITS", async () => {
  const findings = await findingsFor("sequential-awaits", "SEQUENTIAL_INDEPENDENT_AWAITS");

  it("reports one finding spanning the independent run", () => {
    expect(findings.filter((f) => f.file === "positive.ts").map((f) => [f.line, f.endLine, f.evidence.length])).toEqual([
      [4, 6, 3],
    ]);
    expect(findings[0]?.suggestedFix).toContain("Promise.all");
  });

  it("does not fire on dependent, concurrent, guarded or write sequences", () => {
    expect(summary(findings, "near-miss.ts")).toEqual([]);
  });
});

describe("R5 MISSING_PAGINATION", async () => {
  const findings = await findingsFor("missing-pagination", "MISSING_PAGINATION");

  it("fires HIGH without a filter and MEDIUM with one", () => {
    expect(summary(findings, "positive.ts")).toEqual([
      { line: 5, confidence: "HIGH" },
      { line: 10, confidence: "MEDIUM" },
    ]);
  });

  it("does not fire with take, conditional cursor, unknown args or non-findMany", () => {
    expect(summary(findings, "near-miss.ts")).toEqual([]);
  });
});

describe("structured evidence for cross-layer joins", async () => {
  const mapped = await analyze({ sourceDir: sourceDir("mapped"), schemaPath: join(sourceDir("mapped"), "schema.prisma") });
  const byRule = (ruleId: string) => mapped.filter((f) => f.ruleId === ruleId);

  it("records the model and operation on every static-source evidence item", () => {
    for (const finding of mapped) {
      const source = finding.evidence.find((e) => e.source === "STATIC_SOURCE");
      expect(source?.data).toMatchObject({ model: "Ticket" });
      expect(typeof source?.data?.operation).toBe("string");
    }
  });

  it("gives the missing-index finding both database and Prisma names for table and columns", () => {
    const [finding] = byRule("MISSING_INDEX_ON_FILTERED_FIELD");
    const declared = finding?.evidence.find((e) => e.source === "DECLARED_SCHEMA");
    expect(declared?.data).toMatchObject({
      model: "Ticket",
      table: "tickets",
      columns: ["owner_id"],
      fields: ["ownerId"],
    });
  });

  it("uses the model name as the table when there is no @@map", async () => {
    const plain = await analyze({ sourceDir: sourceDir("rules/missing-index"), schemaPath: SOURCE_SCHEMA_PATH });
    const declared = plain.find((f) => f.title.includes("Invoice.amountCents"))?.evidence.find((e) => e.source === "DECLARED_SCHEMA");
    expect(declared?.data).toMatchObject({ table: "Invoice", columns: ["amountCents"], fields: ["amountCents"] });
  });
});

describe("every finding", async () => {
  const all = (
    await Promise.all(
      ["n-plus-one", "missing-index", "unbounded-mutation", "sequential-awaits", "missing-pagination"].map((dir) =>
        analyze({ sourceDir: sourceDir(`rules/${dir}`), schemaPath: SOURCE_SCHEMA_PATH }),
      ),
    )
  ).flat();

  it("carries schemaVersion, explicit confidence, evidence and a markdown code-block fix", () => {
    expect(all.length).toBeGreaterThan(0);
    for (const finding of all) {
      expect(finding.schemaVersion).toBe(1);
      expect(["LOW", "MEDIUM", "HIGH"]).toContain(finding.confidence);
      expect(finding.evidence.length).toBeGreaterThan(0);
      expect(finding.suggestedFix).toMatch(/^```\w+\n[\s\S]+\n```$/);
    }
  });

  it("has a unique fingerprint", () => {
    const keys = all.map((f) => `${f.ruleId}:${f.file}:${f.fingerprint}`);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("fingerprint stability", () => {
  const scratch = mkdtempSync(join(tmpdir(), "dbinsight-fp-"));
  afterAll(() => rmSync(scratch, { recursive: true, force: true }));

  it("is unchanged when unrelated lines shift", async () => {
    const original = sourceDir("rules/n-plus-one");
    const shifted = join(scratch, "n-plus-one");
    cpSync(original, shifted, { recursive: true });
    const file = join(shifted, "positive.ts");
    writeFileSync(file, `// unrelated\n// lines\n\n${readFileSync(file, "utf8")}`);

    const before = await analyze({ sourceDir: original, schemaPath: SOURCE_SCHEMA_PATH });
    const after = await analyze({ sourceDir: shifted, schemaPath: SOURCE_SCHEMA_PATH });

    expect(after.map((f) => f.line)).not.toEqual(before.map((f) => f.line));
    expect(after.map((f) => f.fingerprint)).toEqual(before.map((f) => f.fingerprint));
  });
});

describe("rule purity (CLAUDE.md constraint 1)", () => {
  const rulesDir = new URL("../../src/rules/", import.meta.url);
  const files = readdirSync(rulesDir).filter((name) => name.endsWith(".ts"));

  it.each(files)("%s performs no I/O and never touches the AST", (name) => {
    const source = readFileSync(new URL(name, rulesDir), "utf8");
    expect(source).not.toMatch(/from "(node:)?(fs|fs\/promises|http|https|net|child_process)"/);
    expect(source).not.toMatch(/from "ts-morph"/);
    expect(source).not.toMatch(/\bfetch\(/);
  });
});
