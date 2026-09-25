import { Node, SyntaxKind, type Symbol as MorphSymbol } from "ts-morph";
import type { LocatedOperation } from "./orm-calls.js";
import { resolvedSymbol, unwrap } from "./syntax.js";

/**
 * Array methods whose result still consists of (or is derived element-wise
 * from) the receiver's elements. Iterating the result iterates the source rows.
 */
const ELEMENT_PRESERVING_METHODS = new Set([
  "filter",
  "slice",
  "sort",
  "toSorted",
  "reverse",
  "toReversed",
  "concat",
  "flat",
  "map",
  "flatMap",
]);

const ITERATION_CALLBACK_METHODS = new Set([
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

const MAX_DEPTH = 6;

type Resolver = (node: Node) => LocatedOperation | undefined;

/** True when a `let`/`var` binding is assigned again anywhere in its file. */
function isReassigned(symbol: MorphSymbol, declaration: Node): boolean {
  return declaration
    .getSourceFile()
    .getDescendantsOfKind(SyntaxKind.BinaryExpression)
    .some((binary) => {
      const operator = binary.getOperatorToken().getKind();
      if (operator < SyntaxKind.FirstAssignment || operator > SyntaxKind.LastAssignment) return false;
      const left = unwrap(binary.getLeft());
      return Node.isIdentifier(left) && resolvedSymbol(left) === symbol;
    });
}

/**
 * The element parameter of an array-iteration callback, e.g. `row` in
 * `rows.map((row) => ...)`. Returns the iterated receiver.
 */
function iterationCallbackReceiver(parameter: Node): Node | undefined {
  if (!Node.isParameterDeclaration(parameter)) return undefined;
  const fn = parameter.getParent();
  if (!Node.isArrowFunction(fn) && !Node.isFunctionExpression(fn)) return undefined;
  const call = fn.getParent();
  if (!Node.isCallExpression(call) || !call.getArguments().includes(fn)) return undefined;
  const callee = call.getExpression();
  if (!Node.isPropertyAccessExpression(callee) || !ITERATION_CALLBACK_METHODS.has(callee.getName())) return undefined;
  const elementIndex = callee.getName() === "reduce" ? 1 : 0;
  return fn.getParameters()[elementIndex] === parameter ? callee.getExpression() : undefined;
}

function resolveDeclaration(declaration: Node, symbol: MorphSymbol, resolve: Resolver): LocatedOperation | undefined {
  if (Node.isVariableDeclaration(declaration)) {
    // Loop variable: `for (const row of rows)` — each row comes from `rows`.
    const list = declaration.getParent();
    const loop = list?.getParent();
    if (Node.isVariableDeclarationList(list) && Node.isForOfStatement(loop)) {
      return resolve(loop.getExpression());
    }
    if (!Node.isIdentifier(declaration.getNameNode())) return undefined;
    const statement = declaration.getVariableStatement();
    if (statement && statement.getDeclarationKind() !== "const" && isReassigned(symbol, declaration)) {
      return undefined;
    }
    const initializer = declaration.getInitializer();
    return initializer ? resolve(initializer) : undefined;
  }

  if (Node.isBindingElement(declaration)) {
    // const [a, b] = await Promise.all([prisma.x.findMany(), prisma.y.findMany()])
    const pattern = declaration.getParent();
    const holder = pattern?.getParent();
    if (!Node.isArrayBindingPattern(pattern) || !Node.isVariableDeclaration(holder)) return undefined;
    const index = pattern.getElements().indexOf(declaration);
    let initializer: Node | undefined = holder.getInitializer();
    if (!initializer) return undefined;
    initializer = unwrap(initializer);
    if (Node.isAwaitExpression(initializer)) initializer = unwrap(initializer.getExpression());
    if (!Node.isCallExpression(initializer) || unwrap(initializer.getExpression()).getText() !== "Promise.all") return undefined;
    const list = initializer.getArguments()[0];
    const elements = list ? unwrap(list) : undefined;
    if (!Node.isArrayLiteralExpression(elements)) return undefined;
    const element = elements.getElements()[index];
    return element ? resolve(element) : undefined;
  }

  if (Node.isParameterDeclaration(declaration)) {
    // Only callback parameters of array iteration have a known origin.
    const receiver = iterationCallbackReceiver(declaration);
    return receiver ? resolve(receiver) : undefined;
  }

  return undefined;
}

function createResolver(byCall: Map<Node, LocatedOperation>): Resolver {
  const resolve = (expression: Node, depth: number): LocatedOperation | undefined => {
    if (depth > MAX_DEPTH) return undefined;
    const next = (node: Node) => resolve(node, depth + 1);
    const node = unwrap(expression);

    if (Node.isAwaitExpression(node)) return next(node.getExpression());

    if (Node.isCallExpression(node)) {
      const located = byCall.get(node);
      if (located) return located;
      const callee = node.getExpression();
      if (Node.isPropertyAccessExpression(callee) && ELEMENT_PRESERVING_METHODS.has(callee.getName())) {
        return next(callee.getExpression());
      }
      return undefined;
    }

    if (Node.isIdentifier(node)) {
      const symbol = resolvedSymbol(node);
      const declarations = symbol?.getDeclarations() ?? [];
      if (!symbol || declarations.length !== 1) return undefined;
      return resolveDeclaration(declarations[0] as Node, symbol, next);
    }

    // `row.children` / `rows[0].children`: a list reached through an ORM row.
    if (Node.isPropertyAccessExpression(node) || Node.isElementAccessExpression(node)) {
      return next(node.getExpression());
    }

    return undefined;
  };
  return (node) => resolve(node, 0);
}

/**
 * For each Prisma call inside a loop, determines via symbol resolution
 * whether the loop iterates over the result of an earlier Prisma call, and
 * records that call's line.
 */
export function resolveLoopSources(located: LocatedOperation[]): void {
  const resolve = createResolver(new Map(located.map((entry) => [entry.call as Node, entry])));

  for (const entry of located) {
    const context = entry.operation.loopContext;
    if (!context || !entry.loop?.iterable) continue;
    const source = resolve(entry.loop.iterable);
    if (source && source !== entry && source.call.getSourceFile() === entry.call.getSourceFile()) {
      context.iteratesOverORMResult = true;
      context.sourceOperationLine = source.operation.line;
    }
  }
}
