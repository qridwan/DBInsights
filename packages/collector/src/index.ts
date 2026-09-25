import { Collector, type CollectorOptions } from "./collector";

export { Collector, countRows, type CollectorOptions } from "./collector";
export type * from "./types";

interface OperationParams {
  model?: string;
  operation: string;
  args: any; // eslint-disable-line @typescript-eslint/no-explicit-any -- Prisma's own parameter type
  query: (args: any) => PromiseLike<any>; // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface CollectorExtension {
  name: string;
  query?: { $allOperations(params: OperationParams): Promise<unknown> };
}

/** The subset of a Prisma driver-adapter factory the collector wraps. */
interface AdapterFactory {
  connect(): Promise<unknown>;
}

export interface PrismaCollector {
  readonly enabled: boolean;
  readonly collector: Collector;
  /** Wraps a driver-adapter factory (e.g. `new PrismaPg(...)`) to capture SQL. Identity when disabled. */
  wrapAdapter<F extends AdapterFactory>(factory: F): F;
  /**
   * Prisma client extension arguments for `client.$extends(extension)`. A
   * plain object so the application's own generated client types it. It
   * has no query hook at all when disabled.
   */
  readonly extension: CollectorExtension;
}

/**
 * Creates the runtime collector for one Prisma client:
 *
 *   const collector = createCollector({ app: "shop", endpoint: process.env.DBINSIGHT_COLLECTOR_URL });
 *   const prisma = new PrismaClient({ adapter: collector.wrapAdapter(new PrismaPg(...)) })
 *     .$extends(collector.extension);
 *
 * With no endpoint it is disabled and adds no hook to the query path.
 */
export function createCollector(options: CollectorOptions): PrismaCollector {
  const collector = new Collector(options);
  if (!collector.enabled) {
    return {
      enabled: false,
      collector,
      wrapAdapter: (factory) => factory,
      extension: { name: "dbinsight-collector-disabled" },
    };
  }

  return {
    enabled: true,
    collector,
    wrapAdapter: <F extends AdapterFactory>(factory: F): F =>
      new Proxy(factory, {
        get: (target, property, receiver) => {
          const value = Reflect.get(target, property, receiver);
          if (property === "connect") {
            return async () =>
              collector.instrumentQueryable(
                (await target.connect()) as Parameters<Collector["instrumentQueryable"]>[0],
              );
          }
          return typeof value === "function" ? value.bind(target) : value;
        },
      }),
    extension: {
      name: "dbinsight-collector",
      query: {
        $allOperations: ({ model, operation, args, query }) => collector.runOperation({ model, operation, args, query }),
      },
    },
  };
}
