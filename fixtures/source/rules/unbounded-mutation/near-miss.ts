import { prisma } from "./db";

export async function clearProjectTasks(projectId: number) {
  return prisma.task.deleteMany({ where: { projectId } });
}

const archivedOnly = { archived: true };

export async function reopenArchived() {
  return prisma.project.updateMany({ where: archivedOnly, data: { archived: false } });
}

// Only OR branches: bounded, even though there is no top-level field key.
export async function clearDoneOrOrphaned() {
  return prisma.task.deleteMany({ where: { OR: [{ status: "DONE" }, { assigneeId: null }] } });
}

// Arguments come from the caller: not statically known, not reported.
export async function deleteWith(args: { where: { id: number } }) {
  return prisma.invoice.deleteMany(args);
}

// Single-row mutation.
export async function deleteOne(id: number) {
  return prisma.invoice.delete({ where: { id } });
}
