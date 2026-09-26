import { prisma } from "./db";

// Filters on a field whose database column has a different name and no index.
export async function ticketsOf(ownerId: number) {
  return prisma.ticket.findMany({ where: { ownerId }, take: 20 });
}

export async function countTickets(ownerId: number) {
  for (const id of [ownerId]) {
    await prisma.ticket.count({ where: { id } });
  }
}
