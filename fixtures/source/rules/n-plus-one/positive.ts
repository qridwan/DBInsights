import { prisma } from "./db";

// Fires with HIGH confidence: the loop iterates over an ORM result.
export async function tasksPerUser() {
  const users = await prisma.user.findMany({ take: 50 });
  const counts: number[] = [];
  for (const user of users) {
    counts.push(await prisma.task.count({ where: { assigneeId: user.id } }));
  }
  return counts;
}

// Fires with MEDIUM confidence: in a loop, collection origin unknown.
export async function usersByIds(ids: number[]) {
  return Promise.all(ids.map((id) => prisma.user.findUnique({ where: { id } })));
}
