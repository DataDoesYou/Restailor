import TeamClient from "@/components/pages/TeamClient";
import { Metadata } from "next";

export const metadata: Metadata = {
	title: "Team | Restailor",
};

export default function Page() {
	return <TeamClient />;
}
