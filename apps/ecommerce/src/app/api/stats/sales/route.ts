import { NextResponse, type NextRequest } from "next/server";
import { parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const DAY_MS = 24 * 60 * 60 * 1000;
const TOP_PRODUCTS = 10;

function salesByStatus(since: Date) {
  return prisma.order.groupBy({
    by: ["status"],
    where: { createdAt: { gte: since } },
    _count: { _all: true },
    _sum: { totalCents: true },
    orderBy: { status: "asc" },
  });
}

async function topProducts(since: Date) {
  const ranked = await prisma.orderItem.groupBy({
    by: ["productId"],
    where: { order: { createdAt: { gte: since } } },
    _sum: { quantity: true },
    orderBy: { _sum: { quantity: "desc" } },
    take: TOP_PRODUCTS,
  });

  const products = await prisma.product.findMany({
    where: { id: { in: ranked.map((row) => row.productId) } },
    take: TOP_PRODUCTS,
    select: { id: true, sku: true, name: true },
  });
  const byId = new Map(products.map((product) => [product.id, product]));

  return ranked.map((row) => ({
    product: byId.get(row.productId) ?? null,
    unitsSold: row._sum.quantity ?? 0,
  }));
}

// GET /api/stats/sales?days=30
export async function GET(request: NextRequest) {
  const days = parsePositiveInt(request.nextUrl.searchParams.get("days"), 30, 365);
  const since = new Date(Date.now() - days * DAY_MS);

  const [byStatus, top] = await Promise.all([salesByStatus(since), topProducts(since)]);

  return NextResponse.json({
    days,
    byStatus: byStatus.map((row) => ({
      status: row.status,
      orders: row._count._all,
      revenueCents: row._sum.totalCents ?? 0,
    })),
    topProducts: top,
  });
}
