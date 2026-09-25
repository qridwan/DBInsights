import { NextResponse, type NextRequest } from "next/server";
import { MAX_PAGE_SIZE, parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/products/low-stock?threshold=10
// Restock report: products at or below the stock threshold, scarcest first.
export async function GET(request: NextRequest) {
  const threshold = parsePositiveInt(request.nextUrl.searchParams.get("threshold"), 10, 1000);

  const items = await prisma.product.findMany({
    where: { stock: { lte: threshold } },
    orderBy: [{ stock: "asc" }, { name: "asc" }],
    take: MAX_PAGE_SIZE,
    select: { id: true, sku: true, name: true, stock: true, category: { select: { name: true } } },
  });

  return NextResponse.json({ threshold, items });
}
