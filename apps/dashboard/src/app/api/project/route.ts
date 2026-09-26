import { API_URL, authHeaders } from "@/lib/api";

// Proxies "Scan a project" (a Git URL, or a folder for administrators) to the dashboard API.
export async function POST(request: Request) {
  try {
    const response = await fetch(`${API_URL}/v1/projects/scans`, {
      method: "POST",
      headers: { ...(await authHeaders()), "content-type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
