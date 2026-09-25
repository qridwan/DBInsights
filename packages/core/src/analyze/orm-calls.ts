import { relative, sep } from "node:path";
import { Node, SyntaxKind, type CallExpression, type Project } from "ts-morph";
import type { SchemaModel } from "../schema/types.js";
import { resolveDelegate } from "./prisma-client.js";
import { declarationsOf, enclosingFunctionName, lineOf, unwrap } from "./syntax.js";
import type { LoopKind, ORMArgs, ORMOperation } from "./types.js";

export const MODEL_OPERATIONS = new Set([
  "findUnique",
  "findUniqueOrThrow",
  "findFirst",
  "findFirstOrThrow",
  "findMany",
  "create",
  "createMany",
  "createManyAndReturn",
  "update",
  "updateMany",
  "updateManyAndReturn",
  "upsert",
  "delete",
  "deleteMany",
  "count",
  "aggregate",
  "groupBy",
]);

export const READ_OPERATIONS = new Set([
  "findUnique",
  "findUniqueOrThrow",
  "findFirst",
  "findFirstOrThrow",
  "findMany",
  "count",
  "aggregate",
  "groupBy",
]);

const ITERATION_METHODS = new Set<LoopKind>([
  "map",
  "flatMap",
  "forEach",
  "filter",
  "reduce",
  "some",
  "every",
  "find",
  "findIndex",
]);

/** Syntax-level facts about a located call, used by later analysis passes. */
export interface LocatedOperation {
  operation: ORMOperation;
  call: CallExpression;
  loop: LocatedLoop | null;
}

export interface LocatedLoop {
  kind: LoopKind;
  node: Node;
  /** The collection being iterated, when the loop has one (for-of, for-in, array methods). */
  iterable: Node | null;
}

// ---------------------------------------------------------------------------
// Argument extraction
// ---------------------------------------------------------------------------

const MAX_RESOLVE_DEPTH = 3;

/**
 * Statically reads the property names of an object expression, following
 * spreads, conditionals and const references. Returns undefined when the shape
 * cannot be determined. Conditional branches are unioned: a key counts as
 * present if any branch can supply it.
 */
