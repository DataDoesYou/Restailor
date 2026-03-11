import api, { ApiOptions } from "./api";

export interface JobsAnalyticsResponse {
  counts_by_stage_active: Record<string, number>;
  hired_count: number;
  closed_count: number;
  closures_over_time: { bucket: string; count: number }[];
  funnel_active: ("applied"|"interviewing"|"offer"|"hired")[];
  snapshots_over_time?: { bucket: string; snapshots: number; applied: number }[];
  stages_over_time?: { bucket: string; interviewing: number; offer: number; hired: number }[];
  cohort_over_time?: { bucket: string; snapshots: number; applied: number; interviewing: number; offer: number; hired: number }[];
}

export async function getJobsAnalytics(options?: ApiOptions) {
  return api.get<JobsAnalyticsResponse>("/analytics/jobs", options);
}
