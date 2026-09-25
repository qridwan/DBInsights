import { NextResponse, type NextRequest } from "next/server";
import { PostStatus } from "@/generated/prisma/client";
import { badRequest, parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const MIN_QUERY_LENGTH = 3;

// GET /api/posts/search?q=&limit=
// Substring match on title, served by the trigram GIN index.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const query = params.get("q")?.trim() ?? "";
  if (query.length < MIN_QUERY_LENGTH) {
    return badRequest(`q must be at least ${MIN_QUERY_LENGTH} characters`);
  }

  const items = await prisma.post.findMany({
    where: {
      status: PostStatus.PUBLISHED,
      title: { contains: query, mode: "insensitive" },
    },
    orderBy: [{ publishedAt: "desc" }, { id: "desc" }],
    take: parsePageSize(params.get("limit")),
    select: {
      id: true,
      title: true,
      slug: true,
      excerpt: true,
      publishedAt: true,
      author: { select: { id: true, name: true } },
    },
  });

  return NextResponse.json({ items });
}
