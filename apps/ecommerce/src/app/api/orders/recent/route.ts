import { NextResponse, type NextRequest } from "next/server";
import { parsePageSize } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/orders/recent?limit=
// Admin dashboard widget: latest orders with the customer who placed them.
export async function GET(request: NextRequest) {
  const orders = await prisma.order.findMany({
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: parsePageSize(request.nextUrl.searchParams.get("limit")),
    select: { id: true, status: true, totalCents: true, createdAt: true, customerId: true },
  });

  const items = [];
  for (const order of orders) {
    const customer = await prisma.customer.findUnique({
      where: { id: order.customerId },
      select: { id: true, name: true, email: true },
    });
    items.push({ ...order, customer });
  }

  return NextResponse.json({ items });
}
