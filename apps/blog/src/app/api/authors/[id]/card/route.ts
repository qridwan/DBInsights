import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/authors/:id/card
// Hover card shown next to an author's byline.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const author = await prisma.author.findUnique({
    where: { id },
    include: { posts: true },
  });
  if (!author) return notFound();

  const published = author.posts.filter((post) => post.status === PostStatus.PUBLISHED);
  const latest = published.reduce<Date | null>(
    (max, post) => (post.publishedAt && (!max || post.publishedAt > max) ? post.publishedAt : max),
    null,
  );

  return NextResponse.json({
    id: author.id,
    name: author.name,
    bio: author.bio,
    publishedPosts: published.length,
    latestPostAt: latest,
  });
}
