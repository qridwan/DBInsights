import { NextResponse, type NextRequest } from "next/server";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/categories/:slug
// Category page header: name, product count and price range.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const category = await prisma.category.findUnique({
    where: { slug },
    include: { products: true },
  });
  if (!category) return notFound();

  const prices = category.products.map((product) => product.priceCents);

  return NextResponse.json({
    id: category.id,
    name: category.name,
    slug: category.slug,
    productCount: category.products.length,
    priceRange: prices.length > 0 ? { minCents: Math.min(...prices), maxCents: Math.max(...prices) } : null,
  });
}
