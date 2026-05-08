import { headers } from "next/headers";
import BillingClient from "@/components/pages/BillingClient";
import { Metadata } from "next";

export const metadata: Metadata = {
  title: "Budget",
  description: "Track provider-cost-equivalent usage for your own AI provider keys. Restailor Budget is a free usage-control tool, not a payment page.",
};

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
      headers: cookie ? { Cookie: cookie } : undefined,
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
  const cookie = (await headers()).get("cookie") || "";
  const [balance, trial, budgetSummary, me] = await Promise.all([
    fetchJsonWithCookies("/users/me/balance"),
    fetchJsonWithCookies("/credits/trial-eligibility"),
    fetchJsonWithCookies("/budget/summary"),
    fetchJsonWithCookies("/users/me"),
  ]);
  const m = /(?:^|; )rt_use_my_avgs=([^;]+)/.exec(cookie);
  const initialUseMyAvgs = m ? m[1] === "1" : false;
  const initialUserAvgs = initialUseMyAvgs ? (await fetchJsonWithCookies("/pricing/averages?scope=user")) : null;
  return (
    <BillingClient
      initialBalance={balance}
      initialTrial={trial}
      initialSummary={budgetSummary}
      initialIsAdmin={Boolean(me?.role === "admin")}
      initialUseMyAvgs={initialUseMyAvgs}
      initialUserAvgs={Array.isArray(initialUserAvgs) ? initialUserAvgs : undefined}
    />
  );
}
