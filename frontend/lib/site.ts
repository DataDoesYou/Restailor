const defaultSiteUrl = "http://localhost:3000";
const defaultSupportEmail = "support@example.com";
const defaultGoogleAnalyticsId = "";

function normalizeSiteUrl(value: string | undefined): string {
  const candidate = (value || defaultSiteUrl).trim();
  try {
    return new URL(candidate).origin;
  } catch {
    return defaultSiteUrl;
  }
}

export const siteName = "Restailor";
export const siteUrl = normalizeSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);
export const siteIconUrl = new URL("/apple-icon.png", siteUrl).toString();
export const supportEmail = (process.env.NEXT_PUBLIC_SUPPORT_EMAIL || defaultSupportEmail).trim() || defaultSupportEmail;
export const supportMailto = `mailto:${supportEmail}`;
export const googleAnalyticsId = typeof process.env.NEXT_PUBLIC_GTAG_ID === "string"
  ? process.env.NEXT_PUBLIC_GTAG_ID.trim()
  : defaultGoogleAnalyticsId;

const bugReportBody = [
  "BUG DESCRIPTION",
  "",
  "What happened?",
  "",
  "",
  "STEPS TO REPRODUCE",
  "",
  "1. ",
  "2. ",
  "3. ",
  "",
  "EXPECTED BEHAVIOR",
  "",
  "What did you expect to happen?",
  "",
  "",
  "ACTUAL BEHAVIOR",
  "",
  "What actually happened?",
  "",
  "",
  "BROWSER & DEVICE",
  "",
  "Browser: ",
  "Device: ",
  "",
  "ADDITIONAL CONTEXT",
  "",
  "Any screenshots or additional information?",
].join("\n");

export const bugReportMailto = `mailto:${supportEmail}?subject=${encodeURIComponent("Bug Report")}&body=${encodeURIComponent(bugReportBody)}`;