function readObject(expression: Node, depth = 0): Map<string, Node | undefined> | undefined {
  if (depth > MAX_RESOLVE_DEPTH) return undefined;
  const node = unwrap(expression);

  if (Node.isObjectLiteralExpression(node)) {
    const properties = new Map<string, Node | undefined>();
    for (const property of node.getProperties()) {
      if (Node.isPropertyAssignment(property)) {
        const nameNode = property.getNameNode();
        if (Node.isComputedPropertyName(nameNode)) return undefined;
        properties.set(property.getName().replace(/^["']|["']$/g, ""), property.getInitializer());
      } else if (Node.isShorthandPropertyAssignment(property)) {
        properties.set(property.getName(), property.getNameNode());
      } else if (Node.isSpreadAssignment(property)) {
        const spread = readObject(property.getExpression(), depth + 1);
        if (!spread) return undefined;
        for (const [key, value] of spread) properties.set(key, value);
      }
    }
    return properties;
  }
  if (Node.isConditionalExpression(node)) {
    const whenTrue = readObject(node.getWhenTrue(), depth + 1);
    const whenFalse = readObject(node.getWhenFalse(), depth + 1);
    if (!whenTrue || !whenFalse) return undefined;
    return new Map([...whenFalse, ...whenTrue]);
  }
  if (Node.isBinaryExpression(node) && node.getOperatorToken().getKind() === SyntaxKind.AmpersandAmpersandToken) {
    return readObject(node.getRight(), depth + 1);
  }
  if (node.getKind() === SyntaxKind.UndefinedKeyword || node.getKind() === SyntaxKind.NullKeyword || node.getText() === "undefined") {
    return new Map();
  }
  if (Node.isIdentifier(node)) {
    for (const declaration of declarationsOf(node)) {
      if (Node.isVariableDeclaration(declaration) && declaration.getVariableStatement()?.getDeclarationKind() === "const") {
        const initializer = declaration.getInitializer();
        if (initializer) return readObject(initializer, depth + 1);
      }
    }
  }
  return undefined;
}

const LOGICAL_KEYS = new Set(["AND", "OR", "NOT"]);

/** Collects `where` keys, descending into `AND` (object or array form). */
function readWhereFields(where: Node, depth = 0): string[] | undefined {
  const properties = readObject(where);
  if (!properties) return undefined;
  const fields = [...properties.keys()].filter((key) => !LOGICAL_KEYS.has(key));
  const and = properties.get("AND");
  if (and && depth < MAX_RESOLVE_DEPTH) {
    const unwrapped = unwrap(and);
    const branches = Node.isArrayLiteralExpression(unwrapped) ? unwrapped.getElements() : [and];
    for (const branch of branches) {
      const nested = readWhereFields(branch, depth + 1);
      if (!nested) return undefined;
      fields.push(...nested);
    }
  }
  return [...new Set(fields)];
}

function isFalseLiteral(node: Node | undefined): boolean {
  return node !== undefined && unwrap(node).getKind() === SyntaxKind.FalseKeyword;
}

interface ReadArgs {
  args: ORMArgs;
  argsResolved: boolean;
  whereResolved: boolean;
  whereEmpty: boolean;
}

function readArgs(call: CallExpression): ReadArgs {
  const empty: ORMArgs = {
    hasWhere: false,
    whereFields: [],
    hasTake: false,
    hasSkip: false,
    hasCursor: false,
    hasSelect: false,
    includeRelations: [],
  };
  const first = call.getArguments()[0];
  if (!first) return { args: empty, argsResolved: true, whereResolved: true, whereEmpty: false };

  const properties = readObject(first);
  if (!properties) return { args: empty, argsResolved: false, whereResolved: false, whereEmpty: false };

  const where = properties.get("where");
  const whereFields = properties.has("where") && where ? readWhereFields(where) : [];
  const whereEmpty = where !== undefined && readObject(where)?.size === 0;

  const relations = new Set<string>();
  const include = properties.get("include");
  if (include) {
    for (const [key, value] of readObject(include) ?? []) {
      if (key !== "_count" && !isFalseLiteral(value)) relations.add(key);
    }
  }
  const select = properties.get("select");
  if (select) {
    for (const [key, value] of readObject(select) ?? []) {
      if (key !== "_count" && value && Node.isObjectLiteralExpression(unwrap(value))) relations.add(key);
    }
  }

  return {
    args: {
      hasWhere: properties.has("where"),
      whereFields: whereFields ?? [],
      hasTake: properties.has("take"),
      hasSkip: properties.has("skip"),
      hasCursor: properties.has("cursor"),
      hasSelect: properties.has("select"),
      includeRelations: [...relations],
    },
    argsResolved: true,
    whereResolved: whereFields !== undefined,
    whereEmpty,
  };
}

// ---------------------------------------------------------------------------
// Loop context
// ---------------------------------------------------------------------------

function isArrayLike(node: Node): boolean {
  const type = node.getType();
  // Unresolved types (missing declarations) are accepted: the method name is
  // the only evidence available.
  if (type.isAny() || type.isUnknown() || type.isTypeParameter()) return true;
  const candidates = type.isUnion() ? type.getUnionTypes() : [type];
  return candidates.some((candidate) => {
    if (candidate.isArray() || candidate.isTuple()) return true;
    const name = candidate.getSymbol()?.getName() ?? "";
    return name === "ReadonlyArray" || name === "Set" || name === "Map";
  });
}

function contains(container: Node | undefined, node: Node): boolean {
  return container !== undefined && node.getPos() >= container.getPos() && node.getEnd() <= container.getEnd();
}

/**
 * Finds the innermost loop that re-executes `call` on each iteration. Stops at
 * a function boundary unless that function is an array-iteration callback.
 */
export function findLoop(call: Node): LocatedLoop | null {
  let child: Node = call;
  for (let current = call.getParent(); current; child = current, current = current.getParent()) {
    if (Node.isForOfStatement(current) && contains(current.getStatement(), child)) {
      return { kind: "for-of", node: current, iterable: current.getExpression() };
    }
    if (Node.isForInStatement(current) && contains(current.getStatement(), child)) {
      return { kind: "for-in", node: current, iterable: current.getExpression() };
    }
    if (Node.isForStatement(current) && !contains(current.getInitializer(), child)) {
      return { kind: "for", node: current, iterable: null };
    }
    if (Node.isWhileStatement(current)) return { kind: "while", node: current, iterable: null };
    if (Node.isDoStatement(current)) return { kind: "do-while", node: current, iterable: null };

    if (Node.isArrowFunction(current) || Node.isFunctionExpression(current)) {
      const parent = current.getParent();
      if (Node.isCallExpression(parent) && parent.getArguments().includes(current)) {
        const callee = parent.getExpression();
        if (Node.isPropertyAccessExpression(callee) && ITERATION_METHODS.has(callee.getName() as LoopKind)) {
          const receiver = callee.getExpression();
          if (isArrayLike(receiver)) {
            return { kind: callee.getName() as LoopKind, node: parent, iterable: receiver };
          }
        }
      }
      return null;
    }
    if (Node.isFunctionDeclaration(current) || Node.isMethodDeclaration(current) || Node.isConstructorDeclaration(current)) {
      return null;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Location
// ---------------------------------------------------------------------------

function isAwaited(call: Node): boolean {
  let parent = call.getParent();
  while (parent && Node.isParenthesizedExpression(parent)) parent = parent.getParent();
  return parent !== undefined && Node.isAwaitExpression(parent);
}

/** The statement containing `node` whose parent is a statement list. */
export function containingStatement(node: Node): Node | undefined {
  return node.getFirstAncestor((ancestor) => {
    const parent = ancestor.getParent();
    return parent !== undefined && (Node.isBlock(parent) || Node.isSourceFile(parent) || Node.isCaseClause(parent) || Node.isDefaultClause(parent));
  });
}

function upperFirst(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function lowerFirst(name: string): string {
  return name.charAt(0).toLowerCase() + name.slice(1);
}

export interface LocateOptions {
  /** Directory that `ORMOperation.file` paths are made relative to. */
  rootDir: string;
  /**
   * Declared schema. When given, only delegates matching a schema model are
   * accepted and delegate names map to exact model names.
   */
  schema?: SchemaModel;
}

/** Finds every Prisma model operation in the project, in file and source order. */
export function locateOrmCalls(project: Project, options: LocateOptions): LocatedOperation[] {
  const modelsByDelegate = new Map(options.schema?.models.map((model) => [lowerFirst(model.name), model.name]));
  const located: LocatedOperation[] = [];

  const sourceFiles = [...project.getSourceFiles()].sort((a, b) => a.getFilePath().localeCompare(b.getFilePath()));
  for (const sourceFile of sourceFiles) {
    const file = relative(options.rootDir, sourceFile.getFilePath()).split(sep).join("/");
    if (file.startsWith("..")) continue;

    for (const call of sourceFile.getDescendantsOfKind(SyntaxKind.CallExpression)) {
      const callee = call.getExpression();
      if (!Node.isPropertyAccessExpression(callee) || !MODEL_OPERATIONS.has(callee.getName())) continue;

      const delegate = resolveDelegate(callee.getExpression());
      if (!delegate) continue;
      const model = options.schema ? modelsByDelegate.get(delegate) : upperFirst(delegate);
      if (!model) continue;

      const loop = findLoop(call);
      const { args, argsResolved, whereResolved, whereEmpty } = readArgs(call);
      located.push({
        call,
        loop,
        operation: {
          file,
          line: lineOf(call),
          model,
          operation: callee.getName(),
          args,
          argsResolved,
          whereResolved,
          whereEmpty,
          loopContext: loop
            ? {
                inLoop: true,
                loopKind: loop.kind,
                loopLine: lineOf(loop.node),
                iteratesOverORMResult: false,
                sourceOperationLine: null,
              }
            : null,
          enclosingFunction: enclosingFunctionName(call),
          isAwaited: isAwaited(call),
          siblingAwaits: 0,
          normalizedCall: "",
        },
      });
    }
  }

  assignSiblingAwaits(located);
  assignNormalizedCalls(located);
  return located;
}

function assignSiblingAwaits(located: LocatedOperation[]): void {
  const byBlock = new Map<Node, LocatedOperation[]>();
  for (const entry of located) {
    if (!entry.operation.isAwaited) continue;
    const block = containingStatement(entry.call)?.getParent();
    if (!block) continue;
    const group = byBlock.get(block) ?? [];
    group.push(entry);
    byBlock.set(block, group);
  }
  for (const group of byBlock.values()) {
    for (const entry of group) entry.operation.siblingAwaits = group.length - 1;
  }
}

function assignNormalizedCalls(located: LocatedOperation[]): void {
  const seen = new Map<string, number>();
  for (const { operation } of located) {
    const base = `${lowerFirst(operation.model)}.${operation.operation}`;
    const key = `${operation.file}|${operation.enclosingFunction ?? ""}|${base}`;
    const ordinal = seen.get(key) ?? 0;
    seen.set(key, ordinal + 1);
    operation.normalizedCall = `${base}#${ordinal}`;
  }
}
