import HelpClient from "@/components/pages/HelpClient";
import { Metadata } from "next";

export const metadata: Metadata = {
	title: "Help for Free BYOK Resume Tailoring",
	description: "Learn how to tailor resumes, compare fit, manage your provider key, track Budget usage, and keep application history in Restailor.",
};

export default async function Page() {
	return <HelpClient />;
}
