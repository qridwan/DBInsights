import { NextResponse, type NextRequest } from "next/server";
import { OrderStatus } from "@/generated/prisma/client";
import { badRequest, parsePageSize, parsePositiveInt } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const STATUSES = new Set<string>(Object.values(OrderStatus));

// GET /api/orders?status=PENDING&page=&limit=
// Fulfilment queue for the operations team, oldest first.
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const status = params.get("status") ?? OrderStatus.PENDING;
  if (!STATUSES.has(status)) return badRequest("invalid status");

  const pageSize = parsePageSize(params.get("limit"));
  const page = parsePositiveInt(params.get("page"), 1, 1000);
  const where = { status: status as OrderStatus };

  const [total, items] = await Promise.all([
    prisma.order.count({ where }),
    prisma.order.findMany({
      where,
      orderBy: [{ createdAt: "asc" }, { id: "asc" }],
      skip: (page - 1) * pageSize,
      take: pageSize,
      select: { id: true, status: true, totalCents: true, createdAt: true, customerId: true },
    }),
  ]);

  return NextResponse.json({ page, pageSize, total, items });
}
