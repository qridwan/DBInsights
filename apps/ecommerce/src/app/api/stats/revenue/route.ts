import { NextResponse, type NextRequest } from "next/server";
import { OrderStatus } from "@/generated/prisma/client";
import { parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const DAY_MS = 24 * 60 * 60 * 1000;

// GET /api/stats/revenue?days=90
// Daily revenue series for the dashboard chart.
export async function GET(request: NextRequest) {
  const days = parsePositiveInt(request.nextUrl.searchParams.get("days"), 90, 365);
  const since = new Date(Date.now() - days * DAY_MS);

  const orders = await prisma.order.findMany({
    where: { createdAt: { gte: since }, status: { not: OrderStatus.CANCELLED } },
    select: { createdAt: true, totalCents: true },
  });

  const byDay = new Map<string, number>();
  for (const order of orders) {
    const day = order.createdAt.toISOString().slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + order.totalCents);
  }

  const series = [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, revenueCents]) => ({ day, revenueCents }));

  return NextResponse.json({ days, series });
}
