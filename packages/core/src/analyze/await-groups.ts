import { Node, SyntaxKind, type Symbol as MorphSymbol } from "ts-morph";
import { containingStatement, READ_OPERATIONS, type LocatedOperation } from "./orm-calls.js";
import { resolvedSymbol, unwrap } from "./syntax.js";
import type { IndependentAwaitGroup } from "./types.js";

/**
 * If `statement` is exactly `await <prisma read>;` or
 * `const x = await <prisma read>;`, returns that operation's index.
 */
function awaitedRead(statement: Node, indexByCall: Map<Node, number>, located: LocatedOperation[]): number | undefined {
  let expression: Node | undefined;
  if (Node.isExpressionStatement(statement)) {
    expression = statement.getExpression();
  } else if (Node.isVariableStatement(statement)) {
    const declarations = statement.getDeclarations();
    if (declarations.length !== 1) return undefined;
    expression = declarations[0]?.getInitializer();
  }
  if (!expression) return undefined;

  const awaited = unwrap(expression);
  if (!Node.isAwaitExpression(awaited)) return undefined;
  const index = indexByCall.get(unwrap(awaited.getExpression()));
  if (index === undefined) return undefined;

  const operation = located[index]?.operation;
  return operation && READ_OPERATIONS.has(operation.operation) && !operation.loopContext ? index : undefined;
}

/** Symbols bound by a variable statement, including destructured names. */
function declaredSymbols(statement: Node): MorphSymbol[] {
  if (!Node.isVariableStatement(statement)) return [];
  return statement.getDeclarations().flatMap((declaration) => {
    const name = declaration.getNameNode();
    const identifiers = Node.isIdentifier(name) ? [name] : name.getDescendantsOfKind(SyntaxKind.Identifier);
    return identifiers.flatMap((identifier) => {
      const symbol = identifier.getSymbol();
      return symbol ? [symbol] : [];
    });
  });
}

function referencesAny(statement: Node, symbols: Set<MorphSymbol>): boolean {
  return statement
    .getDescendantsOfKind(SyntaxKind.Identifier)
    .some((identifier) => {
      const symbol = resolvedSymbol(identifier);
      return symbol !== undefined && symbols.has(symbol);
    });
}

/**
 * Finds runs of adjacent statements that each await a Prisma read, where no
 * statement uses a binding produced by an earlier one in the run. Mutations
 * are excluded: their order can matter even without a visible data dependency.
 * Any intervening statement (a guard, a log line) ends the run.
 */
export function findIndependentAwaitGroups(located: LocatedOperation[]): IndependentAwaitGroup[] {
  const indexByCall = new Map<Node, number>(located.map((entry, index) => [entry.call, index]));
  const blocks = new Set<Node>();
  for (const entry of located) {
    const block = containingStatement(entry.call)?.getParent();
    if (block && entry.operation.isAwaited) blocks.add(block);
  }

  const groups: IndependentAwaitGroup[] = [];
  for (const block of blocks) {
    const statements = Node.isBlock(block) || Node.isSourceFile(block) || Node.isCaseClause(block) || Node.isDefaultClause(block)
      ? block.getStatements()
      : [];

    let chunk: number[] = [];
    let bound = new Set<MorphSymbol>();
    const flush = () => {
      const first = chunk[0] !== undefined ? located[chunk[0]]?.operation : undefined;
      if (chunk.length >= 2 && first) {
        groups.push({ file: first.file, enclosingFunction: first.enclosingFunction, operations: chunk });
      }
      chunk = [];
      bound = new Set();
    };

    for (const statement of statements) {
      const index = awaitedRead(statement, indexByCall, located);
      if (index === undefined) {
        flush();
        continue;
      }
      if (chunk.length > 0 && referencesAny(statement, bound)) flush();
      chunk.push(index);
      for (const symbol of declaredSymbols(statement)) bound.add(symbol);
    }
    flush();
  }

  return groups.sort((a, b) => (a.operations[0] ?? 0) - (b.operations[0] ?? 0));
}
