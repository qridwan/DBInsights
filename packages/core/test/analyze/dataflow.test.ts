import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { resolveLoopSources } from "../../src/analyze/dataflow.js";
import { locateFixture, sourceDir } from "../helpers.js";

const located = locateFixture("dataflow");
resolveLoopSources(located);
const operations = located.map((entry) => entry.operation);
const inFile = (file: string) => operations.filter((op) => op.file === file);

/** Line numbers carrying a `// source` marker in a fixture file. */
function sourceMarkers(file: string): number[] {
  return readFileSync(join(sourceDir("dataflow"), file), "utf8")
    .split("\n")
    .flatMap((text, index) => (text.includes("// source") ? [index + 1] : []));
}

describe("data-flow resolution: negative cases", () => {
  const negatives = inFile("negative.ts");

  it("covers every negative fixture function", () => {
    expect(new Set(negatives.map((op) => op.enclosingFunction))).toEqual(
      new Set([
        "literalArrayInline",
        "literalArrayConst",
        "literalArrayMap",
        "parameterOfUnknownOrigin",
        "parameterMap",
        "fetchResults",
        "fetchResultsForEach",
        "objectKeys",
        "objectKeysOfOrmResult",
        "reassignedBeforeLoop",
        "otherFunctionResult",
        "stringSplit",
        "indexedForLoop",
      ]),
    );
  });

  const inLoop = negatives.filter((op) => op.loopContext !== null);

  it.each(inLoop.map((op) => [op.enclosingFunction, op] as const))(
    "%s: in a loop, but not over an ORM result",
    (_name, op) => {
      expect(op.loopContext).toMatchObject({ inLoop: true, iteratesOverORMResult: false, sourceOperationLine: null });
    },
  );

  it("still recognises the loop in each case (only the ORM-result link is absent)", () => {
    const loopFunctions = new Set(inLoop.map((op) => op.enclosingFunction));
    for (const op of negatives) {
      if (op.operation === "findFirst" || (op.enclosingFunction === "reassignedBeforeLoop" && op.operation === "findMany")) continue;
      expect(loopFunctions.has(op.enclosingFunction)).toBe(true);
    }
  });

  it("does not treat stringSplit.map or Object.keys as a loop over ORM data", () => {
    expect(inLoop.find((op) => op.enclosingFunction === "stringSplit")?.loopContext?.loopKind).toBe("map");
  });
});

describe("data-flow resolution: calls that are not in loops", () => {
  it("ignores an ORM call used as the iterable, custom find methods and non-iteration callbacks", () => {
    expect(inFile("not-a-loop.ts").map((op) => [op.enclosingFunction, op.loopContext])).toEqual([
      ["ormCallAsIterable", null],
      ["customFindMethod", null],
      ["callbackOfNonIterationMethod", null],
    ]);
  });
});

describe("data-flow resolution: positive cases", () => {
  const markers = sourceMarkers("positive.ts");
  const inLoop = inFile("positive.ts").filter((op) => op.loopContext !== null);

  it("finds one looped call per positive fixture function", () => {
    expect(inLoop.map((op) => op.enclosingFunction)).toEqual([
      "forOfAwaitedVariable",
      "chainedMap",
      "chainedForEach",
      "mapOverVariable",
      "intermediateAssignment",
      "intermediateFilter",
      "awaitedLater",
      "destructuredPromiseAll",
      "nestedRelationList",
    ]);
  });

  it.each(inLoop.map((op) => [op.enclosingFunction, op] as const))(
    "%s: resolves to the originating Prisma call",
    (_name, op) => {
      const expected = Math.max(...markers.filter((line) => line <= op.line));
      expect(op.loopContext).toMatchObject({ iteratesOverORMResult: true, sourceOperationLine: expected });
    },
  );
});
