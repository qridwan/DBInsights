import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const FIRST_COMMENTS = 20;

// GET /api/posts/:slug
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const post = await prisma.post.findUnique({
    where: { slug },
    select: {
      id: true,
      title: true,
      slug: true,
      content: true,
      status: true,
      publishedAt: true,
      updatedAt: true,
      author: { select: { id: true, name: true, bio: true } },
      tags: { select: { tag: { select: { name: true, slug: true } } } },
      _count: { select: { comments: true } },
      comments: {
        orderBy: [{ createdAt: "asc" }, { id: "asc" }],
        take: FIRST_COMMENTS,
        select: { id: true, authorName: true, body: true, createdAt: true },
      },
    },
  });

  if (!post || post.status !== PostStatus.PUBLISHED) return notFound();
  return NextResponse.json(post);
}
