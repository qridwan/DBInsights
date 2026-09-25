import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

async function averageOrderValueCents() {
  const [orders, revenue] = await Promise.all([
    prisma.order.count(),
    prisma.order.aggregate({ _sum: { totalCents: true } }),
  ]);
  return orders === 0 ? 0 : Math.round((revenue._sum.totalCents ?? 0) / orders);
}

// GET /api/stats/overview
// Headline numbers for the admin dashboard.
export async function GET() {
  const [orders, customers, averageOrderValue] = await Promise.all([
    prisma.order.count(),
    prisma.customer.count(),
    averageOrderValueCents(),
  ]);

  return NextResponse.json({ orders, customers, averageOrderValueCents: averageOrderValue });
}
