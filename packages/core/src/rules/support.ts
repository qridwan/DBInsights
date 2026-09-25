import { createHash } from "node:crypto";
import type { AnalysisContext, ORMOperation } from "../analyze/types.js";
import type { Evidence, Finding } from "../models.js";

export type Rule = (context: AnalysisContext) => Finding[];

/**
 * Stable dedupe key per CLAUDE.md constraint 6: derived from the rule, file,
 * enclosing function and normalized call, never from line numbers.
 */
export function fingerprint(
  ruleId: string,
  file: string,
  enclosingFunction: string | null,
  normalizedCallExpression: string,
): string {
  return createHash("sha256")
    .update([ruleId, file, enclosingFunction ?? "<module>", normalizedCallExpression].join("\u0000"))
    .digest("hex")
    .slice(0, 32);
}

export function delegateName(model: string): string {
  return model.charAt(0).toLowerCase() + model.slice(1);
}

/** `prisma.user.findMany` style label for messages. */
export function callLabel(operation: ORMOperation): string {
  return `${delegateName(operation.model)}.${operation.operation}()`;
}

export function where(operation: ORMOperation): string {
  return operation.enclosingFunction ? `\`${operation.enclosingFunction}\`` : "module scope";
}

export function callEvidence(operation: ORMOperation, description: string, data?: Record<string, unknown>): Evidence {
  return {
    source: "STATIC_SOURCE",
    description,
    file: operation.file,
    line: operation.line,
    ...(data ? { data } : {}),
  };
}

export function codeBlock(language: string, code: string): string {
  return `\`\`\`${language}\n${code.trim()}\n\`\`\``;
}
