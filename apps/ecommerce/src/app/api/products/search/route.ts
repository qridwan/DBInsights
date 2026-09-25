import { NextResponse, type NextRequest } from "next/server";
import { badRequest, parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const MIN_QUERY_LENGTH = 3;

// GET /api/products/search?q=&limit=
// Substring match on name, served by the trigram GIN index.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const query = params.get("q")?.trim() ?? "";
  if (query.length < MIN_QUERY_LENGTH) {
    return badRequest(`q must be at least ${MIN_QUERY_LENGTH} characters`);
  }

  const items = await prisma.product.findMany({
    where: { name: { contains: query, mode: "insensitive" } },
    orderBy: [{ name: "asc" }, { id: "asc" }],
    take: parsePageSize(params.get("limit")),
    select: {
      id: true,
      sku: true,
      name: true,
      priceCents: true,
      category: { select: { id: true, name: true } },
    },
  });

  return NextResponse.json({ items });
}
