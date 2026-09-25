import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const RELATED_LIMIT = 5;

function findPublishedPost(slug: string) {
  return prisma.post.findFirst({
    where: { slug, status: PostStatus.PUBLISHED },
    select: { id: true, title: true, slug: true, tags: { select: { tagId: true } } },
  });
}

async function relatedPosts(slug: string) {
  const post = await findPublishedPost(slug);
  if (!post) return [];

  return prisma.post.findMany({
    where: {
      status: PostStatus.PUBLISHED,
      id: { not: post.id },
      tags: { some: { tagId: { in: post.tags.map((link) => link.tagId) } } },
    },
    orderBy: [{ publishedAt: "desc" }, { id: "desc" }],
    take: RELATED_LIMIT,
    select: { id: true, title: true, slug: true },
  });
}

// GET /api/posts/:slug/related
// "Read next" block at the end of a post.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const post = await findPublishedPost(slug);
  if (!post) return notFound();

  const related = await relatedPosts(slug);
  return NextResponse.json({ post: { id: post.id, title: post.title, slug: post.slug }, related });
}
