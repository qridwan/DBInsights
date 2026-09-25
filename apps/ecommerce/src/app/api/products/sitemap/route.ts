import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/products/sitemap
// Entries consumed by the storefront's sitemap.xml generator.
export async function GET() {
  const products = await prisma.product.findMany({
    orderBy: { createdAt: "asc" },
    select: { id: true, updatedAt: true },
  });

  return NextResponse.json({
    entries: products.map((product) => ({ path: `/products/${product.id}`, lastModified: product.updatedAt })),
  });
}
