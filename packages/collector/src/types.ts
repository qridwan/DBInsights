/** One SQL statement executed on behalf of a Prisma operation. */
export interface StatementEvent {
  /** SQL exactly as sent to the driver, with $n placeholders. Parameter values are never captured. */
  sql: string;
  paramCount: number;
  kind: "query" | "execute";
  durationMs: number;
  /** Rows returned (query) or affected (execute); null if the statement failed. */
  rows: number | null;
}

/** One Prisma operation, e.g. `product.findMany`, with the SQL it produced. */
export interface OperationEvent {
  schemaVersion: 1;
  app: string;
  operationId: string;
  requestId: string | null;
  route: string | null;
  /** Null for raw queries ($queryRaw etc.). */
  model: string | null;
  operation: string;
  /** ISO timestamp when the operation started. */
  startedAt: string;
  durationMs: number;
  /** Array length, 1 for a single record or a count, 0 for null; null when unknown or failed. */
  rowsReturned: number | null;
  error: boolean;
  statements: StatementEvent[];
}

export interface RequestContext {
  requestId: string;
  route: string | null;
}

export interface CollectorStats {
  captured: number;
  sent: number;
  dropped: number;
  failedBatches: number;
  buffered: number;
}
