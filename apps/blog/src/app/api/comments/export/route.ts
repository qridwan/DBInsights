import { NextResponse } from "next/server";
import { toCsv } from "@/lib/csv";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/comments/export
// All comments as CSV for the moderation team's periodic review.
export async function GET() {
  const comments = await prisma.comment.findMany({
    orderBy: { createdAt: "asc" },
    select: {
      id: true,
      authorName: true,
      authorEmail: true,
      body: true,
      createdAt: true,
      post: { select: { slug: true } },
    },
  });

  const csv = toCsv(
    ["id", "post", "author", "email", "created_at", "body"],
    comments.map((c) => [c.id, c.post.slug, c.authorName, c.authorEmail, c.createdAt.toISOString(), c.body]),
  );

  return new NextResponse(csv, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="comments.csv"',
    },
  });
}
