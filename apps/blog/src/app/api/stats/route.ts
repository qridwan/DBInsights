import { NextResponse } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const TOP_N = 10;

async function topAuthors() {
  const ranked = await prisma.post.groupBy({
    by: ["authorId"],
    where: { status: PostStatus.PUBLISHED },
    _count: { _all: true },
    orderBy: { _count: { authorId: "desc" } },
    take: TOP_N,
  });

  const authors = await prisma.author.findMany({
    where: { id: { in: ranked.map((row) => row.authorId) } },
    take: TOP_N,
    select: { id: true, name: true },
  });
  const byId = new Map(authors.map((author) => [author.id, author]));

  return ranked.map((row) => ({
    author: byId.get(row.authorId) ?? null,
    publishedPosts: row._count._all,
  }));
}

async function mostDiscussedPosts() {
  const ranked = await prisma.comment.groupBy({
    by: ["postId"],
    _count: { _all: true },
    orderBy: { _count: { postId: "desc" } },
    take: TOP_N,
  });

  const posts = await prisma.post.findMany({
    where: { id: { in: ranked.map((row) => row.postId) } },
    take: TOP_N,
    select: { id: true, title: true, slug: true },
  });
  const byId = new Map(posts.map((post) => [post.id, post]));

  return ranked.map((row) => ({
    post: byId.get(row.postId) ?? null,
    comments: row._count._all,
  }));
}

// GET /api/stats
export async function GET() {
  const [authors, posts] = await Promise.all([topAuthors(), mostDiscussedPosts()]);
  return NextResponse.json({ topAuthors: authors, mostDiscussedPosts: posts });
}
