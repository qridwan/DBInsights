import { PrismaClient } from "@prisma/client";
import { prisma } from "./db";

// None of these are Prisma model operations; none may be located.

const cache = { user: { findMany: (_args?: object) => [] as unknown[] } };

interface Holder {
  prisma: PrismaClient;
  user: { findMany(): unknown[] };
}

export async function lookalikes(holder: Holder, repo: { user: { count(): number } }) {
  cache.user.findMany({ where: { teamId: 1 } });
  holder.user.findMany();
  repo.user.count();
  [1, 2, 3].find((n) => n > 1);
  await prisma.$queryRaw`SELECT 1`;
  // A delegate that does not exist in the schema.
  await (prisma as unknown as { ghost: { findMany(): Promise<unknown[]> } }).ghost.findMany();
}
