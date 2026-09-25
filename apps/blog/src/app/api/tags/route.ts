import { NextResponse } from "next/server";
import { MAX_PAGE_SIZE } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/tags
export async function GET() {
  const items = await prisma.tag.findMany({
    orderBy: { name: "asc" },
    take: MAX_PAGE_SIZE,
    select: {
      id: true,
      name: true,
      slug: true,
      _count: { select: { posts: true } },
    },
  });

  return NextResponse.json({ items });
}
