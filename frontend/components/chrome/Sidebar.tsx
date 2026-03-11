import SidebarClient from "@/components/chrome/SidebarClient";
import SidebarSkeleton from "@/components/chrome/SidebarSkeleton";
import { headers } from "next/headers";

function getApiBase(): string {
  const isServer = typeof window === "undefined";
  const base = (isServer ? process.env.INTERNAL_API_BASE_URL : undefined)
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || "";
  if (!base) throw new Error("INTERNAL_API_BASE_URL or NEXT_PUBLIC_API_BASE_URL is not set");
  return base.replace(/\/$/, "");
}

async function fetchMeWithCookies(): Promise<any | null> {
  try {
    const h = await headers();
    const cookie = h.get("cookie") || "";
    const hasRtSession = cookie.includes("rt_session=");
    
    // DEBUG: Log what we're seeing
    console.log('[Sidebar SSR] Cookie header:', { 
      hasCookie: !!cookie, 
      length: cookie.length, 
      hasRtSession,
      cookiePreview: cookie.substring(0, 100)
    });
    
    // If client stores bearer token in a cookie for SSR visibility, forward it as Authorization.
    const res = await fetch(`${getApiBase()}/users/me`, {
      headers: {
  ...(cookie ? { Cookie: cookie } : {}),
      },
      credentials: "include",
      cache: "no-store",
    });
    
    console.log('[Sidebar SSR] API response:', { status: res.status, ok: res.ok });
    
    if (!res.ok) return null;
    const data = await res.json();
    console.log('[Sidebar SSR] Got user:', { email: data?.email });
    return data;
  } catch (e) {
    console.error('[Sidebar SSR] Error fetching user:', e);
    return null;
  }
}

async function fetchBalanceWithCookies(): Promise<any | null> {
  try {
    const h = await headers();
    const cookie = h.get("cookie") || "";
    const res = await fetch(`${getApiBase()}/users/me/balance`, {
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

export default async function Sidebar() {
  const h = await headers();
  const cookie = h.get("cookie") || "";
  const hasAuthCookie = /(?:^|; )rt_session=/.test(cookie) || /(?:^|; )rt_access=/.test(cookie) || /(?:^|; )rt_access_ephem=/.test(cookie);
  
  // DB-only approach: No cookie hydration for model preferences
  // Model preferences will be fetched from DB on client mount
  
  // Always try to fetch the user - don't rely solely on cookie string check
  // The cookie might be present but not visible in the header string during SSR
  const me = await fetchMeWithCookies();
  const balance = me ? await fetchBalanceWithCookies() : null;
  
  return <SidebarClient initialMe={me} initialBalance={balance} />;
}
