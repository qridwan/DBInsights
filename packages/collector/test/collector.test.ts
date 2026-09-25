import { describe, expect, it, vi } from "vitest";
import { Collector, countRows, createCollector, type OperationEvent } from "../src/index.js";

function fakeAdapter(rows: unknown[][] = [[1], [2]]) {
  return {
    queryRaw: vi.fn(async (_q: { sql: string; args: unknown[] }) => ({ columnNames: ["id"], columnTypes: [], rows })),
    executeRaw: vi.fn(async (_q: { sql: string; args: unknown[] }) => 3),
    startTransaction: vi.fn(async () => fakeAdapter(rows)),
    provider: "postgres",
  };
}

function collecting(options: Partial<ConstructorParameters<typeof Collector>[0]> = {}) {
  const batches: OperationEvent[][] = [];
  const collector = new Collector({
    app: "test",
    send: async (events) => void batches.push(events),
    flushIntervalMs: 10,
    ...options,
  });
  return { collector, batches, events: () => batches.flat() };
}

describe("runOperation", () => {
  it("records the operation and every SQL statement it executes", async () => {
    const { collector, events } = collecting({ requestContext: () => ({ requestId: "r1", route: "/api/x" }) });
    const adapter = collector.instrumentQueryable(fakeAdapter());

    const result = await collector.runOperation({
      model: "User",
      operation: "findMany",
      args: { take: 2 },
      query: async () => {
        await adapter.queryRaw({ sql: 'SELECT "id" FROM "User" WHERE "id" IN ($1,$2)', args: [1, 2] });
        await adapter.executeRaw({ sql: 'UPDATE "User" SET "x" = $1', args: [0] });
        return [{ id: 1 }, { id: 2 }];
      },
    });
    await collector.flush();

    expect(result).toEqual([{ id: 1 }, { id: 2 }]);
    const [event] = events();
    expect(event).toMatchObject({
      schemaVersion: 1,
      app: "test",
      requestId: "r1",
      route: "/api/x",
      model: "User",
      operation: "findMany",
      rowsReturned: 2,
      error: false,
    });
    expect(event?.statements.map((s) => [s.kind, s.sql, s.paramCount, s.rows])).toEqual([
      ["query", 'SELECT "id" FROM "User" WHERE "id" IN ($1,$2)', 2, 2],
      ["execute", 'UPDATE "User" SET "x" = $1', 1, 3],
    ]);
    expect(event?.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("attributes SQL from lazy queries that only start when awaited (like PrismaPromise)", async () => {
    const { collector, events } = collecting();
    const adapter = collector.instrumentQueryable(fakeAdapter());
    // Starts its query only when .then() is called, as PrismaPromise does.
    const lazy = {
      then: (resolve: (v: unknown) => void, reject: (e: unknown) => void) =>
        adapter.queryRaw({ sql: "SELECT lazy", args: [] }).then(resolve, reject),
    } as PromiseLike<unknown>;
    await collector.runOperation({ model: "User", operation: "findMany", args: {}, query: () => lazy });
    await collector.flush();
    expect(events()[0]?.statements.map((s) => s.sql)).toEqual(["SELECT lazy"]);
  });

  it("never captures parameter values", async () => {
    const { collector, events } = collecting();
    const adapter = collector.instrumentQueryable(fakeAdapter());
    await collector.runOperation({
      operation: "findFirst",
      args: {},
      query: () => adapter.queryRaw({ sql: "SELECT $1", args: ["secret@example.com"] }),
    });
    await collector.flush();
    expect(JSON.stringify(events())).not.toContain("secret@example.com");
  });

  it("attributes statements only to their own operation when operations overlap", async () => {
    const { collector, events } = collecting();
    const adapter = collector.instrumentQueryable(fakeAdapter());
    const run = (model: string, delay: number) =>
      collector.runOperation({
        model,
        operation: "findMany",
        args: {},
        query: async () => {
          await new Promise((resolve) => setTimeout(resolve, delay));
          return adapter.queryRaw({ sql: `SELECT * FROM "${model}"`, args: [] });
        },
      });
    await Promise.all([run("A", 15), run("B", 5)]);
    await collector.flush();
    expect(events().map((e) => [e.model, e.statements.map((s) => s.sql)])).toEqual(
      expect.arrayContaining([
        ["A", ['SELECT * FROM "A"']],
        ["B", ['SELECT * FROM "B"']],
      ]),
    );
  });

  it("instruments statements inside interactive transactions", async () => {
    const { collector, events } = collecting();
    const adapter = collector.instrumentQueryable(fakeAdapter());
    await collector.runOperation({
      operation: "$transaction",
      args: {},
      query: async () => {
        const tx = await adapter.startTransaction();
        return tx.queryRaw({ sql: "SELECT 1", args: [] });
      },
    });
    await collector.flush();
    expect(events()[0]?.statements.map((s) => s.sql)).toEqual(["SELECT 1"]);
  });

  it("rethrows query errors unchanged and records them", async () => {
    const { collector, events } = collecting();
    const failure = new Error("boom");
    await expect(
      collector.runOperation({ model: "User", operation: "create", args: {}, query: async () => Promise.reject(failure) }),
    ).rejects.toBe(failure);
    await collector.flush();
    expect(events()[0]).toMatchObject({ error: true, rowsReturned: null });
  });

  it("survives a throwing request-context provider", async () => {
    const { collector, events } = collecting({
      requestContext: () => {
        throw new Error("no request");
      },
    });
    await collector.runOperation({ operation: "count", args: {}, query: async () => 7 });
    await collector.flush();
    expect(events()[0]).toMatchObject({ requestId: null, route: null, rowsReturned: 1 });
  });
});

describe("delivery never blocks the request path", () => {
  it("returns the query result while the collector endpoint hangs", async () => {
    const hang = new Promise<void>(() => {});
    const collector = new Collector({ app: "t", send: () => hang, flushIntervalMs: 0, maxBatch: 1 });
    const started = Date.now();
    await collector.runOperation({ operation: "count", args: {}, query: async () => 1 });
    await collector.runOperation({ operation: "count", args: {}, query: async () => 1 });
    expect(Date.now() - started).toBeLessThan(50);
  });

  it("counts failed deliveries instead of throwing", async () => {
    const collector = new Collector({ app: "t", send: async () => Promise.reject(new Error("down")) });
    await collector.runOperation({ operation: "count", args: {}, query: async () => 1 });
    await expect(collector.flush()).resolves.toBeUndefined();
    expect(collector.stats()).toMatchObject({ captured: 1, sent: 0, dropped: 1, failedBatches: 1 });
  });

  it("drops events beyond the buffer limit rather than growing without bound", async () => {
    const { collector } = collecting({ maxBuffer: 2, maxBatch: 100, flushIntervalMs: 60_000 });
    for (let i = 0; i < 5; i++) await collector.runOperation({ operation: "count", args: {}, query: async () => 1 });
    expect(collector.stats()).toMatchObject({ captured: 5, buffered: 2, dropped: 3 });
    await collector.flush();
    expect(collector.stats()).toMatchObject({ sent: 2, buffered: 0 });
  });

  it("flushes automatically on its timer", async () => {
    const { collector, events } = collecting({ flushIntervalMs: 5 });
    await collector.runOperation({ operation: "count", args: {}, query: async () => 1 });
    await vi.waitFor(() => expect(events()).toHaveLength(1));
  });
});

describe("createCollector", () => {
  it("is disabled without an endpoint and leaves the adapter untouched", () => {
    const factory = { connect: async () => fakeAdapter() };
    const collector = createCollector({ app: "t", endpoint: "" });
    expect(collector.enabled).toBe(false);
    expect(collector.wrapAdapter(factory)).toBe(factory);
  });

  it("wraps the adapter returned by connect() when enabled", async () => {
    const inner = fakeAdapter();
    const collector = createCollector({ app: "t", endpoint: "http://localhost:1/v1/operations" });
    const adapter = (await collector.wrapAdapter({ connect: async () => inner }).connect()) as typeof inner;
    await adapter.queryRaw({ sql: "SELECT 1", args: [] });
    expect(inner.queryRaw).toHaveBeenCalledOnce();
    expect(collector.enabled).toBe(true);
  });
});

describe("countRows", () => {
  it.each([
    [[1, 2, 3], 3],
    [null, 0],
    [{ id: 1 }, 1],
    [42, 1],
    [{ count: 7 }, 7],
  ])("%j -> %j", (result, rows) => {
    expect(countRows(result)).toBe(rows);
  });
});
