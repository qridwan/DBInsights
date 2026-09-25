import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/customers/:id
// Account overview shown at the top of the customer's account page.
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const customer = await prisma.customer.findUnique({
    where: { id },
    include: { orders: { include: { items: true } }, reviews: true },
  });
  if (!customer) return notFound();

  return NextResponse.json({
    id: customer.id,
    name: customer.name,
    email: customer.email,
    memberSince: customer.createdAt,
    orderCount: customer.orders.length,
    lifetimeValueCents: customer.orders.reduce((sum, order) => sum + order.totalCents, 0),
    reviewCount: customer.reviews.length,
  });
}
