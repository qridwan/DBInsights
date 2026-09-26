import { API_URL, authHeaders } from "@/lib/api";

// Lists folders on the machine running the API, for the project picker. Administrators only:
// the API enforces that, this just forwards the signed-in user.
export async function GET(request: Request) {
  const query = new URL(request.url).searchParams.toString();
  try {
    const response = await fetch(`${API_URL}/v1/fs/browse${query ? `?${query}` : ""}`, { cache: "no-store", headers: await authHeaders() });
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
