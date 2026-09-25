import { NextResponse, type NextRequest } from "next/server";
import { parsePageSize, parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const DAY_MS = 24 * 60 * 60 * 1000;

// GET /api/posts/new?days=30&limit=
// Editorial queue: everything written recently, drafts included, newest first.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const days = parsePositiveInt(params.get("days"), 30, 365);
  const since = new Date(Date.now() - days * DAY_MS);

  const items = await prisma.post.findMany({
    where: { createdAt: { gte: since } },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: parsePageSize(params.get("limit")),
    select: { id: true, slug: true, title: true, status: true, createdAt: true },
  });

  return NextResponse.json({ days, items });
}
