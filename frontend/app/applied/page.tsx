"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

interface ApplicationListItem {
  appliedKey: string;
  jdSnippet?: string | null;
  jdHash: string;
  baseHash: string;
  updatedAt: string;
  // legacy fields still sent by API (ignored now)
  company?: string | null;
  role?: string | null;
  jdUrl?: string | null;
}
interface ApplicationListResponse {
  page: number;
  pageSize: number;
  total: number;
  items: ApplicationListItem[];
}

export default function AppliedRedirectPage(){
  const router = useRouter();
  useEffect(()=>{ router.replace('/history'); },[router]);
  return <div className="p-4 text-slate-300">Redirecting to History…</div>;
}
