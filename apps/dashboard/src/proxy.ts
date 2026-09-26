import { NextResponse, type NextRequest } from "next/server";

// An optimistic check only: no cookie means certainly signed out, so go to the sign-in page and
// remember where the visitor was headed. Whether the cookie is still valid is decided by the data
// layer (requireUser), not here.
const PUBLIC = ["/login", "/register", "/verify", "/forgot-password", "/reset-password"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return NextResponse.next();
  if (request.cookies.get("dbinsight_session")) return NextResponse.next();
  // Route handlers answer 401 themselves; pages go to the sign-in form.
  if (pathname.startsWith("/api/")) return NextResponse.json({ detail: "Sign in to continue." }, { status: 401 });
  const url = new URL("/login", request.url);
  if (pathname !== "/") url.searchParams.set("next", pathname + search);
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"] };
