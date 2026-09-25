import { PrismaClient } from "@prisma/client";
import { prisma } from "./db";

export const listUsers = async () => prisma.user.findMany({ take: 5 });

export class TaskService {
  private readonly audit = new PrismaClient();

  constructor(private readonly db: PrismaClient) {}

  async openTasks(projectId: number) {
    return this.db.task.findMany({ where: { projectId, status: "OPEN" }, take: 100 });
  }

  countInvoices = async () => this.audit.invoice.count();
}
