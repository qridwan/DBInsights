import { Node, SyntaxKind } from "ts-morph";
import { declarationsOf, unwrap } from "./syntax.js";

// Prisma's own type names. These identify the library, not any application.
// Anchored: the type itself must be the client, not an object that holds one
// (`{ prisma: PrismaClient }` must not match).
const CLIENT_TYPE_TEXT_PATTERN =
  /^(?:import\([^)]*\)\.)?(?:\w+\.)*(?:PrismaClient|TransactionClient|DefaultPrismaClient)\b|^Omit<(?:import\([^)]*\)\.)?(?:\w+\.)*PrismaClient\b/;
const DELEGATE_TYPE_PATTERN = /^(?:import\([^)]*\)\.)?(?:\w+\.)*(\w+)Delegate\b/;
const MAX_DEPTH = 8;

function typeTextMatchesClient(node: Node): boolean {
  const type = node.getType();
  if (type.isAny() || type.isUnknown()) return false;
  return CLIENT_TYPE_TEXT_PATTERN.test(type.getText(node));
}

function typeNodeMatchesClient(node: Node): boolean {
  if (!Node.isVariableDeclaration(node) && !Node.isParameterDeclaration(node) && !Node.isPropertyDeclaration(node) && !Node.isPropertySignature(node)) {
    return false;
  }
  const typeNode = node.getTypeNode();
  return typeNode !== undefined && CLIENT_TYPE_TEXT_PATTERN.test(typeNode.getText());
}

/** True for the parameter of a callback passed to `client.$transaction(...)`. */
function isTransactionCallbackParameter(node: Node, depth: number): boolean {
  if (!Node.isParameterDeclaration(node)) return false;
  const fn = node.getParent();
  const call = fn?.getParent();
  if (!Node.isCallExpression(call)) return false;
  const callee = call.getExpression();
  return (
    Node.isPropertyAccessExpression(callee) &&
    callee.getName() === "$transaction" &&
    isPrismaClientExpression(callee.getExpression(), depth + 1)
  );
}

function declarationIsClient(declaration: Node, depth: number): boolean {
  if (typeNodeMatchesClient(declaration)) return true;
  if (isTransactionCallbackParameter(declaration, depth)) return true;
  if (Node.isVariableDeclaration(declaration) || Node.isPropertyDeclaration(declaration)) {
    const initializer = declaration.getInitializer();
    return initializer !== undefined && isPrismaClientExpression(initializer, depth + 1);
  }
  if (Node.isExportAssignment(declaration)) {
    return isPrismaClientExpression(declaration.getExpression(), depth + 1);
  }
  if (Node.isFunctionDeclaration(declaration) || Node.isArrowFunction(declaration) || Node.isFunctionExpression(declaration)) {
    // A factory: `function createClient() { return new PrismaClient() }`.
    const body = declaration.getBody();
    if (body && !Node.isBlock(body)) return isPrismaClientExpression(body, depth + 1);
    return declaration
      .getDescendantsOfKind(SyntaxKind.ReturnStatement)
      .filter((statement) => statement.getFirstAncestor((a) => Node.isFunctionLikeDeclaration(a)) === declaration)
      .some((statement) => {
        const expression = statement.getExpression();
        return expression !== undefined && isPrismaClientExpression(expression, depth + 1);
      });
  }
  return false;
}

/**
 * Whether an expression evaluates to a Prisma client (or transaction client).
 * Decided by following symbols to their declarations and by the checker's
 * type when the generated client is available; never by variable name.
 */
export function isPrismaClientExpression(expression: Node, depth = 0): boolean {
  if (depth > MAX_DEPTH) return false;
  const node = unwrap(expression);

  if (typeTextMatchesClient(node)) return true;

  if (Node.isNewExpression(node)) {
    return /(^|\.)PrismaClient$/.test(node.getExpression().getText());
  }
  if (Node.isBinaryExpression(node)) {
    const operator = node.getOperatorToken().getText();
    if (operator === "??" || operator === "||") {
      return isPrismaClientExpression(node.getLeft(), depth + 1) || isPrismaClientExpression(node.getRight(), depth + 1);
    }
    return false;
  }
  if (Node.isConditionalExpression(node)) {
    return isPrismaClientExpression(node.getWhenTrue(), depth + 1) || isPrismaClientExpression(node.getWhenFalse(), depth + 1);
  }
  if (Node.isCallExpression(node)) {
    const callee = node.getExpression();
    if (Node.isPropertyAccessExpression(callee) && callee.getName() === "$extends") {
      return isPrismaClientExpression(callee.getExpression(), depth + 1);
    }
    return declarationsOf(callee).some((declaration) => declarationIsClient(declaration, depth + 1));
  }
  if (Node.isIdentifier(node) || Node.isPropertyAccessExpression(node)) {
    return declarationsOf(node).some((declaration) => declarationIsClient(declaration, depth + 1));
  }
  return false;
}

function lowerFirst(name: string): string {
  return name.charAt(0).toLowerCase() + name.slice(1);
}

/**
 * Resolves the expression a model operation is called on (the `x.user` in
 * `x.user.findMany()`, or `users` in `const { user: users } = x; users.findMany()`)
 * to the delegate name, if it is a Prisma model delegate.
 */
export function resolveDelegate(expression: Node, depth = 0): string | undefined {
  if (depth > MAX_DEPTH) return undefined;
  const node = unwrap(expression);

  if (Node.isPropertyAccessExpression(node)) {
    return isPrismaClientExpression(node.getExpression(), depth + 1) ? node.getName() : undefined;
  }

  if (Node.isIdentifier(node)) {
    for (const declaration of declarationsOf(node)) {
      // const { user } = client;  /  const { user: users } = client;
      if (Node.isBindingElement(declaration)) {
        const pattern = declaration.getParent();
        const holder = pattern?.getParent();
        if (Node.isObjectBindingPattern(pattern) && Node.isVariableDeclaration(holder)) {
          const initializer = holder.getInitializer();
          if (initializer && isPrismaClientExpression(initializer, depth + 1)) {
            return declaration.getPropertyNameNode()?.getText() ?? declaration.getName();
          }
        }
      }
      // const users = client.user;
      if (Node.isVariableDeclaration(declaration)) {
        const initializer = declaration.getInitializer();
        if (initializer) {
          const delegate = resolveDelegate(initializer, depth + 1);
          if (delegate) return delegate;
        }
      }
      // function list(users: Prisma.UserDelegate)
      if (Node.isParameterDeclaration(declaration)) {
        const match = DELEGATE_TYPE_PATTERN.exec(declaration.getTypeNode()?.getText() ?? "");
        if (match?.[1]) return lowerFirst(match[1]);
      }
    }
  }

  const type = node.getType();
  if (!type.isAny() && !type.isUnknown()) {
    const match = DELEGATE_TYPE_PATTERN.exec(type.getText(node));
    if (match?.[1]) return lowerFirst(match[1]);
  }
  return undefined;
}
