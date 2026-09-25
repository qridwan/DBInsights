import { NextResponse, type NextRequest } from "next/server";
import { notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/posts/:slug/meta
// Open Graph and SEO metadata for a post page's <head>.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const post = await prisma.post.findUnique({
    where: { slug },
    include: { author: true, tags: { include: { tag: true } }, comments: true },
  });
  if (!post) return notFound();

  return NextResponse.json({
    title: post.title,
    description: post.excerpt,
    author: post.author.name,
    keywords: post.tags.map((link) => link.tag.name),
    publishedAt: post.publishedAt,
    commentCount: post.comments.length,
  });
}
