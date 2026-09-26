import { API_URL } from "@/lib/api";

export async function GET(_request: Request, { params }: { params: Promise<{ scan: string; finding: string }> }) {
  const { scan, finding } = await params;
  try {
    const response = await fetch(
      `${API_URL}/v1/scans/${encodeURIComponent(scan)}/findings/${encodeURIComponent(finding)}/explanation`,
      { cache: "no-store" },
    );
    return new Response(await response.text(), { status: response.status, headers: { "content-type": "application/json" } });
  } catch {
    return Response.json({ detail: `Cannot reach the dashboard API at ${API_URL}` }, { status: 502 });
  }
}
