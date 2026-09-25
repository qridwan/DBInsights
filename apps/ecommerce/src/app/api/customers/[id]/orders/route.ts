import { NextResponse, type NextRequest } from "next/server";
import { badRequest, isUuid, notFound, parsePageSize, toPage } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/customers/:id/orders?cursor=&limit=
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const search = request.nextUrl.searchParams;
  const cursor = search.get("cursor");
  const pageSize = parsePageSize(search.get("limit"));
  if (cursor !== null && !isUuid(cursor)) return badRequest("invalid cursor");

  const rows = await prisma.order.findMany({
    where: { customerId: id },
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: pageSize + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    select: {
      id: true,
      status: true,
      totalCents: true,
      createdAt: true,
      _count: { select: { items: true } },
    },
  });

  return NextResponse.json(toPage(rows, pageSize));
}
