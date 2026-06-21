import { NextResponse } from "next/server";

const ORCHESTRATOR_URL = process.env.AGENT_ORCHESTRATOR_URL;

export async function POST(request: Request) {
  if (!ORCHESTRATOR_URL) {
    return NextResponse.json({ error: "Agent layer not configured" }, { status: 503 });
  }
  try {
    const body = await request.json();
    const res = await fetch(`${ORCHESTRATOR_URL}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: "Orchestrator unreachable" }, { status: 503 });
  }
}
