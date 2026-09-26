import { API_URL, authHeaders } from "@/lib/api";

async function forward(method: "POST" | "DELETE", name: string, path: string) {
  try {
    const response = await fetch(`${API_URL}/v1/projects/${encodeURIComponent(name)}${path}`, { method, cache: "no-store", headers: await authHeaders() });
    return new Response(response.status === 204 ? null : await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}

export async function POST(_request: Request, { params }: { params: Promise<{ name: string }> }) {
  return forward("POST", (await params).name, "/rescan");
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ name: string }> }) {
  return forward("DELETE", (await params).name, "");
}
