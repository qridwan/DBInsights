import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const MAX_TAGS = 100;

function loadTags() {
  return prisma.tag.findMany({
    orderBy: { name: "asc" },
    take: MAX_TAGS,
    select: { id: true, name: true, slug: true, _count: { select: { posts: true } } },
  });
}

async function tagWeights() {
  const tags = await loadTags();
  const max = Math.max(1, ...tags.map((tag) => tag._count.posts));
  return new Map(tags.map((tag) => [tag.id, Math.round((tag._count.posts / max) * 4) + 1]));
}

// GET /api/tags/cloud
// Sidebar tag cloud: every tag with a 1-5 display weight.
export async function GET() {
  const [tags, weights] = await Promise.all([loadTags(), tagWeights()]);

  return NextResponse.json({
    items: tags.map((tag) => ({ name: tag.name, slug: tag.slug, weight: weights.get(tag.id) ?? 1 })),
  });
}
