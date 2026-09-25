import { NextResponse } from "next/server";

export const DEFAULT_PAGE_SIZE = 20;
export const MAX_PAGE_SIZE = 100;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string | null | undefined): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

export function parsePageSize(value: string | null): number {
  const size = Number(value);
  if (!Number.isInteger(size) || size <= 0) return DEFAULT_PAGE_SIZE;
  return Math.min(size, MAX_PAGE_SIZE);
}

export function parsePositiveInt(value: string | null, fallback: number, max: number): number {
  const n = Number(value);
  if (!Number.isInteger(n) || n <= 0) return fallback;
  return Math.min(n, max);
}

/**
 * Callers fetch `pageSize + 1` rows; the extra row only signals that another
 * page exists and is not returned.
 */
export function toPage<T extends { id: string }>(rows: T[], pageSize: number) {
  const hasMore = rows.length > pageSize;
  const items = hasMore ? rows.slice(0, pageSize) : rows;
  return { items, nextCursor: hasMore ? (items.at(-1)?.id ?? null) : null };
}

export function notFound(message = "Not found") {
  return NextResponse.json({ error: message }, { status: 404 });
}

export function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}
