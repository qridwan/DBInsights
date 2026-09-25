import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const RECENT_REVIEWS = 10;

// GET /api/products/:id
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const [product, ratings] = await Promise.all([
    prisma.product.findUnique({
      where: { id },
      include: {
        category: { select: { id: true, name: true, slug: true } },
        reviews: {
          orderBy: [{ createdAt: "desc" }, { id: "desc" }],
          take: RECENT_REVIEWS,
          select: {
            id: true,
            rating: true,
            title: true,
            body: true,
            createdAt: true,
            customer: { select: { id: true, name: true } },
          },
        },
      },
    }),
    prisma.review.aggregate({
      where: { productId: id },
      _avg: { rating: true },
      _count: { _all: true },
    }),
  ]);

  if (!product) return notFound();

  return NextResponse.json({
    ...product,
    rating: { average: ratings._avg.rating, count: ratings._count._all },
  });
}
