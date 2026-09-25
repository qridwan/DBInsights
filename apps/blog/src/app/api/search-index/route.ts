import { NextResponse } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/search-index
// Prebuilt index loaded once by the client-side search box.
export async function GET() {
  const posts = await prisma.post.findMany({
    where: { status: PostStatus.PUBLISHED },
    select: {
      slug: true,
      title: true,
      excerpt: true,
      tags: { select: { tag: { select: { name: true } } } },
    },
  });

  return NextResponse.json({
    documents: posts.map((post) => ({
      slug: post.slug,
      title: post.title,
      excerpt: post.excerpt,
      tags: post.tags.map((link) => link.tag.name),
    })),
  });
}
