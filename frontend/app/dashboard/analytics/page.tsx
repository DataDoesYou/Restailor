import React, { Suspense } from "react";
import { cookies } from "next/headers";
import AnalyticsClient from "../../../components/pages/AnalyticsClient";

export default async function AnalyticsPage() {
  const c = await cookies();
  const fromCookie = c.get("analytics_active")?.value || "overview";
  return (
    <Suspense fallback={<div className="px-6 py-6">Loading…</div>}>
      <AnalyticsClient initialActive={fromCookie} />
    </Suspense>
  );
}
