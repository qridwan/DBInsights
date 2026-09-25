import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const RECENT_POSTS = 20;

// GET /api/authors/:id
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const author = await prisma.author.findUnique({
    where: { id },
    select: {
      id: true,
      name: true,
      bio: true,
      createdAt: true,
      _count: { select: { posts: { where: { status: PostStatus.PUBLISHED } } } },
      posts: {
        where: { status: PostStatus.PUBLISHED },
        orderBy: [{ publishedAt: "desc" }, { id: "desc" }],
        take: RECENT_POSTS,
        select: { id: true, title: true, slug: true, excerpt: true, publishedAt: true },
      },
    },
  });

  if (!author) return notFound();
  return NextResponse.json(author);
}
