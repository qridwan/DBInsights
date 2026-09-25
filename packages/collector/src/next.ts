import { randomUUID } from "node:crypto";
// Next.js keeps one work store per request in an AsyncLocalStorage. It is not
// public API, but it is the only way to learn the route without editing every
// route handler. Only the fields below are read.
import { workAsyncStorage } from "next/dist/server/app-render/work-async-storage.external";
import type { RequestContext } from "./types";

const requestIds = new WeakMap<object, string>();

/**
 * Request context for Next.js App Router handlers: a per-request id and the
 * route pattern (e.g. "/api/orders/[id]/invoice"). Undefined outside a request.
 */
export function nextRequestContext(): RequestContext | undefined {
  const store = workAsyncStorage.getStore();
  if (!store) return undefined;
  let requestId = requestIds.get(store);
  if (!requestId) {
    requestId = randomUUID();
    requestIds.set(store, requestId);
  }
  return { requestId, route: store.route ?? null };
}
