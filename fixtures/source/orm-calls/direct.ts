import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

export async function listTeamUsers(teamId: number, cursor?: number) {
  return prisma.user.findMany({
    where: { teamId, active: true },
    take: 20,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    select: { id: true, name: true, team: { select: { name: true } } },
  });
}

export async function countOpenTasks() {
  const open = await prisma.task.count({ where: { status: "OPEN" } });
  const all = await prisma.task.count();
  return { open, all };
}

export async function loadProject(id: number) {
  return prisma.project.findUnique({ where: { id }, include: { tasks: true, team: false } });
}

const recentFilter = { createdAt: { gte: new Date(0) } };

export async function recentInvoices(teamId?: number) {
  return prisma.invoice.findMany({
    where: { ...recentFilter, AND: [{ amountCents: { gt: 0 } }, teamId ? { teamId } : {}] },
    take: 50,
  });
}

export async function forwarded(args: object) {
  return prisma.user.findMany(args);
}
