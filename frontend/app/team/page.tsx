import TeamClient from "@/components/pages/TeamClient";
import { Metadata } from "next";

export const metadata: Metadata = {
	title: "Team | Restailor",
	description: "Meet the founder behind Restailor, an open-source workspace for resume tailoring, fit analysis, and application tracking.",
};

export default function Page() {
	return <TeamClient />;
}
