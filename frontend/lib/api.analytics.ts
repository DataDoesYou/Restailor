import api, { ApiOptions, getApiBaseUrl } from "./api";

export type Bucket = "day" | "week" | "month";

export interface AnalyticsParams {
  from: string; // ISO8601
  to: string;   // ISO8601
  bucket: Bucket;
  recentLimit?: number;
  tz?: string; // IANA timezone, e.g., "America/Los_Angeles"
}

export async function getAnalyticsSummary(params: AnalyticsParams, options?: ApiOptions) {
  const query: Record<string, string> = { from: params.from, to: params.to, bucket: params.bucket };
  if (params.recentLimit) query["recent_limit"] = String(params.recentLimit);
  if (params.tz) query["tz"] = params.tz;
  return api.get<any>("/analytics/summary", { ...(options || {}), query });
}
