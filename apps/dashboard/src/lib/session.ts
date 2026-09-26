import "server-only";
import { cookies, headers } from "next/headers";

// The session token lives in an httpOnly cookie: page scripts can never read it. Only server code
// (server components, server actions, route handlers) sees it and forwards it to the API.
export const COOKIE = "dbinsight_session";

export async function getToken(): Promise<string | undefined> {
  return (await cookies()).get(COOKIE)?.value;
}

// A Secure cookie is only kept over HTTPS. That is right for a deployed dashboard, but the desktop
// app (and anyone running a production build on their own machine) uses http://localhost, where
// some web views drop it and sign-in would silently fail. DBINSIGHT_COOKIE_SECURE=0 turns it off.
const secure = process.env.DBINSIGHT_COOKIE_SECURE ? process.env.DBINSIGHT_COOKIE_SECURE !== "0" : process.env.NODE_ENV === "production";

export async function setSession(token: string, expiresAt: string): Promise<void> {
  (await cookies()).set(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    expires: new Date(expiresAt),
  });
}

export async function clearSession(): Promise<void> {
  (await cookies()).delete(COOKIE);
}

/** The visitor's address, forwarded so the API can rate-limit per address rather than per server. */
export async function clientIp(): Promise<string | undefined> {
  const h = await headers();
  return h.get("x-forwarded-for")?.split(",")[0]?.trim() || h.get("x-real-ip") || undefined;
}

export async function userAgent(): Promise<string | undefined> {
  return (await headers()).get("user-agent") ?? undefined;
}
