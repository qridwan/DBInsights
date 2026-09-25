import { NextResponse, type NextRequest } from "next/server";
import { isUuid, notFound } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/orders/:id/invoice
// Invoice lines for the printable invoice and the confirmation email.
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
      customer: { select: { name: true, email: true } },
      items: { select: { productId: true, quantity: true, unitPriceCents: true } },
    },
  });
  if (!order) return notFound();

  const lines = [];
  for (const item of order.items) {
    const product = await prisma.product.findUnique({
      where: { id: item.productId },
      select: { sku: true, name: true },
    });
    lines.push({
      sku: product?.sku ?? null,
      name: product?.name ?? "Unknown product",
      quantity: item.quantity,
      unitPriceCents: item.unitPriceCents,
      lineTotalCents: item.quantity * item.unitPriceCents,
    });
  }

  return NextResponse.json({
    orderId: order.id,
    status: order.status,
    issuedAt: order.createdAt,
    billTo: order.customer,
    lines,
    totalCents: order.totalCents,
  });
}
