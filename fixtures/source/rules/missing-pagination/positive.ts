import { prisma } from "./db";

// No filter at all: HIGH confidence.
export async function allInvoices() {
  return prisma.invoice.findMany();
}

// Filtered but unbounded: MEDIUM confidence.
export async function openTasks() {
  return prisma.task.findMany({ where: { status: "OPEN" }, orderBy: { createdAt: "desc" } });
}
