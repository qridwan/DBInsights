import { API_URL, authHeaders } from "@/lib/api";

// Proxies "Run scan" to the dashboard API, as the signed-in user.
export async function POST(_request: Request, { params }: { params: Promise<{ app: string }> }) {
  const { app } = await params;
  try {
    const response = await fetch(`${API_URL}/v1/apps/${encodeURIComponent(app)}/scans`, { method: "POST", cache: "no-store", headers: await authHeaders() });
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
