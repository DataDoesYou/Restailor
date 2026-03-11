"use client";
import dynamic from "next/dynamic";

const RtDebugHud = dynamic(() => import("./RtDebugHud"), { ssr: false });

export default function RtDebugHudClient() {
  return <RtDebugHud />;
}
