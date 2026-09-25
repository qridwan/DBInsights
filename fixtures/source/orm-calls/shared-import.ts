import database from "./db";
import { prisma as client } from "./db";

export async function renameUser(id: number, name: string) {
  return client.$transaction(async (tx) => {
    const existing = await tx.user.findUniqueOrThrow({ where: { id } });
    return tx.user.update({ where: { id: existing.id }, data: { name } });
  });
}

export async function teamNames() {
  return database.team.findMany({ select: { name: true }, take: 100 });
}
