import { createCollector } from "@dbinsight/collector";
import { nextRequestContext } from "@dbinsight/collector/next";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "@/generated/prisma/client";

// Runtime query collection for DBInsight. Disabled (no hook in the query path)
// unless DBINSIGHT_COLLECTOR_URL is set.
const collector = createCollector({
  app: "blog",
  endpoint: process.env.DBINSIGHT_COLLECTOR_URL,
  requestContext: nextRequestContext,
});

function createClient() {
  const adapter = collector.wrapAdapter(new PrismaPg({ connectionString: process.env.DATABASE_URL }));
  return new PrismaClient({ adapter }).$extends(collector.extension);
}

const globalForPrisma = globalThis as unknown as { prisma?: ReturnType<typeof createClient> };

export const prisma = globalForPrisma.prisma ?? createClient();

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
