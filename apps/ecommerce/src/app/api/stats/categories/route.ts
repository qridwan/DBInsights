import { NextResponse } from "next/server";
import { MAX_PAGE_SIZE } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/stats/categories
export async function GET() {
  const stats = await prisma.product.groupBy({
    by: ["categoryId"],
    _count: { _all: true },
    _avg: { priceCents: true },
    _sum: { stock: true },
    orderBy: { categoryId: "asc" },
    take: MAX_PAGE_SIZE,
  });

  const categories = await prisma.category.findMany({
    where: { id: { in: stats.map((row) => row.categoryId) } },
    take: MAX_PAGE_SIZE,
    select: { id: true, name: true, slug: true },
  });
  const byId = new Map(categories.map((category) => [category.id, category]));

  return NextResponse.json({
    items: stats.map((row) => ({
      category: byId.get(row.categoryId) ?? null,
      products: row._count._all,
      averagePriceCents: Math.round(row._avg.priceCents ?? 0),
      unitsInStock: row._sum.stock ?? 0,
    })),
  });
}
