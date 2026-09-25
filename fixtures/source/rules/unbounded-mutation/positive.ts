import { prisma } from "./db";

export async function clearTasks() {
  return prisma.task.deleteMany();
}

export async function archiveEverything() {
  return prisma.project.updateMany({ data: { archived: true } });
}

// Statically empty where: MEDIUM confidence.
export async function clearInvoices() {
  return prisma.invoice.deleteMany({ where: {} });
}
