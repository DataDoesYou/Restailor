import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function apiBase(): string {
  return String(process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
}

export async function POST(req: NextRequest) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const upstream = await fetch(`${apiBase()}/streams/test`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "cookie": req.headers.get("cookie") || "",
      "authorization": req.headers.get("authorization") || "",
    },
    cache: "no-store",
    body: JSON.stringify(body),
  });
  if (!upstream.ok || !upstream.body) {
    let detail: any = "missing_byok_key";
    try {
      detail = await upstream.json();
    } catch {}
    return new Response(JSON.stringify({ error: "missing_byok_key", detail }), {
      status: upstream.status || 400,
      headers: { "content-type": "application/json" },
    });
  }
  return new Response(upstream.body, {
    headers: {
      "content-type": "application/x-ndjson",
      "cache-control": "no-store, no-cache, must-revalidate, proxy-revalidate",
    },
  });
}
