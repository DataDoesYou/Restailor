import { headers } from "next/headers";
import "server-only";
import SettingsClient from "@/components/pages/SettingsClient";

function getApiBase(): string {
	const base = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
	if (!base) throw new Error("API base not set");
	return base.replace(/\/$/, "");
}

export default async function Page() {
	// SSR auth check to prevent redirect flicker on refresh
	const h = await headers();
	const cookie = h.get("cookie") || "";
	const hasAuth = /(?:^|; )rt_session=/.test(cookie) || /(?:^|; )rt_access=/.test(cookie) || /(?:^|; )rt_access_ephem=/.test(cookie);

	let initialSettings: any = null;

	// Fetch settings server-side if auth cookies present
	if (hasAuth) {
		try {
			const res = await fetch(`${getApiBase()}/users/me/settings`, {
				headers: cookie ? { Cookie: cookie } : undefined,
				credentials: "include",
				cache: "no-store",
			});
			if (res.ok) {
				initialSettings = await res.json();
			}
		} catch (e) {
			console.error('[settings/page] SSR settings fetch failed:', e);
		}
	}

	return <SettingsClient initialSettings={initialSettings} />;
}
