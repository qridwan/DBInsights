import { prisma } from "./db";

// The second query uses the first query's result.
export async function projectOfTask(taskId: number) {
  const task = await prisma.task.findUniqueOrThrow({ where: { id: taskId } });
  const project = await prisma.project.findUnique({ where: { id: task.projectId } });
  return project;
}

// Already concurrent.
export async function dashboardParallel(teamId: number) {
  const [users, projects] = await Promise.all([
    prisma.user.count({ where: { teamId } }),
    prisma.project.count({ where: { teamId } }),
  ]);
  return { users, projects };
}

// A guard between the reads: the second only runs if the first succeeds.
export async function guarded(teamId: number) {
  const team = await prisma.team.findUnique({ where: { id: teamId } });
  if (!team) return null;
  const users = await prisma.user.count({ where: { teamId } });
  return { team, users };
}

// Writes: order can matter even without a visible data dependency.
export async function seedTeam(name: string) {
  await prisma.team.create({ data: { id: 1, name } });
  await prisma.project.create({ data: { name, teamId: 1 } });
}
