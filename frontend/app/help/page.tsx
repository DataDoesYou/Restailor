import HelpClient from "@/components/pages/HelpClient";
import { Metadata } from "next";

export const metadata: Metadata = {
	title: "Help for Free BYOK Resume Tailoring",
	description: "Learn how Restailor works as a free, open-source BYOK resume tailoring tool with provider-key setup, budget tracking, privacy controls, and application history.",
};

export default async function Page() {
	return <HelpClient />;
}
