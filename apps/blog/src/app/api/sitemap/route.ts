import { NextResponse } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/sitemap
// Every published post URL, consumed by the sitemap.xml generator.
export async function GET() {
  const posts = await prisma.post.findMany({
    where: { status: PostStatus.PUBLISHED },
    orderBy: { publishedAt: "desc" },
    select: { slug: true, updatedAt: true },
  });

  return NextResponse.json({
    entries: posts.map((post) => ({ path: `/posts/${post.slug}`, lastModified: post.updatedAt })),
  });
}
