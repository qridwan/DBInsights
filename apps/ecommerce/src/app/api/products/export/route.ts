import { NextResponse } from "next/server";
import { toCsv } from "@/lib/csv";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/products/export
// Full catalogue as CSV for the merchandising team's spreadsheet.
export async function GET() {
  const products = await prisma.product.findMany({
    orderBy: { sku: "asc" },
    select: {
      sku: true,
      name: true,
      priceCents: true,
      stock: true,
      category: { select: { name: true } },
    },
  });

  const csv = toCsv(
    ["sku", "name", "category", "price", "stock"],
    products.map((p) => [p.sku, p.name, p.category.name, (p.priceCents / 100).toFixed(2), p.stock]),
  );

  return new NextResponse(csv, {
    headers: {
      "content-type": "text/csv; charset=utf-8",
      "content-disposition": 'attachment; filename="products.csv"',
    },
  });
}
