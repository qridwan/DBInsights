import { describe, expect, it } from "vitest";
import { locateFixture, summarize } from "../helpers.js";

const located = locateFixture("orm-calls");
const operations = located.map((entry) => entry.operation);
const find = (file: string, fn: string, operation: string) => {
  const found = operations.find((op) => op.file === file && op.enclosingFunction === fn && op.operation === operation);
  if (!found) throw new Error(`no ${operation} in ${file}:${fn}`);
  return found;
};

describe("ORM call location", () => {
  it("finds direct calls on a locally constructed client", () => {
    expect(summarize(operations, "direct.ts")).toEqual([
      "listTeamUsers:User.findMany",
      "countOpenTasks:Task.count",
      "countOpenTasks:Task.count",
      "loadProject:Project.findUnique",
      "recentInvoices:Invoice.findMany",
      "forwarded:User.findMany",
    ]);
  });

  it("finds calls through a destructured client and an aliased delegate", () => {
    expect(summarize(operations, "destructured.ts")).toEqual([
      "firstActive:User.findFirst",
      "archivedProjects:Project.findMany",
      "purgeTasks:Task.deleteMany",
    ]);
  });

  it("finds calls in arrow functions, class methods, class fields and via constructor-injected clients", () => {
    expect(summarize(operations, "arrow-and-class.ts")).toEqual([
      "listUsers:User.findMany",
      "TaskService.openTasks:Task.findMany",
      "TaskService.countInvoices:Invoice.count",
    ]);
  });

  it("finds calls on a client imported from a shared module, including default and renamed imports and transaction clients", () => {
    expect(summarize(operations, "shared-import.ts")).toEqual([
      "renameUser:User.findUniqueOrThrow",
      "renameUser:User.update",
      "teamNames:Team.findMany",
    ]);
  });

  it("ignores lookalike calls, raw queries and delegates missing from the schema", () => {
    expect(summarize(operations, "not-prisma.ts")).toEqual([]);
  });
});

describe("argument extraction", () => {
  it("reads where fields, pagination through conditional spreads, and nested select relations", () => {
    expect(find("direct.ts", "listTeamUsers", "findMany")).toMatchObject({
      argsResolved: true,
      whereResolved: true,
      args: {
        hasWhere: true,
        whereFields: ["teamId", "active"],
        hasTake: true,
        hasSkip: true,
        hasCursor: true,
        hasSelect: true,
        includeRelations: ["team"],
      },
    });
  });

  it("reports no arguments as resolved and empty", () => {
    const count = operations.filter((op) => op.enclosingFunction === "countOpenTasks")[1];
    expect(count).toMatchObject({ argsResolved: true, args: { hasWhere: false, whereFields: [] } });
  });

  it("reads include keys but skips relations set to false", () => {
    expect(find("direct.ts", "loadProject", "findUnique").args.includeRelations).toEqual(["tasks"]);
  });

  it("follows const references and AND branches in where", () => {
    expect(find("direct.ts", "recentInvoices", "findMany").args.whereFields).toEqual([
      "createdAt",
      "amountCents",
      "teamId",
    ]);
  });

  it("marks arguments passed through from elsewhere as unresolved", () => {
    expect(find("direct.ts", "forwarded", "findMany")).toMatchObject({ argsResolved: false });
  });
});

describe("call context", () => {
  it("detects awaited calls and counts awaited siblings in the same block", () => {
    const counts = operations.filter((op) => op.enclosingFunction === "countOpenTasks");
    expect(counts.map((op) => [op.isAwaited, op.siblingAwaits])).toEqual([
      [true, 1],
      [true, 1],
    ]);
    expect(find("direct.ts", "listTeamUsers", "findMany").isAwaited).toBe(false);
  });

  it("gives calls outside loops no loop context", () => {
    expect(operations.every((op) => op.loopContext === null)).toBe(true);
  });

  it("assigns stable ordinals to repeated calls in one function", () => {
    const counts = operations.filter((op) => op.enclosingFunction === "countOpenTasks");
    expect(counts.map((op) => op.normalizedCall)).toEqual(["task.count#0", "task.count#1"]);
  });

  it("uses repo-relative paths", () => {
    expect(new Set(operations.map((op) => op.file))).toEqual(
      new Set(["arrow-and-class.ts", "destructured.ts", "direct.ts", "shared-import.ts"]),
    );
  });
});
