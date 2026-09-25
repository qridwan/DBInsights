import { prisma } from "./db";

// The related rows are loaded by the parent query; the loop only reads memory.
export async function tasksPerUserIncluded() {
  const users = await prisma.user.findMany({ take: 50, include: { tasks: true } });
  const counts: number[] = [];
  for (const user of users) {
    counts.push(user.tasks.length);
  }
  return counts;
}

// One batched query instead of one per id.
export async function usersByIdsBatched(ids: number[]) {
  return prisma.user.findMany({ where: { id: { in: ids } }, take: ids.length });
}

// The Prisma call is the loop's iterable, evaluated once.
export async function namesOfTeams() {
  const names: string[] = [];
  for (const team of await prisma.team.findMany({ take: 20 })) names.push(team.name);
  return names;
}
