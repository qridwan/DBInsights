import { NextResponse } from "next/server";
import { MAX_PAGE_SIZE } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const PRODUCTS_PER_CATEGORY = 4;

// GET /api/categories/overview
// Storefront landing page: every category with its newest products.
export async function GET() {
  const categories = await prisma.category.findMany({
    orderBy: { name: "asc" },
    take: MAX_PAGE_SIZE,
    select: { id: true, name: true, slug: true },
  });

  const items = await Promise.all(
    categories.map(async (category) => ({
      ...category,
      products: await prisma.product.findMany({
        where: { categoryId: category.id },
        orderBy: [{ createdAt: "desc" }, { id: "desc" }],
        take: PRODUCTS_PER_CATEGORY,
        select: { id: true, name: true, priceCents: true },
      }),
    })),
  );

  return NextResponse.json({ items });
}
