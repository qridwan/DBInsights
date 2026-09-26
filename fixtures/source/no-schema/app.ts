import { prisma } from "./db";

// Needs no schema: a query in a loop over an ORM result, an unbounded findMany, an unbounded delete.
export async function perUser() {
  const users = await prisma.user.findMany({ take: 10 });
  for (const user of users) {
    await prisma.task.count({ where: { assigneeId: user.id } });
  }
}

export async function everything() {
  return prisma.invoice.findMany();
}

export async function wipe() {
  return prisma.task.deleteMany();
}

// Needs the declared schema: whether this filter column is indexed.
export async function largeInvoices() {
  return prisma.invoice.findMany({ where: { amountCents: { gt: 1 } }, take: 5 });
}
