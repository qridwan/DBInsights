import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/tags/:slug/posts?limit=
// Posts filed under a tag, for the tag archive page.
export async function GET(request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const links = await prisma.postTag.findMany({
    where: { tag: { slug } },
    take: parsePageSize(request.nextUrl.searchParams.get("limit")),
    select: { postId: true },
  });

  const posts = [];
  for (const link of links) {
    const post = await prisma.post.findUnique({
      where: { id: link.postId },
      select: { id: true, title: true, slug: true, excerpt: true, status: true, publishedAt: true },
    });
    if (post?.status === PostStatus.PUBLISHED) posts.push(post);
  }

  return NextResponse.json({ tag: slug, items: posts });
}
