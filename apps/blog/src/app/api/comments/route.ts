import { NextResponse, type NextRequest } from "next/server";
import { badRequest, parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/comments?email=&limit=
// Moderation tool: everything a given commenter has posted, newest first.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const email = params.get("email")?.trim().toLowerCase();
  if (!email) return badRequest("email is required");

  const items = await prisma.comment.findMany({
    where: { authorEmail: email },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: parsePageSize(params.get("limit")),
    select: {
      id: true,
      authorName: true,
      body: true,
      createdAt: true,
      post: { select: { slug: true, title: true } },
    },
  });

  return NextResponse.json({ email, items });
}
