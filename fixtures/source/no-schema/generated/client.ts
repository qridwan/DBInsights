// Stands in for generated Prisma client output: never application code.
import { prisma } from "../db";

export async function generatedHelper() {
  return prisma.user.findMany();
}
