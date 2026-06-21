import { NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.AGENT_ORCHESTRATOR_URL;

export async function GET() {
  if (!ORCHESTRATOR_URL) {
    return NextResponse.json({ offline: true, reason: "AGENT_ORCHESTRATOR_URL not configured" });
  }
  try {
    const res = await fetch(`${ORCHESTRATOR_URL}/status`, {
      next: { revalidate: 0 },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return NextResponse.json({ offline: true, reason: `HTTP ${res.status}` });
    return NextResponse.json(await res.json());
  } catch {
    return NextResponse.json({ offline: true, reason: "Orchestrator unreachable" });
  }
}
