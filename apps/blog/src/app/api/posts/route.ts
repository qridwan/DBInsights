import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { badRequest, isUuid, parsePageSize, toPage } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/posts?tag=&cursor=&limit=
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const tag = params.get("tag");
  const cursor = params.get("cursor");
  const pageSize = parsePageSize(params.get("limit"));
  if (cursor !== null && !isUuid(cursor)) return badRequest("invalid cursor");

  const rows = await prisma.post.findMany({
    where: {
      status: PostStatus.PUBLISHED,
      ...(tag ? { tags: { some: { tag: { slug: tag } } } } : {}),
    },
    orderBy: [{ publishedAt: "desc" }, { id: "desc" }],
    take: pageSize + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    select: {
      id: true,
      title: true,
      slug: true,
      excerpt: true,
      publishedAt: true,
      author: { select: { id: true, name: true } },
      tags: { select: { tag: { select: { name: true, slug: true } } } },
      _count: { select: { comments: true } },
    },
  });

  return NextResponse.json(toPage(rows, pageSize));
}
