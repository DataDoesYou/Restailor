import { getSession } from "@/lib/session";
import AdminClient from "@/components/pages/AdminClient";

export default async function Page() {
  const me = await getSession();
  return <AdminClient initialMe={me} />;
}
