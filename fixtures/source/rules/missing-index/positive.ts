import { prisma } from "./db";

// Invoice.amountCents has no index at all.
export async function largeInvoices() {
  return prisma.invoice.findMany({ where: { amountCents: { gt: 100_000 } }, take: 20 });
}

// Relation filter whose FK (Invoice.teamId) lives on Invoice and is unindexed.
export async function invoicesOfTeam(name: string) {
  return prisma.invoice.count({ where: { team: { name } } });
}

// User.createdAt is indexed only in second position of @@index([teamId, createdAt]).
export async function recentUsers(since: Date) {
  return prisma.user.findFirst({ where: { createdAt: { gte: since } } });
}

// Boolean-only filter: fires with LOW confidence.
export async function inactiveUsers() {
  return prisma.user.findMany({ where: { active: false }, take: 20 });
}
