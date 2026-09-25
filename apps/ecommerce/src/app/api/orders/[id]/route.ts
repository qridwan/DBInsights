import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/orders/:id
export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) return notFound();

  const order = await prisma.order.findUnique({
    where: { id },
    select: {
      id: true,
      status: true,
      totalCents: true,
      createdAt: true,
      customer: { select: { id: true, name: true, email: true } },
      items: {
        select: {
          id: true,
          quantity: true,
          unitPriceCents: true,
          product: { select: { id: true, sku: true, name: true } },
        },
      },
    },
  });

  if (!order) return notFound();
  return NextResponse.json(order);
}
