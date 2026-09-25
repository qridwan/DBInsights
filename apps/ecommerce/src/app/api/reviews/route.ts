import { NextResponse, type NextRequest } from "next/server";
import { badRequest, parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/reviews?rating=1&limit=
// Moderation queue: newest reviews with a given star rating.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const rating = Number(params.get("rating") ?? 1);
  if (!Number.isInteger(rating) || rating < 1 || rating > 5) return badRequest("rating must be 1-5");

  const items = await prisma.review.findMany({
    where: { rating },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: parsePageSize(params.get("limit")),
    select: {
      id: true,
      rating: true,
      title: true,
      body: true,
      createdAt: true,
      product: { select: { id: true, name: true } },
      customer: { select: { id: true, name: true } },
    },
  });

  return NextResponse.json({ items });
}
