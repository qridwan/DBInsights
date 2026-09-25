import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { badRequest, isUuid, parsePageSize, toPage } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/posts/:slug/comments?cursor=&limit=
export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const search = request.nextUrl.searchParams;
  const cursor = search.get("cursor");
  const pageSize = parsePageSize(search.get("limit"));
  if (cursor !== null && !isUuid(cursor)) return badRequest("invalid cursor");

  const rows = await prisma.comment.findMany({
    where: { post: { slug, status: PostStatus.PUBLISHED } },
    orderBy: [{ createdAt: "asc" }, { id: "asc" }],
    take: pageSize + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    select: { id: true, authorName: true, body: true, createdAt: true },
  });

  return NextResponse.json(toPage(rows, pageSize));
}
