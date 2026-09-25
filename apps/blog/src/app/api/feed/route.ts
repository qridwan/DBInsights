import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/feed?limit=
// Homepage feed cards: latest posts with their comment counts.
export async function GET(request: NextRequest) {
  const posts = await prisma.post.findMany({
    where: { status: PostStatus.PUBLISHED },
    orderBy: [{ publishedAt: "desc" }, { id: "desc" }],
    take: parsePageSize(request.nextUrl.searchParams.get("limit")),
    select: {
      id: true,
      title: true,
      slug: true,
      excerpt: true,
      publishedAt: true,
      author: { select: { name: true } },
    },
  });

  const items = [];
  for (const post of posts) {
    const comments = await prisma.comment.count({ where: { postId: post.id } });
    items.push({ ...post, comments });
  }

  return NextResponse.json({ items });
}
