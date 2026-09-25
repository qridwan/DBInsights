import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";
import type { CollectorStats, OperationEvent, RequestContext, StatementEvent } from "./types";

export interface CollectorOptions {
  /** Application name recorded on every event. */
  app: string;
  /** Collector endpoint, e.g. http://collector:8700/v1/operations. Empty or undefined disables collection. */
  endpoint?: string | undefined;
  /** Returns the current request's id and route, if any. */
  requestContext?: () => RequestContext | undefined;
  /** Delivers a batch. Defaults to POSTing JSON to `endpoint`. */
  send?: (events: OperationEvent[]) => Promise<void>;
  flushIntervalMs?: number;
  maxBatch?: number;
  /** Events held in memory before new ones are dropped. */
  maxBuffer?: number;
}

/** The minimal driver-adapter surface the collector instruments. */
interface Queryable {
  queryRaw(query: { sql: string; args: unknown[] }): Promise<{ rows: unknown[] }>;
  executeRaw(query: { sql: string; args: unknown[] }): Promise<number>;
}

interface Operation {
  model?: string | undefined;
  operation: string;
  args: unknown;
  query: (args: unknown) => PromiseLike<unknown>;
}

export function countRows(result: unknown): number | null {
  if (Array.isArray(result)) return result.length;
  if (result === null || result === undefined) return 0;
  if (typeof result === "number") return 1;
  if (typeof result === "object") {
    const keys = Object.keys(result);
    if (keys.length === 1 && keys[0] === "count" && typeof (result as { count: unknown }).count === "number") {
      return (result as { count: number }).count;
    }
    return 1;
  }
  return null;
}

export class Collector {
  readonly enabled: boolean;
  private readonly current = new AsyncLocalStorage<OperationEvent>();
  private buffer: OperationEvent[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;
  private readonly counters = { captured: 0, sent: 0, dropped: 0, failedBatches: 0 };
  private readonly send: (events: OperationEvent[]) => Promise<void>;
  private readonly flushIntervalMs: number;
  private readonly maxBatch: number;
  private readonly maxBuffer: number;

  constructor(private readonly options: CollectorOptions) {
    const endpoint = options.endpoint?.trim();
    this.enabled = Boolean(endpoint) || options.send !== undefined;
    this.flushIntervalMs = options.flushIntervalMs ?? 250;
    this.maxBatch = options.maxBatch ?? 200;
    this.maxBuffer = options.maxBuffer ?? 10_000;
    this.send =
      options.send ??
      (async (events) => {
        const response = await fetch(endpoint as string, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(events),
          signal: AbortSignal.timeout(5_000),
        });
        if (!response.ok) throw new Error(`collector responded ${response.status}`);
      });
  }

  /**
   * Runs one Prisma operation, recording it and the SQL it executes. The
   * query result is returned untouched and its errors rethrown unchanged.
   */
  async runOperation({ model, operation, args, query }: Operation): Promise<unknown> {
    const context = this.safeContext();
    const event: OperationEvent = {
      schemaVersion: 1,
      app: this.options.app,
      operationId: randomUUID(),
      requestId: context?.requestId ?? null,
      route: context?.route ?? null,
      model: model ?? null,
      operation,
      startedAt: new Date().toISOString(),
      durationMs: 0,
      rowsReturned: null,
      error: false,
      statements: [],
    };
    const start = performance.now();
    try {
      // Prisma's promises are lazy: they only execute when awaited. Await
      // inside run() so the SQL they issue sees this operation as current.
      const result = await this.current.run(event, async () => await query(args));
      event.rowsReturned = countRows(result);
      return result;
    } catch (error) {
      event.error = true;
      throw error;
    } finally {
      event.durationMs = performance.now() - start;
      this.emit(event);
    }
  }

  /** Wraps a driver adapter so every statement is attributed to the running operation. */
  instrumentQueryable<T extends Queryable>(target: T): T {
    const record = (statement: StatementEvent) => this.current.getStore()?.statements.push(statement);
    const timed = async <R>(kind: StatementEvent["kind"], query: { sql: string; args: unknown[] }, run: () => Promise<R>, rows: (r: R) => number) => {
      const start = performance.now();
      try {
        const result = await run();
        record({ sql: query.sql, paramCount: query.args.length, kind, durationMs: performance.now() - start, rows: rows(result) });
        return result;
      } catch (error) {
        record({ sql: query.sql, paramCount: query.args.length, kind, durationMs: performance.now() - start, rows: null });
        throw error;
      }
    };
    return new Proxy(target, {
      get: (object, property, receiver) => {
        const value = Reflect.get(object, property, receiver);
        if (property === "queryRaw") {
          return (query: { sql: string; args: unknown[] }) =>
            timed("query", query, () => object.queryRaw(query), (result) => result.rows.length);
        }
        if (property === "executeRaw") {
          return (query: { sql: string; args: unknown[] }) =>
            timed("execute", query, () => object.executeRaw(query), (affected) => affected);
        }
        if (property === "startTransaction" && typeof value === "function") {
          return async (...params: unknown[]) =>
            this.instrumentQueryable(await (value as (...p: unknown[]) => Promise<Queryable>).apply(object, params));
        }
        return typeof value === "function" ? value.bind(object) : value;
      },
    });
  }

  /** Delivers everything buffered. Never throws. */
  async flush(): Promise<void> {
    this.clearTimer();
    while (this.buffer.length > 0) {
      const batch = this.buffer.splice(0, this.maxBatch);
      try {
        await this.send(batch);
        this.counters.sent += batch.length;
      } catch {
        this.counters.failedBatches += 1;
        this.counters.dropped += batch.length;
      }
    }
  }

  stats(): CollectorStats {
    return { ...this.counters, buffered: this.buffer.length };
  }

  private safeContext(): RequestContext | undefined {
    try {
      return this.options.requestContext?.();
    } catch {
      return undefined;
    }
  }

  // Never awaits: delivery happens on a timer, outside the request path.
  private emit(event: OperationEvent): void {
    this.counters.captured += 1;
    if (this.buffer.length >= this.maxBuffer) {
      this.counters.dropped += 1;
      return;
    }
    this.buffer.push(event);
    if (this.buffer.length >= this.maxBatch) {
      this.clearTimer();
      setImmediate(() => void this.flush());
    } else if (!this.timer) {
      this.timer = setTimeout(() => void this.flush(), this.flushIntervalMs);
      this.timer.unref?.();
    }
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
  }
}
