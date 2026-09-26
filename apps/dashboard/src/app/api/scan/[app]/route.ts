import { API_URL } from "@/lib/api";

// Proxies "Run scan" to the dashboard API so the browser never talks to it directly.
export async function POST(_request: Request, { params }: { params: Promise<{ app: string }> }) {
  const { app } = await params;
  try {
    const response = await fetch(`${API_URL}/v1/apps/${encodeURIComponent(app)}/scans`, { method: "POST", cache: "no-store" });
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
