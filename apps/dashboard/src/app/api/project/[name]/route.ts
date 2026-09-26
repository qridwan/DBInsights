import { API_URL } from "@/lib/api";

export async function POST(_request: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  try {
    const response = await fetch(`${API_URL}/v1/projects/${encodeURIComponent(name)}/rescan`, { method: "POST", cache: "no-store" });
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
