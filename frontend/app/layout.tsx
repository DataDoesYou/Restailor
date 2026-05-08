import type { Metadata } from "next";
import dynamic from "next/dynamic";
import Script from "next/script";
import "./globals.css";
import Sidebar from "@/components/chrome/Sidebar";
import FingerprintHelper from "@/components/chrome/FingerprintHelper";
import AuthCookieSync from "@/components/chrome/AuthCookieSync";
import AuthFetchGuard from "@/components/chrome/AuthFetchGuard";
import TokenRefreshInitializer from "@/components/chrome/TokenRefreshInitializer";
import LayoutWrapper from "@/components/chrome/LayoutWrapper";

// Production security: assert no export helpers exist on window
import "@/utils/assertNoExports";

// Mount HUD client-side only so keybinding works on every page
import RtDebugHudClient from "@/components/debug/RtDebugHudClient";
import { googleAnalyticsId, siteIconUrl, siteName, siteUrl } from "@/lib/site";

const metadataBase = new URL(siteUrl);

export const metadata: Metadata = {
	title: {
		default: "Restailor - Free Open-Source AI Resume Tailoring",
		template: "%s | Restailor",
	},
	description: "Restailor is a free, open-source resume tailoring and application tracking tool. Bring your own AI provider key, keep a local usage budget, and tailor resumes without paying Restailor.",
	keywords: ["free resume builder", "open source resume tailoring", "BYOK AI resume", "bring your own key", "AI resume", "resume tailoring", "job application tracker", "ATS resume", "career tools", "job search"],
	authors: [{ name: "Restailor" }],
	creator: "Restailor",
	publisher: "Restailor",
	applicationName: "Restailor",
	robots: {
		index: true,
		follow: true,
		googleBot: {
			index: true,
			follow: true,
			'max-video-preview': -1,
			'max-image-preview': 'large',
			'max-snippet': -1,
		},
	},
	openGraph: {
		type: "website",
		locale: "en_US",
		url: siteUrl,
		siteName,
		title: "Restailor - Free Open-Source AI Resume Tailoring",
		description: "Tailor resumes and track applications with a free, open-source BYOK tool. Restailor does not sell credits or add provider markup.",
	},
	twitter: {
		card: "summary_large_image",
		title: "Restailor - Free Open-Source AI Resume Tailoring",
		description: "A free hosted resume tailoring tool for people who bring their own AI provider key.",
	},
	icons: {
		icon: [
			{ url: "/favicon.ico", sizes: "any" },
			{ url: "/apple-icon.png", sizes: "192x192", type: "image/png" },
			{ url: "/apple-icon.png", sizes: "512x512", type: "image/png" },
		],
		apple: [
			{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" },
		],
		shortcut: "/favicon.ico",
	},
	manifest: "/manifest.webmanifest",
	metadataBase,
};

function getApiBase(): string {
	const base = process.env.INTERNAL_API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "";
	if (!base) throw new Error("API base not set");
	return base.replace(/\/$/, "");
}

export default async function RootLayout({
	children,
}: Readonly<{ children: React.ReactNode }>) {
	// SSR: fetch frontend config (safe toggles) from backend so we can enable HUD/logging via app.toml
	let rtDebugUi = false;
	try {
		const res = await fetch(`${getApiBase()}/config/frontend`, { cache: 'no-store' });
		if (res.ok) {
			const js = await res.json();
			rtDebugUi = !!js?.rt_debug_ui;
		}
	} catch {}
	return (
		<html lang="en" suppressHydrationWarning style={{ backgroundColor: "#0b0e14", color: "#e2e8f0" }}>
			<head>
				<meta name="viewport" content="width=device-width, initial-scale=1" />
				{googleAnalyticsId ? (
					<>
						<Script id="google-tag-manager" src={`https://www.googletagmanager.com/gtag/js?id=${googleAnalyticsId}`} strategy="afterInteractive" />
						<Script id="google-analytics-config" strategy="afterInteractive">{`
									window.dataLayer = window.dataLayer || [];
									function gtag(){dataLayer.push(arguments);}
									gtag('js', new Date());
									gtag('config', ${JSON.stringify(googleAnalyticsId)});
								`}</Script>
					</>
				) : null}
				{/* Structured data for Google search */}
				<Script
					id="structured-data"
					type="application/ld+json"
					strategy="beforeInteractive"
					dangerouslySetInnerHTML={{ __html: JSON.stringify({
							"@context": "https://schema.org",
							"@type": "WebApplication",
							"name": siteName,
							"url": siteUrl,
							"description": "Free, open-source resume tailoring and application tracking for job seekers who bring their own AI provider key.",
							"applicationCategory": "BusinessApplication",
							"operatingSystem": "Web",
							"offers": {
								"@type": "Offer",
								"price": "0",
								"priceCurrency": "USD",
								"description": "Restailor is free to use. Model calls require a user-supplied provider API key and are billed by that provider."
							},
							"featureList": [
								"Bring-your-own-key AI model access",
								"AI-powered resume tailoring",
								"Job description matching",
								"Budget tracking for provider-cost planning",
								"Multiple AI models",
								"Application tracking"
							]
						}) }}
				/>
			</head>
			<body className="min-h-screen bg-[#0b0e14] text-slate-200 md:overflow-hidden m-0 p-0" style={{ backgroundColor: "#0b0e14", color: "#e2e8f0" }}>
				<Script id="rt-early-reload" strategy="beforeInteractive">{`(()=>{try{if(typeof window==='undefined')return;window.__rtEarlyReload={iso:new Date().toISOString(),dateNow:Date.now(),timeOrigin:performance.timeOrigin,now:performance.now(),readyState:document.readyState,pathname:location.pathname,search:location.search,nav:(()=>{try{var n=performance.getEntriesByType('navigation')[0];return n?{type:n.type,requestStart:Math.round(n.requestStart),responseStart:Math.round(n.responseStart),responseEnd:Math.round(n.responseEnd)}:null}catch{return null}})()};}catch{}})();`}</Script>
				{/* Inject server-provided frontend config (rt_debug_ui) so client can enable HUD/logs without URL/localStorage */}
				<Script id="rt-config" strategy="beforeInteractive">{`(()=>{try{if(typeof window==='undefined')return;window.__rtConfig={rt_debug_ui:${rtDebugUi ? 'true' : 'false'}};}catch{}})();`}</Script>
				{/* Client-only debug HUD overlay (gated via rtDebug flag) */}
				<RtDebugHudClient />
				{/* Global auth logout listener that runs before page components mount to nuke PII inputs */}
			<Script id="rt-auth-pii-clear" strategy="beforeInteractive">{`(()=>{try{if(typeof window==='undefined')return;window.addEventListener('rt-auth',function(e){try{var d=e&&e.detail||{};if(String(d.state||'').toLowerCase()==='logged-out'){/* PII scope: ONLY resume/jd inputs + judge ephemeral cache (outputs now managed via database snapshots) */var ks=['__rt_judge_cache_ephemeral','__rt_resume_text','__rt_jd_text','__rt_resume_ts','__rt_jd_ts'];for(var i=0;i<ks.length;i++){try{localStorage.removeItem(ks[i]);}catch{}}}}catch{}});}catch{}})();`}</Script>
			{/* Global helpers */}
			<FingerprintHelper />
			<AuthCookieSync />
			<AuthFetchGuard />
			<TokenRefreshInitializer />				{/* Layout with mobile drawer */}
				<LayoutWrapper sidebarContent={<Sidebar />}>
					{children}
				</LayoutWrapper>
			</body>
		</html>
	);
}
