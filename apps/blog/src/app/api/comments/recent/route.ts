import { NextResponse, type NextRequest } from "next/server";
import { parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const DAY_MS = 24 * 60 * 60 * 1000;
const SIDEBAR_SIZE = 10;

// GET /api/comments/recent?days=30
// "Latest discussion" sidebar across the whole blog.
export async function GET(request: NextRequest) {
  const days = parsePositiveInt(request.nextUrl.searchParams.get("days"), 30, 365);
  const since = new Date(Date.now() - days * DAY_MS);

  const items = await prisma.comment.findMany({
    where: { createdAt: { gte: since } },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: SIDEBAR_SIZE,
    select: {
      id: true,
      authorName: true,
      body: true,
      createdAt: true,
      post: { select: { slug: true, title: true } },
    },
  });

  return NextResponse.json({ items });
}
