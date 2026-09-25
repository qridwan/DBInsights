import { PrismaClient } from "@prisma/client";

// Shared client module, the most common layout in real projects.
export const prisma = new PrismaClient();

export default prisma;
