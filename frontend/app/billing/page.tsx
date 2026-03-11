import { headers } from "next/headers";
import BillingClient from "@/components/pages/BillingClient";

function getApiBase(): string {
  const isServer = typeof window === "undefined";
  const base = (isServer ? process.env.INTERNAL_API_BASE_URL : undefined)
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || "";
  if (!base) throw new Error("INTERNAL_API_BASE_URL or NEXT_PUBLIC_API_BASE_URL is not set");
  return base.replace(/\/$/, "");
}

async function fetchJsonWithCookies(path: string): Promise<any | null> {
  try {
    const h = await headers();
    const cookie = h.get("cookie") || "";
    const res = await fetch(`${getApiBase()}${path}`, {
      headers: {
        ...(cookie ? { Cookie: cookie } : {}),
      },
      credentials: "include",
      cache: "no-store",
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export default async function Page() {
  // Client-side auth guard (more reliable cross-platform than SSR session check)
  // Server-render initial data to avoid client-only flash/flicker
  const cookie = (await headers()).get("cookie") || "";
  const [balance, trial, summary, me] = await Promise.all([
    fetchJsonWithCookies("/users/me/balance"),
    fetchJsonWithCookies("/credits/trial-eligibility"),
    fetchJsonWithCookies("/billing/summary"),
    fetchJsonWithCookies("/users/me"),
  ]);
  const isAdmin = Boolean(me?.role === "admin");
  // Read userAvgs toggle from cookie to keep SSR and client in sync
  const m = /(?:^|; )rt_use_my_avgs=([^;]+)/.exec(cookie);
  const initialUseMyAvgs = m ? m[1] === "1" : false;
  const initialUserAvgs = initialUseMyAvgs ? (await fetchJsonWithCookies("/pricing/averages?scope=user")) : null;
  return (
    <BillingClient
      initialBalance={balance}
      initialTrial={trial}
      initialSummary={summary}
      initialIsAdmin={isAdmin}
      initialUseMyAvgs={initialUseMyAvgs}
      initialUserAvgs={Array.isArray(initialUserAvgs) ? initialUserAvgs : undefined}
    />
  );
}
