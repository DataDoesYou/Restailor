import type { Metadata } from "next";
import dynamic from "next/dynamic";
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
		default: "Restailor - Tailor Your Resume to Any Job with AI",
		template: "%s | Restailor",
	},
	description: "Instantly customize your resume for every job application using advanced AI. Match job descriptions perfectly, highlight relevant skills, and land more interviews. Free trial available.",
	keywords: ["resume builder", "AI resume", "resume tailoring", "job application", "resume optimization", "ATS resume", "career tools", "job search", "resume customization"],
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
		title: "Restailor - Tailor Your Resume to Any Job with AI",
		description: "Instantly customize your resume for every job application using advanced AI. Match job descriptions perfectly, highlight relevant skills, and land more interviews.",
		images: [
			{
				url: siteIconUrl,
				width: 180,
				height: 180,
				alt: "Restailor - AI Resume Tailoring Tool",
			},
		],
	},
	twitter: {
		card: "summary_large_image",
		title: "Restailor - Tailor Your Resume to Any Job with AI",
		description: "Instantly customize your resume for every job application. Match job descriptions perfectly and land more interviews.",
		images: [siteIconUrl],
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
		<html lang="en" suppressHydrationWarning>
			<head>
				<meta name="viewport" content="width=device-width, initial-scale=1" />
				{googleAnalyticsId ? (
					<>
						<script async src={`https://www.googletagmanager.com/gtag/js?id=${googleAnalyticsId}`}></script>
						<script
							dangerouslySetInnerHTML={{
								__html: `
									window.dataLayer = window.dataLayer || [];
									function gtag(){dataLayer.push(arguments);}
									gtag('js', new Date());
									gtag('config', ${JSON.stringify(googleAnalyticsId)});
								`,
							}}
						/>
					</>
				) : null}
				{/* Structured data for Google search */}
				<script
					type="application/ld+json"
					dangerouslySetInnerHTML={{
						__html: JSON.stringify({
							"@context": "https://schema.org",
							"@type": "WebApplication",
							"name": siteName,
							"url": siteUrl,
							"description": "Instantly customize your resume for every job application using advanced AI. Match job descriptions perfectly, highlight relevant skills, and land more interviews.",
							"applicationCategory": "BusinessApplication",
							"offers": {
								"@type": "Offer",
								"price": "0",
								"priceCurrency": "USD"
							},
							"featureList": [
								"AI-powered resume tailoring",
								"Job description matching",
								"ATS optimization",
								"Multiple AI models",
								"Application tracking"
							]
						})
					}}
				/>
			</head>
			<body className="min-h-screen bg-[#0b0e14] text-slate-200 md:overflow-hidden m-0 p-0">
				{/* Inject server-provided frontend config (rt_debug_ui) so client can enable HUD/logs without URL/localStorage */}
				<script
					suppressHydrationWarning
					dangerouslySetInnerHTML={{ __html: `(()=>{try{if(typeof window==='undefined')return;window.__rtConfig={rt_debug_ui:${rtDebugUi ? 'true' : 'false'}};}catch{}})();` }}
				/>
				{/* Client-only debug HUD overlay (gated via rtDebug flag) */}
				<RtDebugHudClient />
				{/* Global auth logout listener that runs before page components mount to nuke PII inputs */}
			<script
				dangerouslySetInnerHTML={{ __html: `(()=>{try{if(typeof window==='undefined')return;window.addEventListener('rt-auth',function(e){try{var d=e&&e.detail||{};if(String(d.state||'').toLowerCase()==='logged-out'){/* PII scope: ONLY resume/jd inputs + judge ephemeral cache (outputs now managed via database snapshots) */var ks=['__rt_judge_cache_ephemeral','__rt_resume_text','__rt_jd_text','__rt_resume_ts','__rt_jd_ts'];for(var i=0;i<ks.length;i++){try{localStorage.removeItem(ks[i]);}catch{}}}}catch{}});}catch{}})();` }}
			/>
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
