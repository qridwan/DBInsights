import { NextResponse } from "next/server";
import { MAX_PAGE_SIZE } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/categories
export async function GET() {
  const items = await prisma.category.findMany({
    orderBy: { name: "asc" },
    take: MAX_PAGE_SIZE,
    select: {
      id: true,
      name: true,
      slug: true,
      _count: { select: { products: true } },
    },
  });

  return NextResponse.json({ items });
}
