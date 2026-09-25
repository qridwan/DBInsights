import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const RELATED_LIMIT = 8;

function loadProduct(id: string) {
  return prisma.product.findUnique({
    where: { id },
    select: { id: true, name: true, priceCents: true, categoryId: true },
  });
}

async function relatedProducts(productId: string) {
  const product = await loadProduct(productId);
  if (!product) return [];

  return prisma.product.findMany({
    where: { categoryId: product.categoryId, id: { not: product.id } },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: RELATED_LIMIT,
    select: { id: true, name: true, priceCents: true },
  });
}

// GET /api/products/:id/related
// "You may also like" carousel on the product page.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const product = await loadProduct(id);
  if (!product) return notFound();

  const related = await relatedProducts(id);
  return NextResponse.json({ product: { id: product.id, name: product.name }, related });
}
