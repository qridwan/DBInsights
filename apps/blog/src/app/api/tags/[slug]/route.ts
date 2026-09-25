import { NextResponse, type NextRequest } from "next/server";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/tags/:slug
// Tag page header: post count and how many authors write about it.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const tag = await prisma.tag.findUnique({
    where: { slug },
    include: { posts: { include: { post: { include: { author: true } } } } },
  });
  if (!tag) return notFound();

  const authors = new Set(tag.posts.map((link) => link.post.author.id));

  return NextResponse.json({
    name: tag.name,
    slug: tag.slug,
    postCount: tag.posts.length,
    authorCount: authors.size,
  });
}
