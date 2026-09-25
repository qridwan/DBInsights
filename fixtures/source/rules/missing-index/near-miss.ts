import { prisma } from "./db";

// Leading column of @@index([teamId, createdAt]).
export async function usersOfTeam(teamId: number) {
  return prisma.user.findMany({ where: { teamId, createdAt: { gte: new Date(0) } }, take: 20 });
}

// Unique lookups are not judged by this rule.
export async function userByEmail(email: string) {
  return prisma.user.findUnique({ where: { email } });
}

// findFirst on a @unique field is covered.
export async function firstByEmail(email: string) {
  return prisma.user.findFirst({ where: { email } });
}

// One filtered column (teamId) has a usable index; the extra filter is applied after.
export async function namedUsersOfTeam(teamId: number, name: string) {
  return prisma.user.findMany({ where: { teamId, name }, take: 20 });
}

// Relation filter whose FK lives on the other model: a join, not judged here.
export async function projectsWithOpenTasks() {
  return prisma.project.findMany({ where: { tasks: { some: { status: "OPEN" } } }, take: 20 });
}

// Relation filter through an indexed FK (Task.projectId leads @@index([projectId, createdAt])).
export async function tasksOfArchivedProjects() {
  return prisma.task.count({ where: { project: { archived: true } } });
}

// Filter shape not statically known.
export async function dynamicFilter(filter: object) {
  return prisma.invoice.findMany({ where: filter, take: 20 });
}

// Mutations and aggregations are out of scope.
export async function bumpInvoices() {
  return prisma.invoice.updateMany({ where: { amountCents: 0 }, data: { memo: "zero" } });
}
