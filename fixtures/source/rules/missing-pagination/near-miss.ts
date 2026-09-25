import { prisma } from "./db";

export async function firstPage() {
  return prisma.invoice.findMany({ take: 20, orderBy: { id: "asc" } });
}

export async function nextPage(cursor?: number) {
  return prisma.invoice.findMany({
    take: 20,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
  });
}

// Arguments not statically known.
export async function withArgs(args: object) {
  return prisma.task.findMany(args);
}

// Not a findMany.
export async function newestTask() {
  return prisma.task.findFirst({ orderBy: { createdAt: "desc" } });
}
