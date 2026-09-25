// Records the SQL Prisma generates for one logical query at several argument
// counts, through the collector itself. The output is the fixture the Python
// fingerprinting tests use; re-run this to regenerate it:
//
//   DATABASE_URL=postgresql://dbinsight:dbinsight@localhost:5432/ecommerce \
//     pnpm --filter @dbinsight/collector exec tsx scripts/record-prisma-sql.ts > ../../fixtures/sql/prisma-in-variants.json
//
// Uses the ecommerce test app's generated client only as a convenient real
// Prisma schema; nothing in the collector depends on it.
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../../../apps/ecommerce/src/generated/prisma/client.js";
import { createCollector, type OperationEvent } from "../src/index.js";

const SIZES = [1, 5, 50];

async function main() {
  const events: OperationEvent[] = [];
  const collector = createCollector({ app: "recorder", send: async (batch) => void events.push(...batch) });
  const prisma = new PrismaClient({
    adapter: collector.wrapAdapter(new PrismaPg({ connectionString: process.env.DATABASE_URL })),
  }).$extends(collector.extension);

  const ids = (await prisma.product.findMany({ take: Math.max(...SIZES), orderBy: { sku: "asc" }, select: { id: true } })).map((p) => p.id);
  await collector.collector.flush();
  events.length = 0;

  const record = async (name: string, run: (batch: string[]) => Promise<unknown>) => {
    const variants: { size: number; sql: string[] }[] = [];
    for (const size of SIZES) {
      await run(ids.slice(0, size));
      await collector.collector.flush();
      variants.push({ size, sql: events.flatMap((event) => event.statements.map((statement) => statement.sql)) });
      events.length = 0;
    }
    return { name, variants };
  };

  const queries = [];
  queries.push(await record("findMany where id IN list", (batch) =>
    prisma.product.findMany({ where: { id: { in: batch } }, select: { id: true, name: true } })));
  queries.push(await record("findUnique batched by Promise.all", (batch) =>
    Promise.all(batch.map((id) => prisma.product.findUnique({ where: { id }, select: { id: true, name: true } })))));
  queries.push(await record("findMany with include and IN list", (batch) =>
    prisma.product.findMany({ where: { id: { in: batch } }, include: { category: true, reviews: { take: 2 } } })));

  process.stdout.write(JSON.stringify({ generator: "packages/collector/scripts/record-prisma-sql.ts", queries }, null, 2) + "\n");
  await prisma.$disconnect();
}

await main();
