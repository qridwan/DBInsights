import { prisma } from "../../../../db";

// GET /api/tasks: open-task count per user.
export async function GET() {
  const users = await prisma.user.findMany({ take: 50 });
  const counts: number[] = [];
  for (const user of users) {
    counts.push(await prisma.task.count({ where: { assigneeId: user.id } }));
  }
  return counts;
}
