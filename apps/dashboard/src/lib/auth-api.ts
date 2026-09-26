import "server-only";
import { API_URL, authHeaders } from "./api";

export type AuthResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; code: string; message: string; extra: Record<string, unknown> };

/** Calls the account endpoints. Errors come back as data (`{ok:false, code, message}`), never thrown. */
export async function authCall<T = Record<string, unknown>>(path: string, body?: unknown, method: "POST" | "GET" | "PATCH" = "POST"): Promise<AuthResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/v1/auth${path}`, {
      method,
      cache: "no-store",
      headers: { ...(await authHeaders()), ...(body !== undefined ? { "content-type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    return { ok: false, status: 0, code: "unreachable", message: "We cannot reach the server right now. Please try again in a moment.", extra: {} };
  }
  const text = await response.text();
  let json: Record<string, unknown> = {};
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    /* an empty or non-JSON body */
  }
  if (response.ok) return { ok: true, status: response.status, data: json as T };
  const code = typeof json.code === "string" ? json.code : response.status === 422 ? "invalid_input" : "error";
  const message = typeof json.message === "string" ? json.message : "Something went wrong. Check the details and try again.";
  return { ok: false, status: response.status, code, message, extra: json };
}

/** Only follow same-site paths after signing in, so `?next=` cannot send anyone elsewhere. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.includes("\\")) return "/";
  if (["/login", "/register", "/verify", "/forgot-password", "/reset-password"].some((p) => next === p || next.startsWith(`${p}?`) || next.startsWith(`${p}/`))) return "/";
  return next;
}
