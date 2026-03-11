"use client";

import HistoryClient from "../../components/history/HistoryClient";

// Client-side only page - no SSR, no caching, just like DB Test page
// Database is the single source of truth, fetched on mount
export default function HistoryPage() {
  return (
    <HistoryClient
      initialPage={1}
      initialPageSize={25}
      initialSearch=""
      initialShowAppliedOnly={false}
      initialArchived={false}
      initialResponse={null}
      initialSortBy={null}
      initialSortDir="desc"
      initialStageFilter={{ interviewing: false, offer: false, hired: false }}
    />
  );
}
