import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

async function averageCommentsPerPost(authorId: string) {
  const [posts, comments] = await Promise.all([
    prisma.post.count({ where: { authorId, status: PostStatus.PUBLISHED } }),
    prisma.comment.count({ where: { post: { authorId, status: PostStatus.PUBLISHED } } }),
  ]);
  return posts === 0 ? 0 : Math.round((comments / posts) * 10) / 10;
}

// GET /api/authors/:id/stats
// Engagement numbers on the author's profile page.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const author = await prisma.author.findUnique({ where: { id }, select: { id: true, name: true } });
  if (!author) return notFound();

  const [publishedPosts, commentsPerPost] = await Promise.all([
    prisma.post.count({ where: { authorId: id, status: PostStatus.PUBLISHED } }),
    averageCommentsPerPost(id),
  ]);

  return NextResponse.json({ ...author, publishedPosts, commentsPerPost });
}
