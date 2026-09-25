import { NextResponse } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { MAX_PAGE_SIZE } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/authors
// Author directory with each author's published post count.
export async function GET() {
  const authors = await prisma.author.findMany({
    orderBy: { name: "asc" },
    take: MAX_PAGE_SIZE,
    select: { id: true, name: true, bio: true },
  });

  const items = await Promise.all(
    authors.map(async (author) => ({
      ...author,
      publishedPosts: await prisma.post.count({
        where: { authorId: author.id, status: PostStatus.PUBLISHED },
      }),
    })),
  );

  return NextResponse.json({ items });
}
