import ResetPasswordClient from "@/components/pages/ResetPasswordClient";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

export default async function Page() {
  return (
    <Suspense>
      <ResetPasswordClient />
    </Suspense>
  );
}
