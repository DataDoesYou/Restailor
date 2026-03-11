"use client";

/**
 * Passthrough component - no longer performs protection.
 * Protected routes now use client-side redirects in their respective components
 * (BillingClient, AdminClient, SettingsClient, SecurityClient, ResumeTailorClient).
 * 
 * This file exists to prevent build errors from cached webpack references.
 * It can be safely deleted once all Next.js caches are cleared.
 */
export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
