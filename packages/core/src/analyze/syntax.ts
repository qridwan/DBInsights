import { Node, type Symbol as MorphSymbol } from "ts-morph";

/** Strips parentheses, type assertions, `satisfies` and non-null assertions. */
export function unwrap(node: Node): Node {
  let current = node;
  for (;;) {
    if (
      Node.isParenthesizedExpression(current) ||
      Node.isAsExpression(current) ||
      Node.isSatisfiesExpression(current) ||
      Node.isNonNullExpression(current) ||
      Node.isTypeAssertion(current)
    ) {
      current = current.getExpression();
    } else {
      return current;
    }
  }
}

/** Resolves a node's symbol through import/export aliases to the original declaration's symbol. */
export function resolvedSymbol(node: Node): MorphSymbol | undefined {
  const symbol = node.getSymbol();
  if (!symbol) return undefined;
  return symbol.isAlias() ? (symbol.getAliasedSymbol() ?? symbol) : symbol;
}

export function declarationsOf(node: Node): Node[] {
  return resolvedSymbol(node)?.getDeclarations() ?? [];
}

export function lineOf(node: Node): number {
  return node.getStartLineNumber();
}

/** Name of the nearest named function-like ancestor, skipping anonymous callbacks. */
export function enclosingFunctionName(node: Node): string | null {
  for (let current = node.getParent(); current; current = current.getParent()) {
    if (Node.isFunctionDeclaration(current)) return current.getName() ?? "default";
    if (Node.isMethodDeclaration(current) || Node.isGetAccessorDeclaration(current) || Node.isSetAccessorDeclaration(current)) {
      const owner = current.getParent();
      const ownerName = Node.isClassDeclaration(owner) || Node.isClassExpression(owner) ? owner.getName() : undefined;
      return ownerName ? `${ownerName}.${current.getName()}` : current.getName();
    }
    if (Node.isConstructorDeclaration(current)) {
      const owner = current.getParent();
      return `${Node.isClassDeclaration(owner) ? (owner.getName() ?? "class") : "class"}.constructor`;
    }
    if (Node.isArrowFunction(current) || Node.isFunctionExpression(current)) {
      if (Node.isFunctionExpression(current) && current.getName()) return current.getName() ?? null;
      const parent = current.getParent();
      if (Node.isVariableDeclaration(parent) || Node.isPropertyAssignment(parent)) return parent.getName();
      if (Node.isPropertyDeclaration(parent)) {
        const owner = parent.getParent();
        const ownerName = Node.isClassDeclaration(owner) ? owner.getName() : undefined;
        return ownerName ? `${ownerName}.${parent.getName()}` : parent.getName();
      }
      if (Node.isExportAssignment(parent)) return "default";
      // Anonymous callback: attribute the call to the function around it.
    }
  }
  return null;
}
