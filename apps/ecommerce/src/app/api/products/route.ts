import { NextResponse, type NextRequest } from "next/server";
import { badRequest, isUuid, parsePageSize, toPage } from "@/lib/http";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

// GET /api/products?categoryId=&cursor=&limit=
export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const categoryId = params.get("categoryId");
  const cursor = params.get("cursor");
  const pageSize = parsePageSize(params.get("limit"));

  if (categoryId !== null && !isUuid(categoryId)) return badRequest("invalid categoryId");
  if (cursor !== null && !isUuid(cursor)) return badRequest("invalid cursor");

  const rows = await prisma.product.findMany({
    where: categoryId ? { categoryId } : undefined,
    orderBy: [{ createdAt: "desc" }, { id: "desc" }],
    take: pageSize + 1,
    ...(cursor ? { cursor: { id: cursor }, skip: 1 } : {}),
    select: {
      id: true,
      sku: true,
      name: true,
      priceCents: true,
      stock: true,
      createdAt: true,
      category: { select: { id: true, name: true, slug: true } },
    },
  });

  return NextResponse.json(toPage(rows, pageSize));
}
