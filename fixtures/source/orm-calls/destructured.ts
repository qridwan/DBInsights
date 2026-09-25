import { prisma } from "./db";

const { user, project: projects } = prisma;
const tasks = prisma.task;

export async function firstActive() {
  return user.findFirst({ where: { active: true } });
}

export async function archivedProjects() {
  return projects.findMany({ where: { archived: true }, take: 10 });
}

export async function purgeTasks() {
  return tasks.deleteMany();
}
