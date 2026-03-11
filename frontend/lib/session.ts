import { headers } from "next/headers";
import { redirect } from "next/navigation";

function getApiBase(): string {
  // Prefer internal base URL for server components (SSR) inside Docker
  const isServer = typeof window === "undefined";
  const base = (isServer ? process.env.INTERNAL_API_BASE_URL : undefined)
    || process.env.NEXT_PUBLIC_API_URL
    || process.env.NEXT_PUBLIC_API_BASE_URL
    || "";
  if (!base) throw new Error("INTERNAL_API_BASE_URL or NEXT_PUBLIC_API_URL (or NEXT_PUBLIC_API_BASE_URL) is not set");
  return base.replace(/\/$/, "");
}

export type SessionUser = {
  id?: string | number;
  email?: string;
  role?: string;
  [k: string]: unknown;
} | null;

export async function getSession(): Promise<SessionUser> {
  const h = await headers();
  const cookie = h.get("cookie") || "";
  try {
    const res = await fetch(`${getApiBase()}/users/me`, {
      headers: cookie ? { Cookie: cookie } : undefined,
      // include cookies from incoming request
      credentials: "include",
      cache: "no-store",
      // small timeout behavior could be set by fetch keepalive; keep minimal here
    });
    if (!res.ok) return null;
    return (await res.json()) as SessionUser;
  } catch {
    return null;
  }
}

export async function requireSession(): Promise<NonNullable<SessionUser>> {
  const u = await getSession();
  if (!u) redirect("/");
  return u!;
}

export async function redirectIfAuthenticated(path: string = "/resume"): Promise<void> {
  const u = await getSession();
  if (u) redirect(path);
}
