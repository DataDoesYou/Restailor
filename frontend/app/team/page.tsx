import TeamClient from "@/components/pages/TeamClient";
import { Metadata } from "next";

export const metadata: Metadata = {
	title: "Team | Restailor",
	description: "Meet the founder behind Restailor, a free, open-source hosted resume tailoring and application tracking tool.",
};

export default function Page() {
	return <TeamClient />;
}
