import { getSession } from "@/lib/session";
import AdminAnalyticsClient from "@/components/pages/AdminAnalyticsClient";

export default async function AdminAnalyticsPage() {
  const me = await getSession();
  
  // Server-side role check
  if (!me || String(me.role || "").toLowerCase() !== "admin") {
    return (
      <div className="mx-auto max-w-xl px-6 py-6">
        <div className="text-yellow-300">You need to be logged in as an admin to view this page.</div>
      </div>
    );
  }
  
  return <AdminAnalyticsClient />;
}
