import type { SchemaModel } from "../schema/types.js";

export type LoopKind =
  | "for-of"
  | "for-in"
  | "for"
  | "while"
  | "do-while"
  | "map"
  | "flatMap"
  | "forEach"
  | "filter"
  | "reduce"
  | "some"
  | "every"
  | "find"
  | "findIndex";

export interface LoopContext {
  inLoop: true;
  loopKind: LoopKind;
  /** Line of the loop statement or iteration-method call. */
  loopLine: number;
  /** True when the loop's iterable resolves to the result of an earlier Prisma call. */
  iteratesOverORMResult: boolean;
  /** Line of that originating Prisma call, when resolved. */
  sourceOperationLine: number | null;
}

export interface ORMArgs {
  hasWhere: boolean;
  /** Top-level keys of `where` (including inside `AND`). `OR`/`NOT` branches are not included. */
  whereFields: string[];
  hasTake: boolean;
  hasSkip: boolean;
  hasCursor: boolean;
  hasSelect: boolean;
  /** Relations loaded via `include`, or via a nested object under `select`. */
  includeRelations: string[];
}

export interface ORMOperation {
  /** Path relative to the analyzed source directory, `/`-separated. */
  file: string;
  line: number;
  /** Schema model name, e.g. `User` for `prisma.user`. */
  model: string;
  /** Delegate method, e.g. `findMany`. */
  operation: string;
  args: ORMArgs;
  /**
   * False when the call's argument is not statically readable (e.g. passed
   * through from elsewhere). Rules that depend on argument absence must not
   * fire when this is false.
   */
  argsResolved: boolean;
  /** False when `where` is present but its keys could not be read. */
  whereResolved: boolean;
  /** True when `where` is present and statically an empty object (`{}` or `undefined`). */
  whereEmpty: boolean;
  loopContext: LoopContext | null;
  enclosingFunction: string | null;
  isAwaited: boolean;
  /** Other awaited Prisma calls whose statements share this call's block. */
  siblingAwaits: number;
  /**
   * `delegate.operation#ordinal`: stable identity of this call within its
   * enclosing function, independent of line numbers.
   */
  normalizedCall: string;
}

/**
 * Consecutive awaited Prisma reads in one block where no statement uses a
 * value produced by an earlier one in the group.
 */
export interface IndependentAwaitGroup {
  file: string;
  enclosingFunction: string | null;
  /** Indexes into `AnalysisContext.operations`, in source order. */
  operations: number[];
}

export interface AnalysisContext {
  /** Declared schema (schema.prisma). Never merged with the actual database schema. */
  schema: SchemaModel;
  /** How findings should refer to the schema file, e.g. `prisma/schema.prisma`. */
  schemaFile: string;
  operations: ORMOperation[];
  independentAwaitGroups: IndependentAwaitGroup[];
}
