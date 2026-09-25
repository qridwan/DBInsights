import { NextResponse, type NextRequest } from "next/server";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/categories/:slug/ratings
// Average customer rating across a category, shown on the category page.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const category = await prisma.category.findUnique({
    where: { slug },
    include: { products: { include: { reviews: true } } },
  });
  if (!category) return notFound();

  const ratings = category.products.flatMap((product) => product.reviews.map((review) => review.rating));
  const average = ratings.length > 0 ? ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length : null;

  return NextResponse.json({
    category: { id: category.id, name: category.name },
    reviewCount: ratings.length,
    averageRating: average === null ? null : Math.round(average * 100) / 100,
  });
}
