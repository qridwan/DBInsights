import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const CUSTOMER_FIELDS = { id: true, name: true, email: true, createdAt: true } as const;
const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

async function orderStats(customerId: string) {
  const [customer, totals] = await Promise.all([
    prisma.customer.findUnique({ where: { id: customerId }, select: CUSTOMER_FIELDS }),
    prisma.order.aggregate({
      where: { customerId },
      _count: { _all: true },
      _sum: { totalCents: true },
      _max: { createdAt: true },
    }),
  ]);

  const months = customer ? Math.max(1, Math.round((Date.now() - customer.createdAt.getTime()) / MONTH_MS)) : 1;
  return {
    orders: totals._count._all,
    spentCents: totals._sum.totalCents ?? 0,
    lastOrderAt: totals._max.createdAt,
    ordersPerMonth: Math.round((totals._count._all / months) * 100) / 100,
  };
}

// GET /api/customers/:id/summary
// Customer card for the support console.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const customer = await prisma.customer.findUnique({ where: { id }, select: CUSTOMER_FIELDS });
  if (!customer) return notFound();

  return NextResponse.json({ ...customer, orders: await orderStats(id) });
}
