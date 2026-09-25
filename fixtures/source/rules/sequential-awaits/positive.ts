import { prisma } from "./db";

export async function dashboard(teamId: number) {
  const users = await prisma.user.count({ where: { teamId } });
  const projects = await prisma.project.count({ where: { teamId } });
  const invoices = await prisma.invoice.findMany({ where: { teamId }, take: 10 });
  return { users, projects, invoices };
}
